"""
Invoice PDF generator.

Renders an invoice (+ its line items) using the Django template at
`templates/invoiceprint/invoice.html`, with merge fields replaced via
`replace_merge_fields`. The organization section is pulled from the
`public.organizations` table plus the Organization model's logo.

Endpoint:
    GET  /v2/api/invoice/<invoice_id>/pdf   → downloads invoice.pdf
    GET  /v2/api/invoice/<invoice_id>/pdf?preview=1 → renders HTML for debug
"""
import os
from io import BytesIO

from django.conf import settings
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.template.loader import get_template
from rest_framework.views import APIView

from authentication.custom_jwt_auth import CustomJWTAuthentication
from public.auth.session import get_connection_and_user_details
from api.BL.mergefields import replace_merge_fields
from api.models import Organization


def _fetch_record(table_name, where_field, where_value, schema):
    """Fetch a single record as a dict from a tenant table."""
    with connection.cursor() as cursor:
        cursor.execute("SET search_path TO %s", [schema])
        cursor.execute(
            f'SELECT * FROM "{table_name}" WHERE "{where_field}" = %s LIMIT 1',
            [where_value],
        )
        row = cursor.fetchone()
        if not row:
            return None
        cols = [desc[0] for desc in cursor.description]
        return dict(zip(cols, row))


def _fetch_records(table_name, where_field, where_value, schema):
    """Fetch multiple records as list of dicts."""
    with connection.cursor() as cursor:
        cursor.execute("SET search_path TO %s", [schema])
        cursor.execute(
            f'SELECT * FROM "{table_name}" WHERE "{where_field}" = %s',
            [where_value],
        )
        rows = cursor.fetchall()
        cols = [desc[0] for desc in cursor.description]
        return [dict(zip(cols, row)) for row in rows]


def _get_organization_details(org_id, schema, request):
    """
    Fetch organization details from the tenant-schema `organization` table.
    Falls back to the `public.organizations` Django model for the logo
    when no in-tenant logo URL is set.
    """
    details = {
        "name": "", "company_name": "", "primary_contact": "", "division": "",
        "phone": "", "fax": "", "email": "", "website": "",
        "street": "", "city": "", "state": "", "postal_code": "", "country": "",
        "default_currency": "USD", "timezone": "UTC",
        "description": "", "logo_url": None, "domain": "",
    }

    # 1) Fetch full company profile from tenant schema's organization table
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO %s", [schema])
            cursor.execute(
                """
                SELECT company_name, primary_contact, division, phone, fax, email,
                       website, street, city, state, postal_code, country,
                       default_currency, default_language, timezone,
                       fiscal_year_start_month, description, logo
                FROM organization
                WHERE is_deleted = FALSE
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            if row:
                details.update({
                    "company_name": row[0] or "",
                    "name": row[0] or "",  # keep 'name' alias for template compat
                    "primary_contact": row[1] or "",
                    "division": row[2] or "",
                    "phone": row[3] or "",
                    "fax": row[4] or "",
                    "email": row[5] or "",
                    "website": row[6] or "",
                    "street": row[7] or "",
                    "city": row[8] or "",
                    "state": row[9] or "",
                    "postal_code": row[10] or "",
                    "country": row[11] or "",
                    "default_currency": row[12] or "USD",
                    "default_language": row[13] or "en",
                    "timezone": row[14] or "UTC",
                    "fiscal_year_start_month": row[15] or "April",
                    "description": row[16] or "",
                    "logo_url": row[17] or None,
                })
    except Exception as e:
        print(f"[invoice_pdf] Could not fetch tenant organization: {e}")

    # 2) Fallback: if no logo on the tenant row, use the Django Organization model's logo
    if not details.get("logo_url"):
        try:
            org = Organization.objects.get(pk=org_id)
            if org.logo:
                base = request.build_absolute_uri("/")
                details["logo_url"] = f"{base.rstrip('/')}api{org.logo.url}"
        except Organization.DoesNotExist:
            pass
        except Exception:
            pass

    # 3) If still no company_name, fallback to public.organizations.name
    if not details.get("name"):
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    'SELECT name, domain FROM public.organizations WHERE id = %s',
                    [org_id],
                )
                row = cursor.fetchone()
                if row:
                    details["name"] = row[0] or ""
                    details["company_name"] = row[0] or ""
                    details["domain"] = row[1] or ""
        except Exception:
            pass

    return details


def _apply_merge_fields_to_template(template_html, object_name, record_data):
    """Wrapper around replace_merge_fields for the full template string."""
    try:
        return replace_merge_fields(template_html, object_name, record_data)
    except Exception:
        return template_html


def _render_invoice_html(invoice_id, request):
    """Build the invoice HTML from the template + records."""
    user, org, _conn, _profile_id, schema, _referer = get_connection_and_user_details(request)
    if not org:
        raise PermissionError("Could not determine organisation for this user.")

    schema = schema or "public"
    org_id = org.get("id")

    # Fetch invoice record
    invoice = _fetch_record("invoice", "id", invoice_id, schema)
    if not invoice:
        raise ValueError(f"Invoice '{invoice_id}' not found.")

    # Fetch related account
    account = {}
    if invoice.get("account_id"):
        account = _fetch_record("accounts", "id", invoice["account_id"], schema) or {}

    # Fetch line items
    invoice_items = _fetch_records("invoice_item", "invoice_id", invoice_id, schema) or []

    # Compute formula/rollup values for invoice and its items
    try:
        from api.BL.computed_fields import apply_computed_fields_to_records

        # Build computed field meta for invoice (rollup summaries)
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO %s", [schema])
            cursor.execute("""
                SELECT f.name, f.datatype, f.formula_expression, f.formula_return_type,
                       f.summarized_object, f.rollup_type, f.field_to_aggregate, f.filter_criteria
                FROM fields f
                WHERE f.object_name = %s AND f.datatype IN ('formula', 'rollup_summary')
            """, ["invoice"])
            inv_computed = {
                row[0]: {
                    "name": row[0], "datatype": row[1],
                    "formula_expression": row[2], "formula_return_type": row[3],
                    "summarized_object": row[4], "rollup_type": row[5],
                    "field_to_aggregate": row[6], "filter_criteria": row[7],
                }
                for row in cursor.fetchall()
            }
            cursor.execute("""
                SELECT f.name, f.datatype, f.formula_expression, f.formula_return_type,
                       f.summarized_object, f.rollup_type, f.field_to_aggregate, f.filter_criteria
                FROM fields f
                WHERE f.object_name = %s AND f.datatype IN ('formula', 'rollup_summary')
            """, ["invoice_item"])
            item_computed = {
                row[0]: {
                    "name": row[0], "datatype": row[1],
                    "formula_expression": row[2], "formula_return_type": row[3],
                    "summarized_object": row[4], "rollup_type": row[5],
                    "field_to_aggregate": row[6], "filter_criteria": row[7],
                }
                for row in cursor.fetchall()
            }

        if inv_computed:
            apply_computed_fields_to_records([invoice], inv_computed, "invoice", schema)
        if item_computed and invoice_items:
            apply_computed_fields_to_records(invoice_items, item_computed, "invoice_item", schema)
    except Exception as e:
        print(f"[invoice_pdf] Could not compute formula/rollup: {e}")

    organization = _get_organization_details(org_id, schema, request)

    # Render Django template
    template = get_template("invoiceprint/invoice.html")
    html = template.render({
        "invoice": invoice,
        "invoice_items": invoice_items,
        "account": account,
        "organization": organization,
    })

    # Apply user-defined merge fields ({!Invoice.field}, {!Account.field}, etc.)
    html = _apply_merge_fields_to_template(html, "invoice", invoice)
    html = _apply_merge_fields_to_template(html, "account", account)
    html = _apply_merge_fields_to_template(html, "organization", organization)

    return html, invoice


def _html_to_pdf(html_string):
    """
    Convert HTML to PDF bytes.
    Tries xhtml2pdf first (pure Python, no system deps).
    Falls back to returning None if no PDF library is available.
    """
    try:
        from xhtml2pdf import pisa
    except ImportError:
        return None

    pdf_buffer = BytesIO()
    pisa_status = pisa.CreatePDF(src=html_string, dest=pdf_buffer, encoding="utf-8")
    if pisa_status.err:
        return None
    return pdf_buffer.getvalue()


class InvoicePDFView(APIView):
    """
    GET /v2/api/invoice/<invoice_id>/pdf
    Returns the rendered invoice as a PDF download.

    Query params:
        preview=1  → return HTML (for layout testing)
    """
    authentication_classes = [CustomJWTAuthentication]

    def get(self, request, invoice_id):
        try:
            html, invoice = _render_invoice_html(invoice_id, request)
        except PermissionError as e:
            return JsonResponse({"error": str(e)}, status=403)
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=404)
        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

        # Preview mode — return raw HTML
        if request.GET.get("preview") in ("1", "true"):
            return HttpResponse(html, content_type="text/html")

        pdf_bytes = _html_to_pdf(html)
        if not pdf_bytes:
            return JsonResponse({
                "error": "PDF generation library not installed. Install 'xhtml2pdf' (pip install xhtml2pdf) or use ?preview=1 to view the HTML.",
            }, status=501)

        filename = f"invoice_{invoice.get('name') or invoice_id}.pdf"
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
