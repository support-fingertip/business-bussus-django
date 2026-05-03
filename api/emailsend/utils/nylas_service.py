from nylas.models.auth import URLForAuthenticationConfig,CodeExchangeRequest
from nylas import Client
from django.conf import settings
from rest_framework.views import APIView
from nylas.models.errors import NylasApiError
from .outlook_service import is_html_template,create_outlook_message
from .mergefields import get_record_from_sql, replace_merge_fields
from rest_framework.permissions import AllowAny 
from rest_framework.response import Response

nylas = Client(
    api_key=settings.NYLAS_API_KEY,
    api_uri=settings.NYLAS_API_URL
)


# class NylasSendMail(APIView):
#     authentication_classes = []
#     permission_classes = [AllowAny]

    # def __init__(self,request, **kwargs):
    #     self.request = request
    #     self.kwargs = kwargs

def nylas_callBack(request):
    try:
        code = request.GET.get("code")
        state = request.GET.get("state")
        if not code and not state:
            return {"error": "Missing code"}
        exchange_request = CodeExchangeRequest({
            "redirect_uri": "http://localhost:8000/v2/api/nylas/one/call-back",
            "code": code,
            "client_id":'f3300862-189f-4025-bd8d-295f2dd03682',
        })
        exchange = nylas.auth.exchange_code_for_token(exchange_request)
        grant_id = exchange.grant_id 
        email = exchange.email 
        provider = exchange.provider      
        userQuery = """UPDATE public.users SET grand_id = %s,email = %s WHERE id = %s"""
        run_query(userQuery,[grant_id,email,state])
        return Response({
            "message": "Email connected",
            "grant_id": grant_id,
            "email": email,
            "provider": provider
        })
    except Exception as er:
        print(er)


def another_callback(request):
    print(request)
    return

    

    
def run_query(query, params=None, fetch_one=False, commit=False, **kwargs):
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute(query, params or [])
        if commit:
            return {"status": "success"}
        if cursor.description:
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
            if fetch_one:
                return dict(zip(columns, rows[0])) if rows else None
            return [dict(zip(columns, row)) for row in rows]
        return []



def compose_mail(**kwars):
    grant_id = kwars.get("grant_id")
    body = kwars.get("body")
    subject=kwars.get("subject")
    from_email = kwars.get("from_email")
    to_email = kwars.get("to_email")
    try:
        draft_obj, _ = nylas.drafts.create(
            grant_id,
            request_body={
                "to": [{"email": to_email}],
                "from": [{"email": from_email}],
                "subject": subject,
                "body": body,
            },
        )
        sent_obj, _ = nylas.drafts.send(grant_id, draft_obj.id)
        return {
                "status": "sent",
                "message_id": sent_obj.id,
                "from": from_email,
                "to": to_email,
            }

    except NylasApiError as e:
        return  {
                "status": "error",
                "error": "Nylas API error",
                "details": str(e),
            }
    except Exception as e:
        return {
                "status": "error",
                "error": "Server error",
                "details": str(e),
            }




def send_email_using_nylas(data,**kwargs):
    subject = data.get("template_subject")
    body = data.get("template_body")
    object_name = data.get("selected_object")
    record_ids = data.get("record_ids", [])

    user_id = kwargs.get('user_', {}).get('id')
    try:
        if not user_id or not subject or not body:
            return {"error": "Fields 'user_id', 'to', 'subject', 'body' are required"}
        grant_row = run_query(
            """
            SELECT grant_id, email
            FROM public.users
            WHERE id = %s
            """,
            [user_id],
            fetch_one=True,
        )
        if not grant_row.get("grand_id"):
            config = URLForAuthenticationConfig({
                "client_id": settings.NYLAS_CLIENT_ID,
                "redirect_uri": "http://localhost:8000/v2/nylas/call-back",
                "state": str(user_id)
            })
            auth_url = nylas.auth.url_for_oauth2(config)
            return{
                    "error": "Email not connected for this user",
                    "need_connect": True,
                    "auth_url": auth_url,
                }
        for record_id in record_ids:
            record_data = get_record_from_sql(object_name.lower(), record_id)
            recipient_email = record_data.get("email")
            subject = replace_merge_fields(subject, object_name, record_data)
            body = replace_merge_fields(body, object_name, record_data)
            grant_id = grant_row["grant_id"]
            from_email = grant_row["email"]
            result = compose_mail(grant_id=grant_id,body=body,subject=subject,from_email=from_email,to_email=recipient_email)
            if "error" in result:
                raise Exception("Send email failed")
        return 
    except Exception as er:
        return {"data":[],"error":True,"message":str(er)}

    

