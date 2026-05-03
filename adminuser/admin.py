import uuid

from django import forms
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField

from adminuser.admin_forms import UsernameAdminAuthenticationForm
from adminuser import schema_admin  # noqa: F401  registers /admin/schemas/
from api.models import Organization

admin.site.login_form = UsernameAdminAuthenticationForm

User = get_user_model()


try:
    admin.site.unregister(Organization)
except admin.sites.NotRegistered:
    pass


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "database_schema", "is_active", "created_date")
    list_filter = ("is_active", "created_date")
    search_fields = ("id", "name", "database_schema")
    readonly_fields = ("id", "created_date")
    ordering = ("name",)
    fieldsets = (
        (None, {"fields": ("id", "name", "database_schema", "is_active")}),
        ("Branding", {"fields": ("logo",)}),
        ("Important dates", {"fields": ("created_date",)}),
    )


class UserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(
        label="Password confirmation", widget=forms.PasswordInput
    )

    class Meta:
        model = User
        fields = (
            "email",
            "username",
            "name",
            "first_name",
            "last_name",
            "phone",
            "company",
            "is_active",
            "is_staff",
            "is_superuser",
        )

    def clean_password2(self):
        p1 = self.cleaned_data.get("password1")
        p2 = self.cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Passwords don't match")
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        if not user.id:
            user.id = uuid.uuid4().hex[:10]
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class UserChangeForm(forms.ModelForm):
    password = ReadOnlyPasswordHashField(
        help_text=(
            "Raw passwords are not stored. Use the "
            '<a href="../password/">change password form</a> to set a new password.'
        )
    )

    class Meta:
        model = User
        fields = "__all__"


try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass


class CustomUserAdmin(UserAdmin):
    add_form = UserCreationForm
    form = UserChangeForm
    model = User

    list_display = ("username", "email", "name", "is_active", "is_staff", "is_superuser")
    list_filter = ("is_active", "is_staff", "is_superuser")
    search_fields = ("username", "email", "name", "first_name", "last_name")
    ordering = ("email",)
    readonly_fields = ("created_date", "last_modified_date", "last_login")

    fieldsets = (
        (None, {"fields": ("email", "username", "password")}),
        (
            "Personal info",
            {"fields": ("name", "first_name", "last_name", "phone", "company")},
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "created_date", "last_modified_date")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "username",
                    "name",
                    "first_name",
                    "last_name",
                    "phone",
                    "company",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "password1",
                    "password2",
                ),
            },
        ),
    )


admin.site.register(User, CustomUserAdmin)
