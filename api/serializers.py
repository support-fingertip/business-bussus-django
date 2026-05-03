from rest_framework import serializers
from .models import User

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, required=True)

    class Meta:
        model = User
        fields = ['email', 'name', 'username', 'phone', 'password', 'company']
        extra_kwargs = {'email': {'required': True}}  # Ensure email is mandatory

    def create(self, validated_data):
        """Creates a new user, ensuring password hashing."""
        password = validated_data.pop('password')
        user = User.objects.create_user(**validated_data)  # Uses CustomUserManager
        user.set_password(password)  # Hash the password
        user.save()
        return user

    def update(self, instance, validated_data):
        """Updates an existing user while ensuring password security."""
        password = validated_data.pop('password', None)
        if password:
            instance.set_password(password)  # Hash new password before saving

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        return instance


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['email', 'name', 'phone']  # Add required fields