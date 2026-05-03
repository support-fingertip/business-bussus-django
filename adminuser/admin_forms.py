from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class UsernameAdminAuthenticationForm(AdminAuthenticationForm):
    username = forms.CharField(label=_("Username"), max_length=254)

    error_messages = {
        **AdminAuthenticationForm.error_messages,
        "invalid_login": _(
            "Please enter the correct username and password for a staff "
            "account. Note that both fields may be case-sensitive."
        ),
    }

    def get_invalid_login_error(self):
        return ValidationError(
            self.error_messages["invalid_login"],
            code="invalid_login",
            params={"username": "username"},
        )

    def clean(self):
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if username and password:
            User = get_user_model()
            user_obj = User.objects.filter(username=username).first()
            if user_obj is None:
                raise self.get_invalid_login_error()

            self.user_cache = authenticate(
                self.request,
                username=getattr(user_obj, User.USERNAME_FIELD),
                password=password,
            )
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data
