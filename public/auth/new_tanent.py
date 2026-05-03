from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework.views import APIView
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework.permissions import AllowAny

from public.utils.organisation import create_new_tenant

@method_decorator(csrf_exempt, name='dispatch')
class CreateTenantView(APIView):
    authentication_classes = []  # No authentication for this view
    permission_classes = [AllowAny]  # Allow any user to access this view
    def post(self, request, *args, **kwargs):
        # Get data from request (can be JSON or form data)
        payload = request.data  # Assuming the payload is sent in the request body
        organization_name = request.data.get('organization_name')  # Get from form or request body
        username = request.data.get('username')
        password = request.data.get('password')

        if not organization_name or not username or not password:
            return JsonResponse({'error': 'Missing required fields'}, status=400)
        
        try:
            # Call the create_new_tenant function
            create_new_tenant(organization_name, username, password, payload)
            return JsonResponse({'message': f'Tenant "{organization_name}" created successfully'}, status=201)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
