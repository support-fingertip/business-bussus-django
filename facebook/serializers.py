from rest_framework import serializers
from .models import FacebookLead

class FacebookLeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = FacebookLead
        fields = '__all__'
