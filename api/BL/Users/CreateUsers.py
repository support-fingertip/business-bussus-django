# import os
# import uuid
# from api.BL.utils import encryptPassword
# from api.ORM.sqlFunctions.createSQLFunction import post_data_sql
# from api.ORM.sqlFunctions.deleteSQLFunction import delete_data_sql
# from api.ORM.sqlFunctions.updateSQLFunction import updateRawSQL
# from api.permissions.permissions import delete_permission, get_permissions, patch_permission, post_permission
# from django.contrib.auth.hashers import make_password
# from django.db import connection
# import requests
# from django.utils import timezone

# class UserBussinessLogic:
#     def __init__(self, request, **kwargs):
#         self.request = request
#         self.kwargs = kwargs
    
#     def get_me(self):
#         try:
#             filter = [{"field": "id", "operator":"=", "value": self.kwargs.get('user_', {}).get('id')}]
#             result = get_permissions(self.request, tableName='users', fields=['name', 'username', 'email', 'first_name', 'last_name', 'phone', 'profile_id', 'profile.name', 'profile.profile_type', 'organization_id', 'company', 'created_date', 'last_modified_date', 'timezone', 'locale', 'is_staff', 'is_superuser', 'is_active', 'manager_id', 'manager.name', 'manager.id'], where=filter, **self.kwargs).get('data', [])[0]
#             return {
#                 **result,
#                 "is_setup": True if result.get('profile', {}).get('profile_type') == 'admin' else False
#             }
#         except Exception as e:
#             print(str(e))
#             raise Exception(f"str(e)")
    
#     def get_all_users(self):        
#         try:
#             filter = [{"field":"organization_id", "operator":"=", "value": self.kwargs.get('org', {}).get('id')}]
#             users = get_permissions(self.request, tableName='users', fields=['name', 'username', 'email', 'first_name', 'last_name', 'phone', 'profile_id', 'profile.name', 'profile.profile_type', 'organization_id', 'company','is_active'], where=filter, setup_check = False, **self.kwargs).get('data', [])
#             return users
#         except Exception as e:
#             raise Exception(f"Error fetching users: {str(e)}")
        
#     def get_user_by_id(self, user_id):
#         try:
#             filter = [{"field": "id", "operator": "equals", "value": user_id}]
#             return get_permissions(self.request, tableName='users', where=filter, fields=['name', 'username', 'email', 'first_name', 'last_name', 'phone', 'profile_id', 'profile.name', 'profile.profile_type', 'organization_id', 'created_date', 'last_modified_date', 'timezone', 'locale', 'is_staff', 'is_superuser', 'is_active', 'manager_id', 'manager.name', 'manager.id'], **self.kwargs).get('data', [])
#         except Exception as e:
#             raise Exception(f"Error fetching user by ID: {str(e)}")
#     def create_user(self, user_data):
#         try:
#             first_name = user_data.get('first_name', '')
#             last_name = user_data.get('last_name', '')
#             name = user_data.get('name', first_name + ' ' + last_name).strip()
#             email = user_data.get('email', '')
#             if not email and name:
#                 raise Exception("Email is required to create a user.")
#             locale = user_data.get('locale', 'DD-MM-YYYY')
#             timezone = user_data.get('timezone', 'Asia/Kolkata')
#             phone = user_data.get('phone', '')
#             username = user_data.get('username', email.split('@')[0] if email else '')
#             is_email_verified = False
#             password = user_data.get('password')  # In real scenarios, ensure to hash passwords and follow security best practices.
#             organization_id = self.kwargs.get('org', {}).get('id')
#             profile_id = user_data.get("profile_id")
#             manager_id = user_data.get("manager_id")
#             if not profile_id:
#                 raise Exception("Profile is required to create a user.")
#             try:
#                 res = CreateNewUserInControlPanel({
#                     **user_data,
#                     'organization_id': organization_id,
#                 })
#                 if not res['ok']:
#                     if 'error' not in res:
#                         raise Exception("Unknown error occurred while creating user in control panel.")
#                     raise Exception(res['error'][0])  # Ensure 'error' is in the response if not ok

#                 id = res['user_id']  # Access 'user_id' from the response dictionary

#             except Exception as e:
#                 raise Exception(str(e))
#                 # print(f"Error creating user in control panel: {str(e)}")
#                 # raise Exception(f"USERNAME ALREADY EXISTS")  # Improved error handling

#             new_user_data = {
#                 'id': id,
#                 'name': name,
#                 'username': username,
#                 'email': email.lower(),
#                 'first_name': first_name,
#                 'last_name': last_name,
#                 'phone': phone,
#                 'locale': locale,
#                 'timezone': timezone,
#                 'is_email_verified': is_email_verified,
#                 'password': make_password(password, hasher='pbkdf2_sha256'),
#                 'organization_id': organization_id,
#                 'profile_id': profile_id,
#                 'is_active': True,
#                 'company': self.kwargs.get('org', {}).get('name', ''),
#             }
#             if manager_id:
#                 new_user_data['manager_id'] = manager_id
#             result = post_permission(self.request, table_name='users', create_data=new_user_data, setup_check=True, **self.kwargs)
#             if self.kwargs.get('schema') != 'public':
#                 self.kwargs['schema'] = 'public'
#                 post_data_sql('users', new_user_data, **self.kwargs)  
#             print("New user created with ID:", result)             
#             return result
#         except Exception as e:
#             print(f"Error creating user: {str(e)}")
#             raise Exception(f"Error creating user: {str(e)}")
        
#     def update_user_by_himself(self, update_data):
#         try:
#             id = update_data.get('id')
#             if not id:
#                 raise Exception("User details is required to update user.")

#             name = update_data.get('name', '')
#             first_name = update_data.get('first_name', '')
#             last_name = update_data.get('last_name', '')
#             phone = update_data.get('phone', '')
#             username = update_data.get('username')
#             email = update_data.get('email')

#             new_updated_data = {'id': id}

#             if name:
#                 new_updated_data['name'] = name
#             if first_name:
#                 new_updated_data['first_name'] = first_name
#             if last_name:
#                 new_updated_data['last_name'] = last_name
#             if phone:
#                 # filter = [{"field": "phone", "operator": "=", "value": phone}]
#                 # existing = get_permissions(
#                 #     self.request,
#                 #     tableName='users',
#                 #     where=filter,
#                 #     fields=['id'],
#                 #     setup_check=False,
#                 #     **self.kwargs
#                 # ).get('data', [])
#                 # conflict = next((user for user in existing if user.get('id') != id), None)
#                 # if conflict:
#                 #     raise Exception("Phone number already exists.")
#                 new_updated_data['phone'] = phone
#             if email:
#                 new_updated_data['email'] = email
#                 # Always sync username with email
#                 new_updated_data['username'] = email

#             # If username explicitly provided separately, use it (and validate uniqueness)
#             if username:
#                 filter = [{"field": "username", "operator": "=", "value": username}]
#                 existing = get_permissions(
#                     self.request,
#                     tableName='users',
#                     where=filter,
#                     fields=['id'],
#                     setup_check=False,
#                     **self.kwargs
#                 ).get('data', [])
#                 conflict = next((user for user in existing if user.get('id') != id), None)
#                 if conflict:
#                     raise Exception("Username already exists.")
#                 new_updated_data['username'] = username

#             response = update_details_in_control_panel(
#                 id,
#                 new_updated_data,
#                 self.request.headers.get('Authorization').split(' ')[1]
#             )

#             if not response['ok']:
#                 if isinstance(response.get('error'), list):
#                     raise Exception(response['error'][0])
#                 else:
#                     raise Exception(response.get('error'))

#             update_data['last_modified_date'] = timezone.now()
#             updated_user = patch_permission(
#                 self.request,
#                 'users',
#                 update_data=new_updated_data,
#                 setup_check=False,
#                 **self.kwargs
#             )

#             if self.kwargs['schema'] != 'public':
#                 self.kwargs['schema'] = 'public'
#                 updateRawSQL('users', update_data=new_updated_data, **self.kwargs)

#             return updated_user

#         except Exception as e:
#             raise Exception(str(e))    
#     def update_user_by_admin(self, update_data):
#         try:
#             id = update_data.get('id')
#             if not id:
#                 raise Exception("User details are required to update the user.")
#             print("Update data received:", update_data)
            
#             # Initialize new_updated_data with the mandatory id field
#             new_updated_data = {'id': id}

#             # List of fields to potentially update
#             fields = ['name', 'first_name', 'last_name', 'phone', 'username', 'profile_id', 'is_active', 'manager_id', 'timezone', 'locale','email']

#             # Check for duplicate username before updating
#             username = update_data.get('username')
#             if username:
#                 filter = [{"field": "username", "operator": "=", "value": username}]
#                 existing = get_permissions(
#                     self.request,
#                     tableName='users',
#                     where=filter,
#                     fields=['id'],
#                     setup_check=False,
#                     **self.kwargs
#                 ).get('data', [])
#                 conflict = next((user for user in existing if user.get('id') != id), None)
#                 if conflict:
#                     raise Exception("Username already exists.")

#             # Loop through the fields and add them to new_updated_data if present
#             for field in fields:
#                 value = update_data.get(field)
#                 if value is not None:  # Exclude None or missing fields
#                     new_updated_data[field] = value
#             if new_updated_data.get('phone'):
#                 filter = [{"field": "phone", "operator": "=", "value": new_updated_data['phone']}]
#                 existing = get_permissions(
#                     self.request,
#                     tableName='users',
#                     where=filter,
#                     fields=['id'],
#                     setup_check=False,
#                     **self.kwargs
#                 ).get('data', [])
#                 conflict = next((user for user in existing if user.get('id') != id), None)
#                 if conflict:
#                     raise Exception("Phone number already exists.")

#             # Special logic for password
#             password = update_data.get('password')
#             if password:
#                 new_updated_data['password'] = make_password(password, hasher='pbkdf2_sha256')

#             # Handle superuser and manager assignment rules
#             if 'manager_id' in new_updated_data and id == new_updated_data['manager_id']:
#                 raise Exception("User cannot be assigned as their own manager.")
            
#             is_superuser = self.check_super_user(id, **self.kwargs)
#             if is_superuser and 'profile_id' in new_updated_data:
#                 raise Exception("Superuser profile cannot be changed.")

#             if update_data.get('purpose') and update_data['purpose'] == 'status':
#                 url = f"{os.getenv('CPANEL_API_URL')}/auth/user/status/"
#                 encrypted = encryptPassword(update_data['id'])
#                 payload = {
#                     "user_id": encrypted,  
#                 }
#                 response = requests.post(url, json=payload,headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.request.headers.get('Authorization').split(' ')[1]}"})
#                 if response.status_code != 200:
#                     raise Exception(f"Failed to update user status in control panel: {response.text}")
#             # Update the user
#             response = update_details_in_control_panel(
#                 id,
#                 new_updated_data,
#                 self.request.headers.get('Authorization').split(' ')[1]
#             )
#             print("Control Panel update response:", response)

#             if not response['ok']:
#                 if isinstance(response.get('error'), list):
#                     raise Exception(response['error'][0])
#                 else:
#                     raise Exception(response.get('error'))
#             updated_user = patch_permission(self.request, 'users', update_data=new_updated_data, setup_check=True, **self.kwargs)
            
#             if self.kwargs['schema'] != 'public':
#                 self.kwargs['schema'] = 'public'
#                 updateRawSQL('users', update_data=new_updated_data, **self.kwargs)
#             return updated_user
#         except Exception as e:
#             raise Exception(f"{str(e)}")

#     def delete_user(self, user_id):
#         try:
#             if not user_id:
#                 raise Exception("User details is required to delete user.")
#             if isinstance(user_id, str):
#                 ids = [user_id]
#             elif isinstance(user_id, list):
#                 ids = user_id
#             if not ids:
#                 raise Exception("Please provide valid delete to delete.")
#             result = delete_permission(self.request, 'users', ids=ids, setup_check=True, **self.kwargs)
#             if self.kwargs['schema'] != 'public':
#                 self.kwargs['schema'] = 'public'
#                 delete_data_sql('users', ids, **self.kwargs)
#             return result
#         except Exception as e:
#             raise Exception(f"Error deleting user: {str(e)}")
        
#     def check_super_user(self, user_id, **kwargs):
#         try:
#             filter = [{"field": "id", "operator": "=", "value": user_id}]
#             user = get_permissions(self.request, tableName='users', where=filter, fields=['is_superuser'], setup_check=False, **kwargs).get('data', [])
#             print("USer detail",user)
#             if user and user[0].get('is_superuser'):
#                 return True
#             return False
#         except Exception as e:
#             raise Exception(f"Error checking superuser status: {str(e)}")
        

# import requests

# def CreateNewUserInControlPanel(payload):
#     try:
#         result = requests.post(
#             f"{os.getenv('CPANEL_API_URL')}/auth/register/n910nxryka/",
#             json={
#                 "username": payload['username'],
#                 "email": payload['email'],
#                 "name": payload.get('name'),
#                 "phone": payload['phone'],
#                 "password": payload["password"],
#                 "organization": payload['organization_id'],
#                 "is_active": True,
#                 "is_superuser": False
#             }
#         )
#         print("Control Panel Response:", result.status_code, result.text)
#         print("response json:", result.json())
#         if result.status_code == 201:  # HTTP 201 means success
#             response_data = result.json()  # Parse JSON response
#             user_id = response_data.get("id")  # Get 'id' from the response
#             return {'ok': True, 'user_id': user_id}  # Return user_id along with success status
#         else:
#             return {'ok': False, 'error': result.json()}  # Include error details if any
            
#     except Exception as e:
#         raise Exception(f"An error occurred: {str(e)}")
    
# def update_details_in_control_panel(user_id, payload, auth_token):
#     try:
#         payload = payload.copy()
#         payload['id'] =encryptPassword(user_id)
#         result = requests.post(
#             f"{os.getenv('CPANEL_API_URL')}/auth/user/update-user-details/",
#             json=payload,
#             headers={"Authorization": f"Bearer {auth_token}"}
#         )
#         if result.status_code == 200: 
#             return {'ok': True}
#         else:
#             return {'ok': False, 'error': result.json()}  
            
#     except Exception as e:
#         raise Exception(f"An error occurred: {str(e)}")


        
    

from asyncio.log import logger
import datetime
import os
import uuid
from api.BL.utils import encryptPassword
from api.ORM.sqlFunctions.createSQLFunction import post_data_sql
from api.ORM.sqlFunctions.deleteSQLFunction import delete_data_sql
from api.ORM.sqlFunctions.updateSQLFunction import updateRawSQL
from api.permissions.permissions import delete_permission, get_permissions, patch_permission, post_permission
from django.contrib.auth.hashers import make_password
from django.db import connection
import requests
from django.utils import timezone
from api.notifications.notify import trigger_notication
from channels.layers import get_channel_layer
from datetime import datetime


class UserBussinessLogic:
    def __init__(self, request, **kwargs):
        self.request = request
        self.kwargs = kwargs
    
    def get_me(self):
        try:
            filter = [{"field": "id", "operator":"=", "value": self.kwargs.get('user_', {}).get('id')}]
            result = get_permissions(self.request, tableName='users', fields=['name', 'username', 'email', 'first_name', 'last_name', 'phone', 'profile_id', 'profile.name', 'profile.profile_type', 'organization_id', 'company', 'created_date', 'last_modified_date', 'timezone', 'locale', 'is_staff', 'is_superuser', 'is_active', 'manager_id', 'manager.name', 'manager.id'], where=filter, **self.kwargs).get('data', [])[0]
            try:
                if self.request.GET.get('purpose') and self.request.GET.get('purpose') == 'login':
                    if not result.get('is_superuser'):
                        channel = get_channel_layer()
                        org_admin = get_permissions(
                            self.request,
                            tableName='users',
                            where=[
                                {"field": "organization_id", "operator": "=", "value": self.kwargs.get('org', {}).get('id')},
                            {"field": "is_superuser", "operator": "=", "value": True},
                        ],
                        fields=['id'],
                        **self.kwargs,
                        ).get('data', [])
                        org_admin = org_admin[0]['id'] if org_admin else None
                        self.kwargs["message"] = f"{result.get('name', '').capitalize()} is logged in",
                        trigger_notication(
                        owner_id=org_admin,
                        channel_layer=channel,
                        title="Login alert",
                        notification_type='alert',
                        user_id=self.kwargs.get('user_', {}).get('id'),
                        channel='push',
                        request=self.request,
                        **self.kwargs
                        )
            except Exception as e:
                logger.error(f"Error sending login notification: {str(e)}")
            app = get_permissions(
                self.request,
                tableName='app',
                where=[{"field": "name", "operator": "=", "value": "sales"}],
                **self.kwargs,
            ).get('data', [])
            default_app= app[0] if app else None
            return {    
                **result,
                "is_setup": True if result.get('profile', {}).get('profile_type') == 'admin' else False,
                "app": default_app
            }
        except Exception as e:
            print(str(e))
            raise Exception(f"str(e)")
    
    def get_all_users(self):        
        try:
            filter = [{"field":"organization_id", "operator":"=", "value": self.kwargs.get('org', {}).get('id')}]
            users = get_permissions(self.request, tableName='users', fields=['name', 'username', 'email', 'first_name', 'last_name', 'phone', 'profile_id', 'profile.name', 'profile.profile_type', 'organization_id', 'company','is_active'], where=filter, setup_check = False, **self.kwargs).get('data', [])
            return users
        except Exception as e:
            raise Exception(f"Error fetching users: {str(e)}")
        
    def get_user_by_id(self, user_id):
        try:
            filter = [{"field": "id", "operator": "equals", "value": user_id}]
            return get_permissions(self.request, tableName='users', where=filter, fields=['name', 'username', 'email', 'first_name', 'last_name', 'phone', 'profile_id', 'profile.name', 'profile.profile_type', 'organization_id', 'created_date', 'last_modified_date', 'timezone', 'locale', 'is_staff', 'is_superuser', 'is_active', 'manager_id', 'manager.name', 'manager.id'], **self.kwargs).get('data', [])
        except Exception as e:
            raise Exception(f"Error fetching user by ID: {str(e)}")
    def create_user(self, user_data):
        try:
            first_name = user_data.get('first_name', '')
            last_name = user_data.get('last_name', '')
            name = user_data.get('name', first_name + ' ' + last_name).strip()
            email = user_data.get('email', '')
            if not email and name:
                raise Exception("Email is required to create a user.")
            locale = user_data.get('locale', 'DD-MM-YYYY')
            timezone = user_data.get('timezone', 'Asia/Kolkata')
            phone = user_data.get('phone', '')
            username = user_data.get('username', email.split('@')[0] if email else '')
            is_email_verified = False
            password = user_data.get('password')  # In real scenarios, ensure to hash passwords and follow security best practices.
            organization_id = self.kwargs.get('org', {}).get('id')
            profile_id = user_data.get("profile_id")
            manager_id = user_data.get("manager_id")
            if not profile_id:
                raise Exception("Profile is required to create a user.")
            try:
                res = CreateNewUserInControlPanel({
                    **user_data,
                    'organization_id': organization_id,
                })
                if not res['ok']:
                    if 'error' not in res:
                        raise Exception("Unknown error occurred while creating user in control panel.")
                    raise Exception(res['error'][0])  # Ensure 'error' is in the response if not ok

                id = res['user_id']  # Access 'user_id' from the response dictionary

            except Exception as e:
                raise Exception(str(e))
                # print(f"Error creating user in control panel: {str(e)}")
                # raise Exception(f"USERNAME ALREADY EXISTS")  # Improved error handling

            new_user_data = {
                'id': id,
                'name': name,
                'username': username,
                'email': email.lower(),
                'first_name': first_name,
                'last_name': last_name,
                'phone': phone,
                'locale': locale,
                'timezone': timezone,
                'is_email_verified': is_email_verified,
                'password': make_password(password, hasher='pbkdf2_sha256'),
                'organization_id': organization_id,
                'profile_id': profile_id,
                'is_active': user_data.get('is_active', True),
                'company': self.kwargs.get('org', {}).get('name', ''),
            }
            if manager_id:
                new_user_data['manager_id'] = manager_id
            result = post_permission(self.request, table_name='users', create_data=new_user_data, setup_check=True, **self.kwargs)
            if self.get_validated_schema(kwargs) != 'public':
                self.kwargs['schema'] = 'public'
                post_data_sql('users', new_user_data, **self.kwargs)  
            print("New user created with ID:", result)             
            return result
        except Exception as e:
            print(f"Error creating user: {str(e)}")
            raise Exception(f"Error creating user: {str(e)}")
        
    def update_user_by_himself(self, update_data):
        try:
            id = update_data.get('id')
            if not id:
                raise Exception("User details is required to update user.")

            name = update_data.get('name', '')
            first_name = update_data.get('first_name', '')
            last_name = update_data.get('last_name', '')
            phone = update_data.get('phone', '')
            username = update_data.get('username')
            email = update_data.get('email')

            new_updated_data = {'id': id}

            if name:
                new_updated_data['name'] = name
            if first_name:
                new_updated_data['first_name'] = first_name
            if last_name:
                new_updated_data['last_name'] = last_name
            if phone:
                # filter = [{"field": "phone", "operator": "=", "value": phone}]
                # existing = get_permissions(
                #     self.request,
                #     tableName='users',
                #     where=filter,
                #     fields=['id'],
                #     setup_check=False,
                #     **self.kwargs
                # ).get('data', [])
                # conflict = next((user for user in existing if user.get('id') != id), None)
                # if conflict:
                #     raise Exception("Phone number already exists.")
                new_updated_data['phone'] = phone
            if email:
                new_updated_data['email'] = email
                # Always sync username with email
                new_updated_data['username'] = email

            # If username explicitly provided separately, use it (and validate uniqueness)
            if username:
                filter = [{"field": "username", "operator": "=", "value": username}]
                existing = get_permissions(
                    self.request,
                    tableName='users',
                    where=filter,
                    fields=['id'],
                    setup_check=False,
                    **self.kwargs
                ).get('data', [])
                conflict = next((user for user in existing if user.get('id') != id), None)
                if conflict:
                    raise Exception("Username already exists.")
                new_updated_data['username'] = username

            response = update_details_in_control_panel(
                id,
                new_updated_data,
                self.request.headers.get('Authorization').split(' ')[1]
            )

            if not response['ok']:
                if isinstance(response.get('error'), list):
                    raise Exception(response['error'][0])
                else:
                    raise Exception(response.get('error'))

            update_data['last_modified_date'] = timezone.now()
            updated_user = patch_permission(
                self.request,
                'users',
                update_data=new_updated_data,
                setup_check=False,
                **self.kwargs
            )

            if self.kwargs['schema'] != 'public':
                self.kwargs['schema'] = 'public'
                updateRawSQL('users', update_data=new_updated_data, **self.kwargs)

            return updated_user

        except Exception as e:
            raise Exception(str(e))    
    def update_user_by_admin(self, update_data):
        try:
            id = update_data.get('id')
            if not id:
                raise Exception("User details are required to update the user.")
            print("Update data received:", update_data)
            
            # Initialize new_updated_data with the mandatory id field
            new_updated_data = {'id': id}

            # List of fields to potentially update
            fields = ['name', 'first_name', 'last_name', 'phone', 'username', 'profile_id', 'is_active', 'manager_id', 'timezone', 'locale','email']

            # Check for duplicate username before updating
            username = update_data.get('username')
            if username:
                filter = [{"field": "username", "operator": "=", "value": username}]
                existing = get_permissions(
                    self.request,
                    tableName='users',
                    where=filter,
                    fields=['id'],
                    setup_check=False,
                    **self.kwargs
                ).get('data', [])
                conflict = next((user for user in existing if user.get('id') != id), None)
                if conflict:
                    raise Exception("Username already exists.")

            # Loop through the fields and add them to new_updated_data if present
            for field in fields:
                value = update_data.get(field)
                if value is not None:  # Exclude None or missing fields
                    new_updated_data[field] = value
            if new_updated_data.get('phone'):
                filter = [{"field": "phone", "operator": "=", "value": new_updated_data['phone']}]
                existing = get_permissions(
                    self.request,
                    tableName='users',
                    where=filter,
                    fields=['id'],
                    setup_check=False,
                    **self.kwargs
                ).get('data', [])
                conflict = next((user for user in existing if user.get('id') != id), None)
                if conflict:
                    raise Exception("Phone number already exists.")

            # Special logic for password
            password = update_data.get('password')
            if password:
                new_updated_data['password'] = make_password(password, hasher='pbkdf2_sha256')

            # Handle superuser and manager assignment rules
            if 'manager_id' in new_updated_data and id == new_updated_data['manager_id']:
                raise Exception("User cannot be assigned as their own manager.")
            
            is_superuser = self.check_super_user(id, **self.kwargs)
            if is_superuser and 'profile_id' in new_updated_data:
                raise Exception("Superuser profile cannot be changed.")

            if update_data.get('purpose') and update_data['purpose'] == 'status':
                url = f"{os.getenv('CPANEL_API_URL')}/auth/user/status/"
                encrypted = encryptPassword(update_data['id'])
                payload = {
                    "user_id": encrypted,  
                }
                response = requests.post(url, json=payload,headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.request.headers.get('Authorization').split(' ')[1]}"})
                if response.status_code != 200:
                    raise Exception(f"Failed to update user status in control panel: {response.text}")
            # Update the user
            response = update_details_in_control_panel(
                id,
                new_updated_data,
                self.request.headers.get('Authorization').split(' ')[1]
            )
            print("Control Panel update response:", response)

            if not response['ok']:
                if isinstance(response.get('error'), list):
                    raise Exception(response['error'][0])
                else:
                    raise Exception(response.get('error'))
            updated_user = patch_permission(self.request, 'users', update_data=new_updated_data, setup_check=True, **self.kwargs)
            
            if self.kwargs['schema'] != 'public':
                self.kwargs['schema'] = 'public'
                updateRawSQL('users', update_data=new_updated_data, **self.kwargs)
            return updated_user
        except Exception as e:
            raise Exception(f"{str(e)}")

    def delete_user(self, user_id):
        try:
            if not user_id:
                raise Exception("User details is required to delete user.")
            if isinstance(user_id, str):
                ids = [user_id]
            elif isinstance(user_id, list):
                ids = user_id
            if not ids:
                raise Exception("Please provide valid delete to delete.")
            result = delete_permission(self.request, 'users', ids=ids, setup_check=True, **self.kwargs)
            if self.kwargs['schema'] != 'public':
                self.kwargs['schema'] = 'public'
                delete_data_sql('users', ids, **self.kwargs)
            return result
        except Exception as e:
            raise Exception(f"Error deleting user: {str(e)}")
        
    def check_super_user(self, user_id, **kwargs):
        try:
            filter = [{"field": "id", "operator": "=", "value": user_id}]
            user = get_permissions(self.request, tableName='users', where=filter, fields=['is_superuser'], setup_check=False, **kwargs).get('data', [])
            print("USer detail",user)
            if user and user[0].get('is_superuser'):
                return True
            return False
        except Exception as e:
            raise Exception(f"Error checking superuser status: {str(e)}")
        
    def send_welcomenotes(self, user_id,name):
        try:
            mention = " ".join(word.capitalize() for word in f"{name}".strip().split())
            channel = get_channel_layer()
            self.kwargs['message'] = f"Welcome {mention}! We are excited to have you on board."
            trigger_notication(
                owner_id=user_id,
                channel_layer=channel,
                title=f"Welcome {mention}",
                notification_type='system',
                user_id=user_id,
                channel='push',
                request=self.request,
                **self.kwargs
            )
            return {"success": True,"message": "Welcome notification sent successfully."}
        except Exception as e:
            logger.error(f"Error sending welcome notification: {str(e)}")
            return {"success": False, "error": str(e)}

import requests
from api.security.schema_authority import get_validated_schema

def CreateNewUserInControlPanel(payload):
    try:
        result = requests.post(
            f"{os.getenv('CPANEL_API_URL')}/auth/register/n910nxryka/",
            json={
                "username": payload['username'],
                "email": payload['email'],
                "name": payload.get('name'),
                "phone": payload['phone'],
                "password": payload["password"],
                "organization": payload['organization_id'],
                "is_active": payload.get('is_active', True),
                "is_superuser": False
            }
        )
        print("Control Panel Response:", result.status_code, result.text)
        print("response json:", result.json())
        if result.status_code == 201:  # HTTP 201 means success
            response_data = result.json()  # Parse JSON response
            user_id = response_data.get("id")  # Get 'id' from the response
            return {'ok': True, 'user_id': user_id}  # Return user_id along with success status
        else:
            return {'ok': False, 'error': result.json()}  # Include error details if any
            
    except Exception as e:
        raise Exception(f"An error occurred: {str(e)}")
    
def update_details_in_control_panel(user_id, payload, auth_token):
    try:
        payload = payload.copy()
        payload['id'] =encryptPassword(user_id)
        result = requests.post(
            f"{os.getenv('CPANEL_API_URL')}/auth/user/update-user-details/",
            json=payload,
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        if result.status_code == 200: 
            return {'ok': True}
        else:
            return {'ok': False, 'error': result.json()}  
            
    except Exception as e:
        raise Exception(f"An error occurred: {str(e)}")

# def get_admin_user(org_id):
#     try:
#         cursor = connection.cursor()
#         cursor.execute("""
#                 SELECT id
#                 FROM users
#                 WHERE organization_id = %s AND is_staff=true
#             """, [org_id])
#         user_details = cursor.fetchone()
#         if user_details:
#             adminid = user_details[0]
#             return adminid
#         raise Exception("Admin not found")
#     except Exception as er:
#         return None


        
    