
from django.db import connection
from django.contrib.auth.hashers import make_password
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.status import HTTP_200_OK, HTTP_400_BAD_REQUEST
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import AllowAny

@method_decorator(csrf_exempt, name='dispatch')
class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]
    
    def post(self, request, *args, **kwargs):
        try:
            data = request.data
            email = data.get('email')
            new_password = data.get('new_password')
            confirm_password = data.get('confirm_password')

            if not email or not new_password or not confirm_password:
                return Response({'error': 'Missing required fields.'}, status=HTTP_400_BAD_REQUEST)

            if new_password != confirm_password:
                return Response({'error': 'Passwords do not match.'}, status=HTTP_400_BAD_REQUEST)

            with connection.cursor() as cursor:
                # Check if user exists
                cursor.execute("SELECT id, email FROM users WHERE email = %s", [email])
                row = cursor.fetchone()
                if not row:
                    return Response({'error': 'User with this email does not exist.'}, status=HTTP_400_BAD_REQUEST)

                user_id, user_email = row

                # Hash the password
                hashed_password = make_password(new_password)

                # Update password
                cursor.execute("UPDATE users SET password = %s WHERE id = %s", [hashed_password, user_id])

            # You can fetch user object to pass to log_audit, or pass `user_id` if log_audit allows it
            # log_audit(
            #     user_id=user_id,
            #     action=f"User {user_email} reset their password successfully.",
            #     section="Password Reset",
            #     prefix="USER"
            # )

            return Response({'message': 'Password reset successful.'}, status=HTTP_200_OK)

        except Exception as e:
            return Response({'error': f'Unexpected error: {str(e)}'}, status=HTTP_400_BAD_REQUEST)
