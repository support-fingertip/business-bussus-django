from django import forms
from .models import SalesforceSettings

class SalesforceSettingsForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)  # Hide password

    class Meta:
        model = SalesforceSettings
        fields = ['username', 'password', 'client_id', 'client_secret', 'sync_enabled']
