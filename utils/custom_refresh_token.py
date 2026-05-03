from rest_framework_simplejwt.tokens import RefreshToken

class CustomRefreshToken(RefreshToken):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_payload(self):
        # Get the original payload from the base RefreshToken
        payload = super().get_payload()

        # Add custom claims (user_id, organization_id) to the payload
        user_id = getattr(self.user, 'id', None)
        organization_id = getattr(self.user, 'organization_id', None)
        print(f"User ID: {user_id}, Organization ID: {organization_id}")
        # Add the custom claims to the payload
        if user_id:
            payload['user_id'] = user_id
        if organization_id:
            payload['organization_id'] = organization_id
        print(f"Custom Payload: {payload}")  # Debugging line to check the payload
        return payload
    
import jwt
from django.conf import settings
from jwt.exceptions import ExpiredSignatureError, DecodeError

def get_jwt_payload(token):
    try:
        # Decode the JWT token using the Django SECRET_KEY and the correct algorithm (HS256 by default)
        decoded_payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])

        # Return the decoded payload
        return decoded_payload
    except ExpiredSignatureError:
        # Handle case when the token is expired
        raise Exception("Token has expired")
    except DecodeError:
        # Handle errors in decoding the token (e.g., invalid signature)
        raise Exception("Error decoding the token")
    except Exception as e:
        # Handle any other exceptions
        raise Exception(f"An error occurred while decoding the token: {str(e)}")

