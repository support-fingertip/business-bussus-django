from django.conf import settings
import psycopg2
from psycopg2 import OperationalError

def get_shcema_connection(user, password, alias='default'):
    """
    Establish a psycopg2 connection using Django's settings.DATABASES[alias]
    """
    db_config = settings.DATABASES.get(alias)

    if not db_config:
        raise ValueError(f"No database configuration found for alias '{alias}'.")

    try:
        conn = psycopg2.connect(
            dbname=db_config.get('NAME'),
            user=user,
            password=password,
            host=db_config.get('HOST', 'localhost'),
            port=db_config.get('PORT', 5432),
        )
        print("✅ PostgreSQL connection established using Django settings.")
        return conn
    except OperationalError as e:
        print("❌ Failed to connect using Django DB settings.")
        raise e
