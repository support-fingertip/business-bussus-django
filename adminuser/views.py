from rest_framework.permissions import BasePermission
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import connection, DatabaseError

from adminuser.services.organizations import OrganizationService
from adminuser.services.user import UserService

# Custom permission to allow only superusers
class IsSuperUser(BasePermission):
    def has_permission(self, request, view):
        # Check if the user is authenticated and is a superuser
        return request.user and request.user.is_authenticated and request.user.is_staff

class YourAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsSuperUser]

    def get(self, request, table, second=None, third=None):
        id = request.GET.get('id', None)           
        if table == 'organizations':   
            organizationservice = OrganizationService()   
            try:      
                if id:
                    result = organizationservice.get_organization(id)
                    cursor = connection.cursor()
                    schema_name = result.get('database_schema')
                    if schema_name:
                        cursor.execute(
                            "SELECT schema_name FROM information_schema.schemata WHERE schema_name = %s;",
                            [schema_name]
                        )
                        if not cursor.fetchone():
                            result['schema_exists'] = False
                            result['data_storage'] = 'N/A'
                        cursor.execute(
                            """
                            SELECT pg_size_pretty(SUM(pg_total_relation_size(pg_class.oid))) AS size
                            FROM pg_class
                            JOIN pg_namespace ON relnamespace = pg_namespace.oid
                            WHERE nspname = %s;
                            """,
                            [schema_name]
                        )
                        schema_size = cursor.fetchone()[0]
                        result['data_storage'] = schema_size if schema_size else '0 bytes'
                        result['schema_exists'] = True                    
                else:                
                    result = organizationservice.get_all_organizations(request.GET.get('search', None))
                return Response(result, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        elif second == 'users':
            userservice = UserService(table)
            try:
                if id:
                    result = userservice.get_user(id)
                else:
                    result = userservice.get_all_users(table)
                return Response(result, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        elif second == "profiles":
            userservice = UserService(table)
            try:
                result = userservice.get_profiles()
                return Response(result, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request, table, second=None, third=None):
        data = request.data
        
        if table == 'organizations' and not second:
            pass
        elif second == 'users':
            userservice = UserService(table)
            try:
                result = userservice.create_user(data)             
                return Response(status=201, data=result)
            except Exception as e:
                return Response(status=500, data={"error": str(e)})
            except DatabaseError as db_err:
                return Response(
                    status=500,
                    data={"error": "Database error occurred", "details": str(db_err)}
                )
    
    def patch(self, request, table, second=None, third=None):
        data = request.data
        if table == 'organizations' and not second:
            organizationservice = OrganizationService()
            try:
                if second is None:
                    pass
                    # result = organizationservice.update_organization(data)
                elif second == "freeze":
                    result = organizationservice.freeze_organization(data.get("id"))
                return Response(status=200, data=result)
            except Exception as e:
                return Response(status=500, data={"error": str(e)})
        elif second == 'users':
            userservice = UserService(table)
            try:
                if third == 'freeze':
                    result = userservice.freeze_user(data.get("id"))
                elif third == 'unfreeze':
                    result = userservice.unfreeze_user(data.get("id"))
                elif third == 'reset_password':
                    result = userservice.reset_password(data)
                elif third == 'make_admin':
                    result = userservice.make_admin(data.get("id"))
                elif third == 'remove_admin':
                    result = userservice.remove_admin(data.get("id"))
                elif third == 'update_email':
                    result = userservice.update_email(data)
                elif third is None:
                    result = userservice.update_user(data)
                return Response(status=200, data=result)
            except Exception as e:
                return Response(status=500, data={"error": str(e)})
            except DatabaseError as db_err:
                return Response(
                    status=500,
                    data={"error": "Database error occurred", "details": str(db_err)}
                )
        return Response(status=400, data={"error": "Invalid table or operation"})
    
    def delete(self, request, table, second=None, third=None):
        if second == 'users' and table:
            userservice = UserService(table)
            try:
                result = userservice.delete_user(third)
                return Response(status=200, data=result)
            except Exception as e:
                return Response(status=500, data={"error": str(e)})
            except DatabaseError as db_err:
                return Response(
                    status=500,
                    data={"error": "Database error occurred", "details": str(db_err)}
                )
        return Response(status=400, data={"error": "Invalid table or operation"})
            
