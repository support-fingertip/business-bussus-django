from django.db import connection, transaction
from django.contrib.auth.hashers import make_password
from psycopg2 import sql
from api.ORM.sqlFunctions.utils.helpers import validate_identifier
from django.contrib.auth.hashers import make_password, check_password
from django.core.exceptions import ValidationError
from api.models import User, Organization
from adminuser.utils import validate_schema_name
import logging
import uuid

logger = logging.getLogger(__name__)


class UserService():
    def __init__(self, id=None):
        self.org_id = id
    
    def get_all_users(self, org_id, search_param=None):
        """
        Get all users for an organization, optionally filtered by search parameter.
        
        Args:
            org_id: The organization ID
            search_param: Optional search string to filter users
            
        Returns:
            list: List of user dictionaries
        """
        try:
            if not org_id:
                raise ValidationError("Organization ID is required")
            
            from django.db.models import Q
            
            # Base queryset with organization filter
            queryset = User.objects.filter(organization_id=org_id)
            
            if search_param:
                # Sanitize and apply search filter
                search_param = str(search_param).strip()
                queryset = queryset.filter(
                    Q(username__icontains=search_param) |
                    Q(email__icontains=search_param) |
                    Q(first_name__icontains=search_param) |
                    Q(last_name__icontains=search_param)
                )
            
            # Use values to get dictionary results
            users = list(queryset.values(
                'id', 'username', 'email', 'first_name', 'name', 'last_name',
                'is_active', 'is_staff', 'is_superuser', 'company',
                'last_modified_date', 'timezone', 'locale', 'created_date'
            ))
            
            logger.info(f"Retrieved {len(users)} users for organization {org_id}")
            return users
        except Exception as e:
            logger.error(f"Error fetching users for org {org_id}: {str(e)}")
            raise ValidationError(f"Failed to fetch users: {str(e)}")
    
    def get_user(self, user_id):
        """
        Get a single user by ID.
        
        Args:
            user_id: The user ID
            
        Returns:
            dict: User data or None if not found
        """
        try:
            if not user_id:
                raise ValidationError("User ID is required")
            
            user = User.objects.filter(id=user_id).values(
                'id', 'username', 'email', 'first_name', 'name', 'last_name',
                'is_active', 'is_staff', 'is_superuser', 'company',
                'last_modified_date', 'timezone', 'locale', 'created_date'
            ).first()
            
            if user:
                logger.info(f"Retrieved user {user_id}")
            else:
                logger.warning(f"User {user_id} not found")
            
            return user
        except Exception as e:
            logger.error(f"Error fetching user {user_id}: {str(e)}")
            raise ValidationError(f"Failed to fetch user: {str(e)}")
    
    def active_user_count(self, org_id):
        """
        Count active users in an organization.
        
        Args:
            org_id: The organization ID
            
        Returns:
            int: Count of active users
        """
        try:
            if not org_id:
                raise ValidationError("Organization ID is required")
            
            count = User.objects.filter(organization_id=org_id, is_active=True).count()
            logger.info(f"Active user count for org {org_id}: {count}")
            return count
        except Exception as e:
            logger.error(f"Error counting active users for org {org_id}: {str(e)}")
            raise ValidationError(f"Failed to count active users: {str(e)}")
        
    def freeze_user(self, user_id):
        """
        Deactivate a user.
        
        Args:
            user_id: The user ID to freeze
            
        Returns:
            dict: Success message
        """
        try:
            if not user_id:
                raise ValidationError("User ID is required")
            
            user = User.objects.get(id=user_id)
            user.is_active = False
            user.save(update_fields=['is_active'])
            
            logger.info(f"User {user_id} frozen successfully")
            return {"message": f"User {user_id} has been frozen."}
        except User.DoesNotExist:
            logger.error(f"User {user_id} not found")
            raise ValidationError(f"User with id {user_id} does not exist.")
        except Exception as e:
            logger.error(f"Error freezing user {user_id}: {str(e)}")
            raise ValidationError(f"Failed to freeze user: {str(e)}")    
    def unfreeze_user(self, user_id):
        """
        Reactivate a user.
        
        Args:
            user_id: The user ID to unfreeze
            
        Returns:
            dict: Success message
        """
        try:
            if not user_id:
                raise ValidationError("User ID is required")
            
            user = User.objects.get(id=user_id)
            user.is_active = True
            user.save(update_fields=['is_active'])
            
            logger.info(f"User {user_id} unfrozen successfully")
            return {"message": f"User {user_id} has been unfrozen."}
        except User.DoesNotExist:
            logger.error(f"User {user_id} not found")
            raise ValidationError(f"User with id {user_id} does not exist.")
        except Exception as e:
            logger.error(f"Error unfreezing user {user_id}: {str(e)}")
            raise ValidationError(f"Failed to unfreeze user: {str(e)}")
    def reset_password(self, data):
        """
        Reset user password with validation.
        
        Args:
            data: Dictionary containing id, password, and optionally old_password
            
        Returns:
            dict: Success message
        """
        try:
            user_id = data.get("id")
            new_password = data.get("password")
            old_password = data.get("old_password")
            
            if not user_id or not new_password:
                raise ValidationError("User ID and new password are required")
            
            if len(new_password) < 8:
                raise ValidationError("Password must be at least 8 characters long")
            
            user = User.objects.get(id=user_id)
            
            # Validate old password if provided
            if old_password and not check_password(old_password, user.password):
                raise ValidationError("Current password is incorrect")
            
            user.set_password(new_password)
            user.save(update_fields=['password'])
            
            logger.info(f"Password reset successfully for user {user_id}")
            return {"message": f"Password for user {user_id} has been reset."}
        except User.DoesNotExist:
            logger.error(f"User {user_id} not found")
            raise ValidationError(f"User with id {user_id} does not exist.")
        except Exception as e:
            logger.error(f"Error resetting password for user {user_id}: {str(e)}")
            raise ValidationError(f"Failed to reset password: {str(e)}")
    def make_admin(self, user_id):
        """
        Grant admin privileges to a user.
        
        Args:
            user_id: The user ID
            
        Returns:
            dict: Success message
        """
        try:
            if not user_id:
                raise ValidationError("User ID is required")
            
            user = User.objects.get(id=user_id)
            user.is_superuser = True
            user.save(update_fields=['is_superuser'])
            
            logger.info(f"Admin privileges granted to user {user_id}")
            return {"message": f"User {user_id} has been granted admin privileges."}
        except User.DoesNotExist:
            logger.error(f"User {user_id} not found")
            raise ValidationError(f"User with id {user_id} does not exist.")
        except Exception as e:
            logger.error(f"Error granting admin to user {user_id}: {str(e)}")
            raise ValidationError(f"Failed to grant admin privileges: {str(e)}")
    def remove_admin(self, user_id):
        """
        Remove admin privileges from a user.
        
        Args:
            user_id: The user ID
            
        Returns:
            dict: Success message
        """
        try:
            if not user_id:
                raise ValidationError("User ID is required")
            
            user = User.objects.get(id=user_id)
            user.is_superuser = False
            user.save(update_fields=['is_superuser'])
            
            logger.info(f"Admin privileges removed from user {user_id}")
            return {"message": f"Admin privileges removed for user {user_id}."}
        except User.DoesNotExist:
            logger.error(f"User {user_id} not found")
            raise ValidationError(f"User with id {user_id} does not exist.")
        except Exception as e:
            logger.error(f"Error removing admin from user {user_id}: {str(e)}")
            raise ValidationError(f"Failed to remove admin privileges: {str(e)}")
    def update_email(self, data):
        """
        Update user email. Handles both public and tenant schema updates.
        Username is always synced with the email.
        """
        try:
            user_id = data.get("id")
            new_email = data.get("email")

            if not user_id or not new_email:
                raise ValidationError("User ID and email are required")

            # Validate email format
            from django.core.validators import validate_email
            validate_email(new_email)

            # Check if email already exists for another user
            if User.objects.filter(email=new_email).exclude(id=user_id).exists():
                raise ValidationError("Email already exists for another user")

            with transaction.atomic():
                # Update in public schema using ORM
                user = User.objects.get(id=user_id)

                user.email = new_email
                # Always sync username with email
                user.username = new_email
                user.save(update_fields=['email', 'username'])

                # Update in tenant schema if needed
                if self.org_id:
                    org = Organization.objects.get(id=self.org_id)
                    schema_name = org.database_schema

                    validate_schema_name(schema_name)

                    if schema_name != 'public':
                        from psycopg2 import sql
                        with connection.cursor() as cursor:
                            try:
                                cursor.execute(
                                    sql.SQL('SET search_path TO {}, public;').format(
                                        sql.Identifier(schema_name)
                                    )
                                )

                                # Always sync username with email in tenant schema
                                cursor.execute(
                                    "UPDATE users SET email = %s, username = %s WHERE id = %s;",
                                    [new_email, new_email, user_id]
                                )
                            finally:
                                cursor.execute('SET search_path TO public;')

            logger.info(f"Email and username updated for user {user_id}")
            return {"message": f"Email for user {user_id} has been updated to {new_email}."}

        except User.DoesNotExist:
            logger.error(f"User {user_id} not found")
            raise ValidationError(f"User with id {user_id} does not exist.")
        except Organization.DoesNotExist:
            logger.error(f"Organization {self.org_id} not found")
            raise ValidationError(f"Organization with id {self.org_id} does not exist.")
        except Exception as e:
            logger.error(f"Error updating email for user {user_id}: {str(e)}")
            raise ValidationError(f"Failed to update email: {str(e)}")    
    def get_profiles(self):
        """
        Get profiles from tenant schema.
        
        Returns:
            list: List of profile dictionaries
        """
        try:
            if not self.org_id:
                raise ValidationError("Organization ID is required")
            
            org = Organization.objects.get(id=self.org_id)
            schema_name = org.database_schema
            
            # Validate schema name
            validate_schema_name(schema_name)
                
            
            from psycopg2 import sql
            with connection.cursor() as cursor:
                try:
                    cursor.execute(
                        sql.SQL('SET search_path TO {}, public;').format(
                            sql.Identifier(schema_name)
                        )
                    )
                    cursor.execute("SELECT id, name, profile_type, created_date FROM profile;")
                    columns = [col[0] for col in cursor.description]
                    results = cursor.fetchall()
                finally:
                    # Always reset search_path
                    cursor.execute('SET search_path TO public;')
            
            profiles = [dict(zip(columns, row)) for row in results]
            logger.info(f"Retrieved {len(profiles)} profiles for org {self.org_id}")
            return profiles
        except Organization.DoesNotExist:
            logger.error(f"Organization {self.org_id} not found")
            raise ValidationError(f"Organization with id {self.org_id} does not exist.")
        except Exception as e:
            logger.error(f"Error fetching profiles: {str(e)}")
            raise ValidationError(f"Failed to fetch profiles: {str(e)}")
    
    def update_user(self, data):
        """
        Update user fields. Handles both public and tenant schema updates.
        
        Args:
            data: Dictionary containing id and fields to update
            
        Returns:
            dict: Success message
        """
        try:
            user_id = data.get("id")
            if not user_id:
                raise ValidationError("User ID is required")
            
            # Define allowed fields to update
            allowed_fields = ["username", "first_name", "last_name", "company", 
                            "timezone", "locale", "phone", "manager_id", "profile_id", "name"]
            
            # Extract only allowed fields that are present in data
            update_data = {key: data[key] for key in allowed_fields if key in data}
            
            if not update_data:
                return {"message": "No fields to update."}
            
            with transaction.atomic():
                # Update in public schema using ORM
                user = User.objects.get(id=user_id)
                for key, value in update_data.items():
                    setattr(user, key, value)
                user.save(update_fields=list(update_data.keys()))
                
                # Update in tenant schema if needed
                if self.org_id:
                    org = Organization.objects.get(id=self.org_id)
                    schema_name = org.database_schema
                    
                    # Validate schema name
                    validate_schema_name(schema_name)
                        
                    
                    if schema_name != 'public':
                        # Build safe SQL query using psycopg2.sql
                        from psycopg2 import sql
                        
                        # Create SQL identifiers for field names (safe from injection)
                        update_parts = [
                            sql.SQL('{} = %s').format(sql.Identifier(key))
                            for key in update_data.keys()
                        ]
                        update_clause = sql.SQL(', ').join(update_parts)
                        
                        values = list(update_data.values())
                        values.append(user_id)
                        
                        with connection.cursor() as cursor:
                            try:
                                cursor.execute(
                                    sql.SQL('SET search_path TO {}, public;').format(
                                        sql.Identifier(schema_name)
                                    )
                                )
                                # Build complete UPDATE query with safe identifiers
                                update_query = sql.SQL('UPDATE users SET {} WHERE id = %s;').format(
                                    update_clause
                                )
                                cursor.execute(update_query, values)
                            finally:
                                # Always reset search_path
                                cursor.execute('SET search_path TO public;')
            
            logger.info(f"User {user_id} updated successfully")
            return {"message": f"User {user_id} has been updated."}
        except User.DoesNotExist:
            logger.error(f"User {user_id} not found")
            raise ValidationError(f"User with id {user_id} does not exist.")
        except Organization.DoesNotExist:
            logger.error(f"Organization {self.org_id} not found")
            raise ValidationError(f"Organization with id {self.org_id} does not exist.")
        except Exception as e:
            logger.error(f"Error updating user {user_id}: {str(e)}")
            raise ValidationError(f"Failed to update user: {str(e)}")
    
    def delete_user(self, user_id):
        """
        Delete a user from both public and tenant schemas.
        
        Args:
            user_id: The user ID to delete
            
        Returns:
            dict: Success message
        """
        try:
            if not user_id:
                raise ValidationError("User ID is required")
            
            with transaction.atomic():
                # Delete from public schema using ORM
                user = User.objects.get(id=user_id)
                user.delete()
                
                # Delete from tenant schema if needed
                if self.org_id:
                    org = Organization.objects.get(id=self.org_id)
                    schema_name = org.database_schema
                    
                    # Validate schema name
                    validate_schema_name(schema_name)
                        
                    
                    if schema_name != 'public':
                        from psycopg2 import sql
                        with connection.cursor() as cursor:
                            try:
                                cursor.execute(
                                    sql.SQL('SET search_path TO {}, public;').format(
                                        sql.Identifier(schema_name)
                                    )
                                )
                                cursor.execute("DELETE FROM users WHERE id = %s;", [user_id])
                            finally:
                                # Always reset search_path
                                cursor.execute('SET search_path TO public;')
            
            logger.info(f"User {user_id} deleted successfully")
            return {"message": f"User {user_id} has been deleted."}
        except User.DoesNotExist:
            logger.error(f"User {user_id} not found")
            raise ValidationError(f"User with id {user_id} does not exist.")
        except Organization.DoesNotExist:
            logger.error(f"Organization {self.org_id} not found")
            raise ValidationError(f"Organization with id {self.org_id} does not exist.")
        except Exception as e:
            logger.error(f"Error deleting user {user_id}: {str(e)}")
            raise ValidationError(f"Failed to delete user: {str(e)}")
    
    def create_user(self, data):
        """
        Create a new user in both public and tenant schemas.
        
        Args:
            data: Dictionary containing user data
            
        Returns:
            dict: Success message with user_id
        """
        try:
            # Validate required fields
            raw_password = data.get("password")
            email = data.get("email")
            
            if not raw_password:
                return {"error": "Password is required."}
            
            if not email:
                return {"error": "Email is required."}
            
            if len(raw_password) < 8:
                return {"error": "Password must be at least 8 characters long."}
            
            # Validate email format
            from django.core.validators import validate_email
            validate_email(email)
            
            # Check if email already exists
            if User.objects.filter(email=email).exists():
                return {"error": "Email already exists."}
            
            # Generate user ID
            user_id = f"usR_{uuid.uuid4().hex[:10]}"
            
            with transaction.atomic():
                # Create user in public schema using ORM
                user = User.objects.create(
                    id=user_id,
                    name=data.get("name", ""),
                    email=email,
                    username=data.get("username", ""),
                    phone=data.get("phone"),
                    manager_id=data.get("manager_id"),
                    profile_id=data.get("profile_id"),
                    company=data.get("company"),
                    is_active=True,
                    organization_id=self.org_id
                )
                user.set_password(raw_password)
                user.save()
                
                # Create in tenant schema if needed
                if self.org_id:
                    org = Organization.objects.get(id=self.org_id)
                    schema_name = org.database_schema
                    
                    # Validate schema name
                    validate_schema_name(schema_name)
                        
                    
                    if schema_name != 'public':
                        hashed_password = user.password
                        params = [
                            user_id,
                            data.get("name"),
                            email,
                            data.get("username"),
                            data.get("phone"),
                            data.get("manager_id"),
                            data.get("profile_id"),
                            data.get("company"),
                            True,
                            hashed_password,
                            self.org_id
                        ]
                        
                        from psycopg2 import sql
                        with connection.cursor() as cursor:
                            try:
                                cursor.execute(
                                    sql.SQL('SET search_path TO {}, public;').format(
                                        sql.Identifier(schema_name)
                                    )
                                )
                                cursor.execute("""
                                    INSERT INTO users(
                                        id, name, email, username, phone, 
                                        manager_id, profile_id, company, is_active, password, organization_id
                                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                """, params)
                            finally:
                                # Always reset search_path
                                cursor.execute('SET search_path TO public;')
            
            logger.info(f"User {user_id} created successfully")
            return {"message": f"User {user_id} has been created.", "user_id": user_id}
        except Organization.DoesNotExist:
            logger.error(f"Organization {self.org_id} not found")
            raise ValidationError(f"Organization with id {self.org_id} does not exist.")
        except Exception as e:
            logger.error(f"Error creating user: {str(e)}")
            raise ValidationError(f"Failed to create user: {str(e)}")
        return {"message": f"User {user_id} has been created.", "user_id": user_id}
        