from api.telephony.views import run_query
from django.utils.timezone import now

def log_sent_email(sender, recipient, subject, body, status, object_name, record_id, user_id, message_id=None, schema="public"):
    """
    Logs a sent email into the 'email' table.
    """
    try:
        # 1. Get Object ID
        object_query = "SELECT id FROM object WHERE name = %s"
        object_result = run_query(object_query, [object_name], schema=schema)
        
        object_id = None
        if object_result:
            object_id = object_result[0]['id']
        else:
            print(f"⚠️ Warning: Object '{object_name}' not found. Email logged without object linkage.")

        # 2. Insert into Email table
        # We rely on DB defaults for 'id' and 'name' (EML-...)
        insert_query = """
            INSERT INTO email (
                subject, 
                body, 
                from_email, 
                to_email, 
                sent_time, 
                email_status, 
                matched_record_id, 
                owner_id, 
                object_id,
                created_by_id,
                last_modified_by_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        params = [
            subject,
            body,
            sender,
            recipient,
            now(),          # sent_time
            'Sent',         # email_status (assuming we only log sent ones here)
            record_id,
            user_id,        # owner_id
            object_id,
            user_id,        # created_by_id
            user_id         # last_modified_by_id
        ]
        
        run_query(insert_query, params, schema=schema)
        print(f"✅ Email log created for {recipient} (Record: {record_id}, Object: {object_name})")

    except Exception as e:
        print(f"❌ Error logging email: {str(e)}")
