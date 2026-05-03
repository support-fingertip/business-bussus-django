from rest_framework import serializers
from .models import SalesforceSync

class SalesforceSyncSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesforceSync
        fields = '__all__'  # Include all fields
