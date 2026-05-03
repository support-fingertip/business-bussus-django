from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST, HTTP_401_UNAUTHORIZED
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
import jwt
from django.conf import settings


class LogoutView(APIView):
    def post(self, request):
        try:
            auth_header = request.META.get("HTTP_AUTHORIZATION", "")
            if not auth_header or not auth_header.startswith("Bearer "):
                raise AuthenticationFailed("No authentication token provided")
            token = auth_header.split(" ", 1)[1].strip()
            try:
                refresh = RefreshToken(token)
                refresh.blacklist()
            except TokenError:
                return Response({'error': 'Only refresh tokens can be blacklisted.'}, status=HTTP_400_BAD_REQUEST)

            return Response({'message': 'Logout successful'}, status=HTTP_200_OK)
        except AuthenticationFailed as e:
            return Response({'error': str(e)}, status=HTTP_401_UNAUTHORIZED)
        except Exception:
            return Response({'error': 'Invalid request data.'}, status=HTTP_400_BAD_REQUEST)