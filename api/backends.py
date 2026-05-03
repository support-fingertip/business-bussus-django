from django.contrib.auth.backends import BaseBackend
from django.contrib.auth import get_user_model

class EmailBackend(BaseBackend):
    """
    Custom authentication backend to authenticate users using email and password.
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        # Fetch the custom User model
        User = get_user_model()

        # Attempt to find the user by email
        try:
            user = User.objects.get(email=username)  # 'username' will actually contain the email
        except User.DoesNotExist:
            return None

        # Verify the password
        if user.check_password(password):
            return user
        return None

    def get_user(self, user_id):
        # Fetch the user by ID
        User = get_user_model()
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
