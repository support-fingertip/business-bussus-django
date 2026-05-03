import random
import re
import string
import threading
import time

import psycopg2
from cryptography.fernet import Fernet
from django.contrib.auth.hashers import make_password
from django.db import connections
from psycopg2 import sql

from public.utils.apps.apps import create_app
from public.utils.objects.builk_object_creation import create_bulk_objects

SAFE_SCHEMA_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
SAFE_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def _validate_schema_name(schema_name: str) -> str:
    """Reject unsafe schema names early to avoid SQL injection."""
    if not schema_name or not SAFE_SCHEMA_PATTERN.match(schema_name):
        raise ValueError("Invalid schema name; only letters, numbers, and underscores are allowed")
    return schema_name


def _validate_token(value: str, label: str) -> str:
    """Ensure identifiers like user/profile ids do not carry injection payloads."""
    if value is None:
        return value
    if not SAFE_TOKEN_PATTERN.match(value):
        raise ValueError(f"Invalid {label}; only letters, numbers, dash, and underscore are allowed")
    return value


def _get_connection():
    """Fetch the thread-local Django connection explicitly for thread safety."""
    return connections["default"]

# Generate a key for encryption (one-time generation)
def generate_key():
    return Fernet.generate_key()

# Encrypt the password before storing it in the database (you can store encrypted passwords)
def encrypt_password(password):
    key = generate_key()  # Use a secret key, should be stored securely
    fernet = Fernet(key)
    encrypted = fernet.encrypt(password.encode())
    return encrypted, key  # Return the encrypted password and key (for later decryption)

# Function to create a new schema for the organization
def create_schema(schema_name):
    schema = _validate_schema_name(schema_name)
    conn = _get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {schema}").format(schema=sql.Identifier(schema)))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise Exception(f"Failed to create schema {schema}: {e}")

# Function to create default tables in the organization schema
def create_user_table_and_profile_table(schema_name):
    schema = _validate_schema_name(schema_name)
    conn = _get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql.SQL("SET search_path TO {schema}, public;").format(schema=sql.Identifier(schema)))

            cursor.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {schema}.profile
                    (
                        id VARCHAR(64) PRIMARY KEY DEFAULT concat('pRfl_', "left"((gen_random_uuid())::text, 18)),
                        name VARCHAR(255) NOT NULL UNIQUE,
                        profile_type VARCHAR(50) NOT NULL DEFAULT 'Standard',
                        created_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE CASCADE,
                        last_modified_by_id VARCHAR(64) REFERENCES public.users(id) ON DELETE CASCADE,
                        created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        description text,
                        user_license_id VARCHAR(255),
                        permissions_read BOOLEAN,
                        permissions_modify_all_data BOOLEAN,
                        permissions_api_enabled BOOLEAN,
                        permissions_view_setup BOOLEAN
                    );
                    """
                ).format(schema=sql.Identifier(schema))
            )

            cursor.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {schema}.users (
                        id VARCHAR(64) PRIMARY KEY,
                        email VARCHAR(255),
                        name VARCHAR(255),
                        username VARCHAR(255) NOT NULL UNIQUE,
                        phone VARCHAR(255),
                        first_name VARCHAR(255),
                        last_name VARCHAR(255),
                        is_active BOOLEAN DEFAULT TRUE,
                        is_superuser BOOLEAN DEFAULT False,
                        is_staff BOOLEAN DEFAULT FALSE,
                        is_email_verified BOOLEAN DEFAULT True,
                        is_deleted BOOLEAN DEFAULT FALSE,
                        app_password VARCHAR(1024) DEFAULT NULL,
                        alias VARCHAR(255),
                        role_id VARCHAR(255),
                        organization_id VARCHAR(64) REFERENCES public.organizations(id) ON DELETE CASCADE,
                        profile_id VARCHAR(64) REFERENCES {schema}.profile(id) ON DELETE SET NULL,
                        password VARCHAR(1024) NOT NULL,
                        created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_login TIMESTAMP,
                        last_modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        timezone VARCHAR(64) DEFAULT 'Asia/Kolkata',
                        locale VARCHAR(32) DEFAULT 'DD/MM/YYYY',
                        company VARCHAR(255) DEFAULT 'Default Company',
                        manager_id VARCHAR(64) REFERENCES {schema}.users(id)
                    );
                    """
                ).format(schema=sql.Identifier(schema))
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise Exception(f"Failed to create tables in schema {schema}: {e}")

def insert_metadata(schema_name, user_id=None, profile_id=None, user_name=None):
     # Third thread - Create bulk objects
    thread3 = threading.Thread(target=create_bulk_objects, args=(user_id, schema_name))
    thread3.daemon = True
    thread3.start()

    thread4 = threading.Thread(target=create_app, args = (user_id, schema_name, user_name))
    thread4.daemon = True
    thread4.start()

    thread5 = threading.Thread(target=execute_sql_file, args=('sqlfiles/setup_fields.sql', schema_name, user_id, profile_id, None))
    thread5.daemon = True
    thread5.start()

    thread3.join()
    thread4.join()
    thread5.join()

def create_default_tables(schema_name, user_id=None, profile_id=None):    
    # First thread - Execute 'default_tables.sql'    
    try:
        execute_sql_file('default_tables.sql', schema_name, user_id, profile_id, None)
    except Exception as e:
        raise Exception(f"Failed to create default tables: {e}")
    try:
        execute_sql_file('tables.sql', schema_name, user_id, profile_id, None)
    except Exception as e:
        raise Exception(f"Failed to table default tables: {e}") 

def insert_mock_data(schema, user_id, profile_id=None):
    # files = [
    #     'sqlfiles/mockdata/accounts_100k.sql',
    #     'sqlfiles/mockdata/leads_100k.sql',
    #     'sqlfiles/mockdata/products_100k.sql',
    #     'sqlfiles/mockdata/invoices_100k.sql',
    #     'sqlfiles/mockdata/invoice_items_100k.sql',
    # ]
    files= ["sqlfiles/mockdata/reports.sql"]
    for file in files:
        execute_sql_file(file, schema, user_id, profile_id=profile_id)

def execute_sql_file(file_path, schema_name, user_id=None, profile_id=None, event=None, batch_size=500):
    """
    Execute SQL file. For large files (100K+ rows), streams the file and
    executes statements in batches to avoid memory bloat and long transactions.

    Statements are split on ';' at the end of a line (not mid-string).
    """
    import os

    schema = _validate_schema_name(schema_name)
    safe_user_id = _validate_token(user_id, "user id") if user_id else None
    safe_profile_id = _validate_token(profile_id, "profile id") if profile_id else None

    def _apply_placeholders(text):
        if safe_user_id:
            text = text.replace('DYNAMIC_CREATED_BY_ID', safe_user_id)
            text = text.replace('DYNAMIC_LAST_MODIFIED_DATE_ID', safe_user_id)
            text = text.replace('DYNAMIC_OWNER_ID', safe_user_id)
            text = text.replace('USER_ID', safe_user_id)
        if safe_profile_id:
            text = text.replace('PROFILE_ID', safe_profile_id)
        return text

    # File size threshold (in MB) above which we use streaming
    LARGE_FILE_MB = 5
    try:
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    except OSError:
        file_size_mb = 0

    retries = 3
    conn = _get_connection()

    for attempt in range(retries):
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql.SQL("SET search_path TO {schema};").format(schema=sql.Identifier(schema)))

                if file_size_mb < LARGE_FILE_MB:
                    # Small file — original single-execute path
                    with open(file_path, 'r') as file:
                        sql_content = file.read()
                    sql_content = _apply_placeholders(sql_content)
                    cursor.execute(sql.SQL(sql_content))
                    conn.commit()
                else:
                    # Large file — stream and batch
                    buffer = []
                    batch = []
                    total_executed = 0
                    with open(file_path, 'r', encoding='utf-8') as file:
                        for line in file:
                            buffer.append(line)
                            # A statement ends when a line ends with ';' (ignoring trailing whitespace)
                            stripped = line.rstrip()
                            if stripped.endswith(';'):
                                statement = ''.join(buffer).strip()
                                buffer = []
                                if not statement or statement.startswith('--'):
                                    continue
                                batch.append(_apply_placeholders(statement))
                                if len(batch) >= batch_size:
                                    cursor.execute(sql.SQL('\n'.join(batch)))
                                    total_executed += len(batch)
                                    batch = []
                                    conn.commit()
                    # Flush remaining buffer / batch
                    if buffer:
                        remaining = ''.join(buffer).strip()
                        if remaining:
                            batch.append(_apply_placeholders(remaining))
                    if batch:
                        cursor.execute(sql.SQL('\n'.join(batch)))
                        total_executed += len(batch)
                        conn.commit()
                    print(f"[insert_mock_data] Executed {total_executed} statements from {file_path}")
            break
        except psycopg2.errors.DeadlockDetected:
            conn.rollback()
            time.sleep(random.uniform(1, 3))
        except Exception as e:
            conn.rollback()
            raise Exception(f"Failed to execute SQL file {file_path}: {e}")
    if event:
        event.set()


# Function to insert the organization into the public schema's organization table
def insert_organization_to_public_schema(orgid, name, db_user, db_password, schema_name, domain):
    conn = _get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO public.organizations (id, name, domain, database_schema, db_user, db_password)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    domain = EXCLUDED.domain,
                    database_schema = EXCLUDED.database_schema,
                    db_user = EXCLUDED.db_user,
                    db_password = EXCLUDED.db_password
                RETURNING id;
                """,
                [orgid, name, domain, schema_name, db_user, db_password],
            )
            row = cursor.fetchone()
        conn.commit()
        return row[0]
    except Exception as e:
        conn.rollback()
        raise Exception(f"Failed to insert organization: {e}")

# Function to create the new tenant (organization)
def create_new_tenant(organization_name, username, password, schema_name, payload,organization_id):
    name = organization_name
    domain = payload.get('domain', organization_name.replace(" ", "-").lower())
    user_id = payload.get('id')

    if not user_id:
        raise ValueError("user_id is required in payload for tenant creation")
    if not organization_id:
        raise ValueError("Organization id is required for tenant creation")
    schema = _validate_schema_name(schema_name)
    safe_user_id = _validate_token(user_id, "user id")
    safe_org_id = _validate_token(organization_id, "organization id")
    try:
        create_schema(schema)
        create_user_table_and_profile_table(schema)
        organization_id = insert_organization_to_public_schema(safe_org_id, name, username, "Salesforce1!", schema, domain)
        profile_id = insert_first_user_and_profile(schema, payload, organization_id)

        # sequential, fail-fast
        create_default_tables(schema, safe_user_id, profile_id)
        user_name = f"{payload.get('first_name', '')} {payload.get('last_name', '')}".strip() or username
        insert_metadata(schema, safe_user_id, profile_id, user_name=user_name)
        insert_mock_data(schema, safe_user_id, profile_id=profile_id)

        return profile_id, organization_id

    except Exception as e:
        # log here if needed
        # log.error("Tenant creation failed", exc_info=True)
        # You might also want to clean up half-created schema/org if needed
        raise Exception(f"Failed to create new tenant: {e}")


def insert_first_user_and_profile(schema_name, user_payload, organization_id=None):
    """
    Inserts the first user into both public.users and organization.users,
    creates a profile in the organization schema, and assigns it to the user.
    """
    schema = _validate_schema_name(schema_name)
    user_id = _validate_token(user_payload.get('id'), "user id")
    org_id = _validate_token(organization_id, "organization id") if organization_id else None
    if not user_id:
        raise ValueError("user_id is required in payload")
    
    print("Payload",user_payload)

    conn = _get_connection()
    try:
        with conn.cursor() as cursor:
            profile_id = f"pRfl_{''.join(random.choices(string.ascii_letters + string.digits, k=12))}"
            profile_id = _validate_token(profile_id, "profile id")

            cursor.execute(
                sql.SQL(
                    """
                    INSERT INTO {schema}.profile (id, name, profile_type, description, created_by_id, last_modified_by_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """
                ).format(schema=sql.Identifier(schema)),
                [
                    profile_id,
                    "System Administrator",
                    "admin",
                    "Default admin profile",
                    user_id,
                    user_id,
                ],
            )

            try:
                cursor.execute(
                    sql.SQL(
                        """
                        INSERT INTO {schema}.profile (name, profile_type, description, created_by_id, last_modified_by_id)
                        VALUES (%s, %s, %s, %s, %s);
                        """
                    ).format(schema=sql.Identifier(schema)),
                    (
                        'User',
                        'user',
                        'A minimal access to the app',
                        user_id,
                        user_id,
                    ),
                )
            except Exception:
                # If it already exists, continue; uniqueness keeps it safe.
                pass

            encrypted_password = make_password(user_payload.get('password'))

            cursor.execute(
                """
                UPDATE public.users
                SET profile_id = %s, organization_id = %s WHERE id = %s
                """,
                [profile_id, org_id, user_id],
            )

            cursor.execute(
                sql.SQL(
                    """
                    INSERT INTO {schema}.users 
                    (id, name, email, 
                    username, phone, first_name, 
                    last_name, is_active, is_superuser,
                    is_staff, alias, 
                    organization_id, profile_id, password, 
                    created_date,company)
                    VALUES 
                    (%s, %s, %s, 
                     %s, %s, %s, 
                     %s, %s, %s,
                     %s, %s, %s, 
                     %s, %s,CURRENT_TIMESTAMP,%s)
                    """
                ).format(schema=sql.Identifier(schema)),
                [
                    user_id,
                    (user_payload.get('first_name') or '') + " " + (user_payload.get('last_name') or ''),
                    user_payload.get('email'),
                    user_payload.get('username'),
                    user_payload.get('phone'),
                    user_payload.get('first_name'),
                    user_payload.get('last_name'),
                    True,
                    True,
                    False,
                    user_payload.get('alias', None),
                    org_id,
                    profile_id,
                    encrypted_password,
                    user_payload.get('organisation_name', None),
                ],
            )
        conn.commit()
        return profile_id
    except Exception as e:
        conn.rollback()
        raise Exception(f"Failed to insert first user and profile: {e}")
