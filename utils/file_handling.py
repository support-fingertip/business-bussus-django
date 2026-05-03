import os
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

def handle_file_upload(file, **kwargs):
    """
    Upload a file and return its type and uploaded path.

    Args:
        file (InMemoryUploadedFile): The file to be uploaded.
        kwargs (dict): Should contain 'org' dict with 'name' key.

    Returns:
        dict: {'type': 'image', 'file_path': 'uploads/<org_name>/file_name.jpg', 'size': 12345}
    """
    org_name = kwargs.get('org', {}).get('name', 'public').replace(" ", "_").lower()

    try:
        if not file:
            raise Exception({'error': 'No file provided'})

        # Folder based on organization
        upload_folder = os.path.join('uploads', org_name)
        os.makedirs(os.path.join(default_storage.location, upload_folder), exist_ok=True)

        # Save the file
        file_name = file.name
        file_path = os.path.join(upload_folder, file_name)
        file_saved_path = default_storage.save(file_path, ContentFile(file.read()))

        # Detect file type
        file_extension = file_name.split('.')[-1].lower()
        if file_extension in ['jpg', 'jpeg', 'png', 'gif']:
            file_type = 'image'
        elif file_extension in ['pdf', 'doc', 'docx']:
            file_type = 'document'
        elif file_extension in ['mp4', 'avi', 'mkv']:
            file_type = 'video'
        else:
            file_type = 'unknown'

        return {
            'type': file_type,
            'file_path': file_saved_path,
            'size': file.size
        }

    except Exception as e:
        raise Exception({'error': str(e)})


def handle_file_update(file, previous_file_path, **kwargs):
    """
    Update an existing file with a new file and delete the old one.
    """
    org_name = kwargs.get('org', {}).get('name', 'public').replace(" ", "_").lower()

    try:
        if not file:
            raise Exception({'error': 'No file provided'})
        if not previous_file_path:
            raise Exception({'error': 'No previous file path provided'})

        # Delete old file
        if default_storage.exists(previous_file_path):
            default_storage.delete(previous_file_path)

        # Folder based on organization
        upload_folder = os.path.join('uploads', org_name)
        os.makedirs(os.path.join(default_storage.location, upload_folder), exist_ok=True)

        # Save new file
        file_name = file.name
        file_path = os.path.join(upload_folder, file_name)
        file_saved_path = default_storage.save(file_path, ContentFile(file.read()))

        # Detect file type
        file_extension = file_name.split('.')[-1].lower()
        if file_extension in ['jpg', 'jpeg', 'png', 'gif']:
            file_type = 'image'
        elif file_extension in ['pdf', 'doc', 'docx']:
            file_type = 'document'
        elif file_extension in ['mp4', 'avi', 'mkv']:
            file_type = 'video'
        else:
            file_type = 'unknown'

        return {
            'type': file_type,
            'file_path': file_saved_path
        }

    except Exception as e:
        raise Exception({'error': str(e)})

    
class FileDeletionError(Exception):
    """Custom exception raised when file deletion fails."""
    pass

class FileNotFoundError(Exception):
    """Custom exception raised when a file is not found."""
    pass

def handle_file_delete(file_path):
    """
    Delete the file at the given path.

    Args:
        file_path (str): The path to the file to be deleted.

    Raises:
        FileDeletionError: If there is an issue deleting the file.
        FileNotFoundError: If the file does not exist.
        
    Returns:
        None: If the file is successfully deleted.
    """
    try:
        # Ensure the file path is provided
        if not file_path:
            raise FileDeletionError("No file path provided")

        # Check if the file exists before deleting
        if default_storage.exists(file_path):
            # Delete the file
            default_storage.delete(file_path)
            
            # After deletion, check if the file exists (should not exist)
            if default_storage.exists(file_path):
                raise FileDeletionError("File could not be deleted")
            else:
                # Successfully deleted
                return        

    except FileDeletionError as e:
        raise FileDeletionError(f"Error deleting file: {str(e)}")

    except FileNotFoundError as e:
        raise FileNotFoundError(f"Error: {str(e)}")

    except Exception as e:
        raise Exception(f"An unexpected error occurred: {str(e)}")