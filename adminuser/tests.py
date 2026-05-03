from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db import connection
from unittest.mock import patch, MagicMock
from api.models import Organization, User
from adminuser.services.organizations import OrganizationService
from adminuser.services.user import UserService
import uuid


class OrganizationServiceTestCase(TestCase):
    """Test cases for OrganizationService."""
    
    def setUp(self):
        """Set up test data."""
        self.org_service = OrganizationService()
        self.test_org = Organization.objects.create(
            id="org_test123",
            name="Test Organization",
            database_schema="test_schema",
            is_active=True
        )
        self.test_user = User.objects.create(
            id="user_test123",
            email="test@example.com",
            username="testuser",
            organization=self.test_org
        )
    
    def test_freeze_organization_success(self):
        """Test successfully freezing an organization."""
        result = self.org_service.freeze_organization(self.test_org.id)
        
        # Refresh from database
        self.test_org.refresh_from_db()
        
        self.assertFalse(self.test_org.is_active)
        self.assertIn("frozen", result["message"])
    
    def test_freeze_organization_not_found(self):
        """Test freezing a non-existent organization."""
        with self.assertRaises(ValidationError):
            self.org_service.freeze_organization("nonexistent_id")
    
    def test_freeze_organization_no_id(self):
        """Test freezing with no ID provided."""
        with self.assertRaises(ValidationError):
            self.org_service.freeze_organization(None)
    
    def test_unfreeze_organization_success(self):
        """Test successfully unfreezing an organization."""
        self.test_org.is_active = False
        self.test_org.save()
        
        result = self.org_service.unfreeze_organization(self.test_org.id)
        
        # Refresh from database
        self.test_org.refresh_from_db()
        
        self.assertTrue(self.test_org.is_active)
        self.assertIn("unfrozen", result["message"])
    
    def test_get_all_organizations(self):
        """Test getting all organizations."""
        result = self.org_service.get_all_organizations()
        
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        self.assertEqual(result[0]["name"], "Test Organization")
    
    def test_get_all_organizations_with_search(self):
        """Test getting organizations with search parameter."""
        result = self.org_service.get_all_organizations(search_param="Test")
        
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        
        # Test search that should return nothing
        result = self.org_service.get_all_organizations(search_param="NonExistent")
        self.assertEqual(len(result), 0)
    
    def test_get_organization_success(self):
        """Test getting a single organization."""
        result = self.org_service.get_organization(self.test_org.id)
        
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Test Organization")
        self.assertIn("user_count", result)
    
    def test_get_organization_not_found(self):
        """Test getting a non-existent organization."""
        result = self.org_service.get_organization("nonexistent_id")
        self.assertIsNone(result)
    
    @patch('adminuser.services.organizations.connection')
    def test_delete_organization_success(self, mock_connection):
        """Test successfully deleting an organization."""
        mock_cursor = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        
        result = self.org_service.delete_organization(self.test_org.id)
        
        self.assertIn("deleted", result["message"])
        # Verify organization is deleted
        self.assertFalse(Organization.objects.filter(id=self.test_org.id).exists())


class UserServiceTestCase(TestCase):
    """Test cases for UserService."""
    
    def setUp(self):
        """Set up test data."""
        self.test_org = Organization.objects.create(
            id="org_test456",
            name="Test User Organization",
            database_schema="test_user_schema",
            is_active=True
        )
        self.user_service = UserService(id=self.test_org.id)
        
        self.test_user = User.objects.create(
            id="user_test456",
            email="testuser@example.com",
            username="testuser",
            name="Test User",
            organization=self.test_org,
            is_active=True
        )
        self.test_user.set_password("testpassword123")
        self.test_user.save()
    
    def test_get_all_users(self):
        """Test getting all users for an organization."""
        result = self.user_service.get_all_users(self.test_org.id)
        
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        self.assertEqual(result[0]["email"], "testuser@example.com")
    
    def test_get_all_users_with_search(self):
        """Test getting users with search parameter."""
        result = self.user_service.get_all_users(self.test_org.id, search_param="testuser")
        
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
    
    def test_get_all_users_no_org_id(self):
        """Test getting users without organization ID."""
        with self.assertRaises(ValidationError):
            self.user_service.get_all_users(None)
    
    def test_get_user_success(self):
        """Test getting a single user."""
        result = self.user_service.get_user(self.test_user.id)
        
        self.assertIsNotNone(result)
        self.assertEqual(result["email"], "testuser@example.com")
    
    def test_get_user_not_found(self):
        """Test getting a non-existent user."""
        result = self.user_service.get_user("nonexistent_id")
        self.assertIsNone(result)
    
    def test_active_user_count(self):
        """Test counting active users."""
        count = self.user_service.active_user_count(self.test_org.id)
        self.assertGreaterEqual(count, 1)
    
    def test_freeze_user_success(self):
        """Test successfully freezing a user."""
        result = self.user_service.freeze_user(self.test_user.id)
        
        # Refresh from database
        self.test_user.refresh_from_db()
        
        self.assertFalse(self.test_user.is_active)
        self.assertIn("frozen", result["message"])
    
    def test_unfreeze_user_success(self):
        """Test successfully unfreezing a user."""
        self.test_user.is_active = False
        self.test_user.save()
        
        result = self.user_service.unfreeze_user(self.test_user.id)
        
        # Refresh from database
        self.test_user.refresh_from_db()
        
        self.assertTrue(self.test_user.is_active)
        self.assertIn("unfrozen", result["message"])
    
    def test_reset_password_success(self):
        """Test successfully resetting password."""
        data = {
            "id": self.test_user.id,
            "password": "newpassword123"
        }
        
        result = self.user_service.reset_password(data)
        
        # Refresh from database
        self.test_user.refresh_from_db()
        
        # Verify password was changed
        self.assertTrue(self.test_user.check_password("newpassword123"))
        self.assertIn("reset", result["message"])
    
    def test_reset_password_with_old_password_validation(self):
        """Test password reset with old password validation."""
        data = {
            "id": self.test_user.id,
            "password": "newpassword123",
            "old_password": "testpassword123"
        }
        
        result = self.user_service.reset_password(data)
        self.assertIn("reset", result["message"])
        
        # Test with wrong old password
        data["old_password"] = "wrongpassword"
        data["password"] = "anotherpassword123"
        
        with self.assertRaises(ValidationError):
            self.user_service.reset_password(data)
    
    def test_reset_password_too_short(self):
        """Test password reset with password too short."""
        data = {
            "id": self.test_user.id,
            "password": "short"
        }
        
        with self.assertRaises(ValidationError):
            self.user_service.reset_password(data)
    
    def test_make_admin_success(self):
        """Test granting admin privileges."""
        result = self.user_service.make_admin(self.test_user.id)
        
        # Refresh from database
        self.test_user.refresh_from_db()
        
        self.assertTrue(self.test_user.is_superuser)
        self.assertIn("admin", result["message"])
    
    def test_remove_admin_success(self):
        """Test removing admin privileges."""
        self.test_user.is_superuser = True
        self.test_user.save()
        
        result = self.user_service.remove_admin(self.test_user.id)
        
        # Refresh from database
        self.test_user.refresh_from_db()
        
        self.assertFalse(self.test_user.is_superuser)
        self.assertIn("removed", result["message"])
    
    def test_update_user_success(self):
        """Test successfully updating user."""
        data = {
            "id": self.test_user.id,
            "username": "updateduser",
            "first_name": "Updated",
            "company": "Updated Company"
        }
        
        result = self.user_service.update_user(data)
        
        # Refresh from database
        self.test_user.refresh_from_db()
        
        self.assertEqual(self.test_user.username, "updateduser")
        self.assertEqual(self.test_user.first_name, "Updated")
        self.assertIn("updated", result["message"])
    
    def test_update_user_no_fields(self):
        """Test updating user with no fields."""
        data = {"id": self.test_user.id}
        
        result = self.user_service.update_user(data)
        self.assertIn("No fields", result["message"])
    
    @patch('adminuser.services.user.connection')
    def test_create_user_success(self, mock_connection):
        """Test successfully creating a user."""
        mock_cursor = MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        
        data = {
            "email": "newuser@example.com",
            "password": "password123",
            "username": "newuser",
            "name": "New User",
            "company": "Test Company"
        }
        
        result = self.user_service.create_user(data)
        
        self.assertIn("created", result["message"])
        self.assertIn("user_id", result)
        
        # Verify user was created
        self.assertTrue(User.objects.filter(email="newuser@example.com").exists())
    
    def test_create_user_no_password(self):
        """Test creating user without password."""
        data = {
            "email": "nopass@example.com",
            "username": "nopass"
        }
        
        result = self.user_service.create_user(data)
        self.assertIn("error", result)
    
    def test_create_user_duplicate_email(self):
        """Test creating user with duplicate email."""
        data = {
            "email": self.test_user.email,
            "password": "password123",
            "username": "duplicate"
        }
        
        result = self.user_service.create_user(data)
        self.assertIn("error", result)

