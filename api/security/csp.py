"""Content-Security-Policy middleware — Phase C7.

In plain English
----------------

A Content-Security-Policy (CSP) header tells the browser what a page
is allowed to do — which scripts may run, where it may connect, etc.
If a stored-XSS payload ever lands in CRM data and gets rendered,
a strict CSP stops the injected script from actually executing or
phoning home.

Why a tiny middleware instead of `django-csp`
---------------------------------------------

`django-csp` is a fine library, but it's another dependency to vet
and pin. For a backend that mostly serves JSON (CSP matters here for
the Django admin and any HTML error pages), a ~40-line middleware is
simpler and has zero new dependencies.

Report-only by default — this is deliberate
-------------------------------------------

A too-strict CSP silently breaks pages. So this middleware ships the
header as ``Content-Security-Policy-Report-Only`` unless ``CSP_ENFORCE``
is set. In report-only mode the browser does NOT block anything — it
just reports what *would* have been blocked. The rollout is:

  1. Deploy with ``CSP_ENFORCE`` unset (report-only). Nothing breaks.
  2. Watch the violation reports for a week (Sentry / a report
     endpoint). Tighten the policy to cover the real legitimate
     sources.
  3. Set ``CSP_ENFORCE=1``. Now the browser actually blocks.

The frontend SPA has its OWN CSP concern — this header protects the
backend's HTML surface (admin, error pages), not the SPA.
"""

from __future__ import annotations

import os

from django.utils.deprecation import MiddlewareMixin


def _build_policy() -> str:
    """Assemble the CSP directive string.

    Conservative defaults suitable for an API backend + Django admin:
      * default-src 'self'        — only same-origin by default
      * script-src 'self'         — no inline scripts, no external JS
      * style-src 'self' 'unsafe-inline' — Django admin uses inline styles
      * img-src 'self' data:      — admin + data-URI images
      * frame-ancestors 'none'    — reinforces X-Frame-Options: DENY
      * base-uri 'self'           — blocks <base> tag hijacking
      * object-src 'none'         — no Flash/Java/embeds
      * form-action 'self'        — forms can only post same-origin

    Override the whole string via the CSP_POLICY env var if the
    backend ever needs to load an external resource.
    """
    override = os.getenv("CSP_POLICY", "").strip()
    if override:
        return override
    return "; ".join([
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "object-src 'none'",
        "form-action 'self'",
    ])


class ContentSecurityPolicyMiddleware(MiddlewareMixin):
    """Attach a CSP header to every response.

    Report-only unless ``CSP_ENFORCE`` is truthy. Optionally appends
    a ``report-uri`` if ``CSP_REPORT_URI`` is set so violations are
    collected centrally.
    """

    def process_response(self, request, response):
        policy = _build_policy()

        report_uri = os.getenv("CSP_REPORT_URI", "").strip()
        if report_uri:
            policy = f"{policy}; report-uri {report_uri}"

        enforce = os.getenv("CSP_ENFORCE", "0") == "1"
        header = (
            "Content-Security-Policy"
            if enforce
            else "Content-Security-Policy-Report-Only"
        )

        # Don't overwrite a CSP a view set deliberately.
        if "Content-Security-Policy" not in response and \
                "Content-Security-Policy-Report-Only" not in response:
            response[header] = policy

        return response
