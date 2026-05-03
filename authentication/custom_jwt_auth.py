import jwt
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.authentication import BaseAuthentication
from django.conf import settings

class CustomJWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        """Custom authentication logic to validate JWT"""
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise AuthenticationFailed("No authentication token provided")
        token = auth_header.split(" ")[1]

        try:
            # Decode the JWT token using the shared secret
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,  # The same secret key used in the Auth service
                algorithms=["HS256"],     # Expecting HS256 algorithm
                options={"verify_aud": False},  # Optional: disable audience verification
            )
            # Create a custom user object based on the JWT payload
            user = CustomUser(
                id=payload.get("id") or payload.get("user_id"),
                schema_name=payload.get("schema_name"),
                domain=payload.get("domain"),
                username=payload.get("username") or payload.get("email", ""),
                email=payload.get("email", ""),
            )          

        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("Token has expired")
        except jwt.InvalidTokenError:
            raise AuthenticationFailed("Invalid token")
        return (user, token)  # Return user info and None for auth credentials
    
    



# Define a simple custom User-like object to hold user-related info
class CustomUser:
    def __init__(self, id, schema_name, domain, username, email):
        self.id = id
        self.schema_name = schema_name
        self.domain = domain
        self.username = username
        self.email = email

    def __str__(self):
        return f"User({self.username}, {self.email})"

    # Optionally, you can add more methods to mimic a user object
    def get_full_name(self):
        return self.username

    def get_email(self):
        return self.email

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False