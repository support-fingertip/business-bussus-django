from django.db import connection, transaction
from django.core.exceptions import ValidationError
from api.models import Organization, User
from adminuser.utils import validate_schema_name
import logging
from api.ORM.sqlFunctions.utils.helpers import validate_identifier
logger = logging.getLogger(__name__)


class OrganizationService():
    def freeze_organization(self, org_id):
        """
        Deactivate an organization by setting is_active to False.
        
        Args:
            org_id: The ID of the organization to freeze
            
        Returns:
            dict: Success message
            
        Raises:
            Organization.DoesNotExist: If organization not found
            ValidationError: If validation fails
        """
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE organizations SET is_active = FALSE WHERE id = %s;", [org_id])
            return {"message": f"Organization {org_id} has been frozen."}
        except Organization.DoesNotExist:
            logger.error(f"Organization {org_id} not found")
            raise ValidationError(f"Organization with id {org_id} does not exist.")
        except Exception as e:
            logger.error(f"Error freezing organization {org_id}: {str(e)}")
            raise ValidationError(f"Failed to freeze organization: {str(e)}")
    def unfreeze_organization(self, org_id):
        """
        Reactivate an organization by setting is_active to True.
        
        Args:
            org_id: The ID of the organization to unfreeze
            
        Returns:
            dict: Success message
            
        Raises:
            Organization.DoesNotExist: If organization not found
            ValidationError: If validation fails
        """
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE organizations SET is_active = TRUE WHERE id = %s;", [org_id])
            return {"message": f"Organization {org_id} has been unfrozen."}
        except Organization.DoesNotExist:
            logger.error(f"Organization {org_id} not found")
            raise ValidationError(f"Organization with id {org_id} does not exist.")
        except Exception as e:
            logger.error(f"Error unfreezing organization {org_id}: {str(e)}")
            raise ValidationError(f"Failed to unfreeze organization: {str(e)}")
    def delete_organization(self, org_id):
        """
        Delete an organization and its associated schema.
        
        Args:
            org_id: The ID of the organization to delete
            
        Returns:
            dict: Success message with schema name
            
        Raises:
            Organization.DoesNotExist: If organization not found
            ValidationError: If validation fails
        """
        try:
            if not org_id:
                raise ValidationError("Organization ID is required")
            
            with transaction.atomic():
                org = Organization.objects.get(id=org_id)
                schema_name = org.database_schema
                
                # Validate schema name to prevent injection
                validate_schema_name(schema_name)
                
                # Drop the tenant's schema using SQL identifier for safe quoting
                from psycopg2 import sql
                with connection.cursor() as cursor:
                    # First, fetch the schema name
                    cursor.execute("SELECT database_schema FROM organizations WHERE id = %s;", [org_id])
                    schema_name = cursor.fetchone()
                    if not schema_name:
                        raise Exception(f"Organization with id {org_id} does not exist.")
                    schema_name = schema_name[0]
                    
                    # Validate schema name to prevent SQL injection
                    validate_identifier(schema_name)
                    
                    # Drop the tenant's schema using sql.Identifier for safety
                    cursor.execute(
                        sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE;').format(sql.Identifier(schema_name))
                    )
                    
                    # Delete the organization record
                    cursor.execute("DELETE FROM organizations WHERE id = %s;", [org_id])
            return {"message": f"Organization {org_id} and its schema {schema_name} have been deleted."}
        except Organization.DoesNotExist:
            logger.error(f"Organization {org_id} not found")
            raise ValidationError(f"Organization with id {org_id} does not exist.")
        except Exception as e:
            logger.error(f"Error deleting organization {org_id}: {str(e)}")
            raise ValidationError(f"Failed to delete organization: {str(e)}")
    def get_all_organizations(self, search_param=None):
        """
        Get all organizations with user count, optionally filtered by search parameter.
        
        Args:
            search_param: Optional search string to filter by organization name
            
        Returns:
            list: List of organization dictionaries with user counts
            
        Raises:
            ValidationError: If query fails
        """
        try:
            # Use ORM with annotations for better security
            from django.db.models import Count, Q
            
            queryset = Organization.objects.annotate(
                user_count=Count('user')
            ).values(
                'id',
                'name',
                'user_count',
                'is_active',
                'database_schema',
                'created_date'
            ).order_by('-created_date')
            
            if search_param:
                # Sanitize search parameter
                search_param = str(search_param).strip()
                queryset = queryset.filter(name__icontains=search_param)
            
            data = list(queryset)
            # Rename fields to match existing API
            for item in data:
                item['organization_id'] = item.pop('id')
            
            logger.info(f"Retrieved {len(data)} organizations")
            return data
        except Exception as e:
            logger.error(f"Error fetching organizations: {str(e)}")
            raise ValidationError(f"Failed to fetch organizations: {str(e)}")
    def get_organization(self, org_id):
        """
        Get a single organization with user count.
        
        Args:
            org_id: The ID of the organization to retrieve
            
        Returns:
            dict: Organization data with user count, or None if not found
            
        Raises:
            ValidationError: If query fails
        """
        try:
            if not org_id:
                raise ValidationError("Organization ID is required")
            
            from django.db.models import Count
            
            # Use ORM with annotation
            org_data = Organization.objects.filter(id=org_id).annotate(
                user_count=Count('user')
            ).values(
                'id',
                'name',
                'user_count',
                'is_active',
                'database_schema',
                'created_date'
            ).first()
            
            if org_data:
                # Rename field to match existing API
                org_data['organization_id'] = org_data.pop('id')
                logger.info(f"Retrieved organization {org_id}")
                return org_data
            else:
                logger.warning(f"Organization {org_id} not found")
                return None
        except Exception as e:
            logger.error(f"Error fetching organization {org_id}: {str(e)}")
            raise ValidationError(f"Failed to fetch organization: {str(e)}")
        