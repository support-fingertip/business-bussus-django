import os
import psycopg2

DB_NAME = os.getenv("DATABASE_NAME")
DB_USER = os.getenv("DATABASE_USER")
DB_PASSWORD = os.getenv("DATABASE_PASSWORD")
DB_HOST = os.getenv("DATABASE_HOST", "localhost")
DB_PORT = os.getenv("DATABASE_PORT", "5432")

TEMPLATE_DUMP = "/root/dump.sql"  # path to your pre-generated template dump
TMP_DIR = "/tmp"  # temporary folder for modified dump files

def clean_dump(sql_text):
    """Remove all psql meta commands starting with a backslash"""
    cleaned_lines = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("\\"):  
            # skip all psql meta commands
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)

def clone_schema(new_schema):
    if not os.path.exists(TEMPLATE_DUMP):
        raise Exception("Template SQL not found at " + TEMPLATE_DUMP)

    # 1. Read dump file
    with open(TEMPLATE_DUMP, "r") as f:
        dump_sql = f.read()

    # 2. Clean dump from backslash (\) commands
    dump_sql = clean_dump(dump_sql)

    # 3. Replace schema name
    dump_sql = dump_sql.replace("public", new_schema)

    # 4. Connect to DB
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    )
    conn.autocommit = True
    cur = conn.cursor()

    # 5. Create schema
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {new_schema};")

    # 6. Execute SQL safely, splitting by semicolon
    statements = dump_sql.split(";")

    for stmt in statements:
        stmt = stmt.strip()
        if stmt == "":
            continue
        try:
            cur.execute(stmt + ";")
        except Exception as e:
            print("❌ Error executing statement:")
            print(stmt)
            raise e

    cur.close()
    conn.close()

    return f"Schema {new_schema} created successfully."