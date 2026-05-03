from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework.permissions import AllowAny, IsAuthenticated
from api.serializers import UserRegistrationSerializer

@method_decorator(csrf_exempt, name='dispatch')  # Disable CSRF for simplicity
class UserRegistrationView(APIView):
    
    def get_permissions(self):
        """Set permissions dynamically for different actions."""
        if self.request.method == "POST":
            return [AllowAny()]  # No authentication needed for registration
        return [IsAuthenticated()]  # Authentication required for updates
    
    
    def post(self, request):
        """Handles user registration."""
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "User created successfully"}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request):
        """Handles updating user details (authenticated users only)."""
        user = request.user  # Gets the authenticated user
        serializer = UserRegistrationSerializer(user, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response({"message": "User updated successfully", "data": serializer.data}, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
