import jwt
from django.conf import settings
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth import get_user_model

User = get_user_model()

class JWTAuthenticationMiddleware(MiddlewareMixin):
    """
    Middleware to validate JWT access tokens for all incoming requests.
    HS256 symmetric key is used to decode and verify tokens.
    """

    def process_request(self, request):
        # Skip authentication for public endpoints if needed
        if request.path.startswith("/public/"):
            return None

        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JsonResponse({"detail": "Authorization header missing or invalid"}, status=401)

        token = auth_header.split(" ")[1]

        try:
            # Decode token using the same secret key from Auth service
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,  # MUST be the same secret used to sign the token
                algorithms=["HS256"],     # HS256 symmetric algorithm
                options={"verify_aud": False},  # Set True if you want audience validation
            )
            
            print(f"JWT payload: {payload}")  # Debugging line to check payload contents

            # Attach user info to request for later use in views
            request.user_id = payload.get("id")
            request.username = payload.get("username")
            request.name = payload.get("name")
            request.email = payload.get("email")
            request.org_id = payload.get("org_id")

            # Optionally: fetch user object from local DB if you maintain a users table
            try:
                request.user = User.objects.get(id=request.user_id)
            except User.DoesNotExist:
                # If no local user table, you can just skip or create a lightweight User object
                request.user = None

        except jwt.ExpiredSignatureError:
            return JsonResponse({"detail": "Token has expired"}, status=401)
        except jwt.InvalidTokenError:
            return JsonResponse({"detail": "Invalid token"}, status=401)
        
        print(f"Authenticated request for user_id: {request.user_id}, username: {request.username}")

        # Continue to the view
        return None
