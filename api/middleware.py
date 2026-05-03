from django.urls import resolve

class ExemptAuthMiddleware:
    """
    Middleware to exempt certain routes from authentication.
    """
    EXEMPT_ROUTES = [
        
        'auth_signup',
        'auth_logout',
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        match = resolve(request.path)
        if match.url_name in self.EXEMPT_ROUTES:
            request._dont_enforce_csrf_checks = True
            return self.get_response(request)
        return self.get_response(request)
    

