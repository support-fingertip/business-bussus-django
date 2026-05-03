from api.ORM.sqlFunctions.information_schema import get_column_data_types
from cryptography.fernet import Fernet
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import base64
import os
import jwt
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Any
from cryptography.hazmat.primitives import serialization

key = Fernet.generate_key()
fernet = Fernet(key)

KEY = base64.b64decode(os.getenv("KEY"))
IV  = base64.b64decode(os.getenv("IV"))

def construct_filters(fields, table_name, search_term, **kwargs):
    """
    Construct filters dynamically based on field data types.
    Fields will be filtered using appropriate operators based on their data types.
    """
    column_data_types = get_column_data_types(table_name, fields, **kwargs)
    filters = []

    for field in fields:
        column_type = column_data_types.get(field)

        if column_type:
            operator, valid_search_term = determine_operator(column_type, search_term, **kwargs)
            if operator:
                filters.append({'field': field, 'operator': operator, 'value': valid_search_term})
    
    return {"or": filters}

def determine_operator(column_type, search_term, **kwargs):
    """
    Determine the appropriate operator based on the column data type and ensure
    that the search_term is valid for that type.
    """
    # Handle boolean fields separately to avoid invalid syntax errors
    if column_type == 'boolean':
        if search_term.lower() in ['true', 'false']:
            return '=', search_term.lower()  # Exact match for boolean values
        else:
            return None, None  # Return None if invalid boolean input

    # Handle numeric fields separately to avoid invalid syntax errors
    if column_type in ['integer', 'numeric', 'decimal']:
        # Try to convert the search term to a number
        try:
            # If the search term is a valid number, use it in the filter
            valid_search_term = float(search_term)  # Use float to allow decimals as well
            return '=', valid_search_term
        except ValueError:
            return None, None  # Return None if the search_term can't be converted to a number

    if column_type in ['character varying', 'text', 'varchar']:
        return 'ilike', search_term  # Case-insensitive matching for text-based fields
    elif column_type in ['date', 'timestamp']:
        if isinstance(search_term, str):
            return None, None  # Return None if the search_term is a string (invalid for date/timestamp)
        return '>=', search_term  # Date comparison (can be adjusted as needed)
    elif column_type == 'json':
        return 'ilike', search_term  # Fallback to ilike for JSON fields (you could use JSON-specific functions here)
    else:
        return None, None  # Default to no operator if the type is not supported
    



def process_filters(filters, table_name, **kwargs):
    """
    Process filters to ensure they are in the correct format for the database query.
    This function can be extended to handle more complex filter processing if needed.
    """
    if filters is not None and not isinstance(filters, list):
        return None
    fields = [filter_item['field'] for filter_item in filters]
    column_data_types = get_column_data_types(table_name, fields, **kwargs)    
    for filter_item in filters:
        field = filter_item['field']
        datatype = column_data_types.get(field)
        if datatype:
            filter_item['datatype'] = datatype
        if 'timestamp' in column_data_types.get(field) and (filter_item['operator'] == '=' or filter_item['operator'] == 'equals'):
            filter_item['cast'] = True
            filter_item['datatype'] = 'timestamp'
    return filters


def encrypt_dict(data: dict) -> dict:
    """
    Encrypts all values in a dictionary using Fernet symmetric encryption.
    """
    encrypted_data = {}
    for key, value in data.items():
        if value is not None:
            # Convert all values to string for consistency
            encrypted_value = fernet.encrypt(str(value).encode()).decode()
            encrypted_data[key] = encrypted_value
        else:
            encrypted_data[key] = None
    return encrypted_data


def decrypt_dict(data: dict) -> dict:
    """
    Decrypts all values in a dictionary that were encrypted using encrypt_dict.
    """
    decrypted_data = {}
    for key, value in data.items():
        if value is not None:
            try:
                decrypted_value = fernet.decrypt(value.encode()).decode()
                decrypted_data[key] = decrypted_value
            except Exception:
                # if not encrypted, just return as-is
                decrypted_data[key] = value
        else:
            decrypted_data[key] = None
    return decrypted_data


def encryptPassword(password:str):
    try:
        chiper = AES.new(KEY,AES.MODE_CBC,IV)
        padded = password + (AES.block_size - len(password) % AES.block_size) * chr(AES.block_size - len(password) % AES.block_size)
        encrypted = chiper.encrypt(padded.encode("utf-8"))
        encoded = base64.b64encode(encrypted).decode("utf-8")
        return encoded
    except Exception as er:
        print(er)
        return None

class JWTHandler:
    """
    A class to handle JWT token creation and verification
    """
    def __init__(self):
        self.secret_key  = os.getenv("ENCRYPTION_JWT_SECRET")
        self.algorithm = os.getenv("ENCRYPTION_JWT_ALGORITHM", "HS256")
        self.secret_key_no_expire = os.getenv("ENCRYPTION_JWT_NO_EXPIRE_SECRET")
        self.algorithm_no_expire = os.getenv("ENCRYPTION_JWT_NO_EXPIRE_ALGORITHM", "HS256")
        
    def _get_signing_key(self):
        """
        Converts the secret string into a key object if using EdDSA.
        """
        if self.algorithm_no_expire == "EdDSA":
            return serialization.load_pem_private_key(
                self.secret_key_no_expire.encode(),
                password=None
            )
        return self.secret_key_no_expire
    
    def encrypt(self, payload: Dict[str, Any], expires_in_hours: int = 24) -> str:
        token_data = payload.copy()
        expiration = datetime.utcnow() + timedelta(hours=expires_in_hours)
        token_data['exp'] = expiration
        token_data['iat'] = datetime.utcnow()
        encoded_token = jwt.encode(
            token_data,
            self.secret_key,
            algorithm=self.algorithm
        )
        return encoded_token
    
    def decrypt(self, token: str) -> Optional[Dict[str, Any]]:
        try:
            decoded_payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )
            return decoded_payload
            
        except jwt.ExpiredSignatureError:
            print("Error: Token has expired")
            return None
        except jwt.InvalidTokenError:
            print("Error: Invalid token")
            return None
        except Exception as e:
            print(f"Error decoding token: {str(e)}")
            return None
        
    def encrypt_no_expire(self, payload: Dict[str, Any]) -> Optional[str]:
        try:
            token_data = payload.copy()
            token_data['iat'] = datetime.now(timezone.utc)
            return jwt.encode(
                token_data,
                self.secret_key_no_expire,
                algorithm=self.algorithm_no_expire
            )
        except Exception as e:
            print(f"Error encoding token: {e}")
            return None

    def decrypt_no_expire(self, token: str) -> Optional[Dict[str, Any]]:
        try:
            return jwt.decode(
                token,
                self.secret_key_no_expire,
                algorithms=[self.algorithm_no_expire]
            )
        except jwt.InvalidTokenError as e:
            print(f"Invalid token: {e}")
            return None