from django.db import connection

def get_chats_with_last_message(user_phone_number):
    try:
        with connection.cursor() as cursor:
            # Define the raw SQL query
            query = """
                WITH user_messages AS (
                SELECT
                    CASE 
                        WHEN sender = %s THEN receiver
                        ELSE sender
                    END AS chat_user,
                    message_content,
                    name,
                    timestamp,
                    status,
                    sender,
                    receiver
                FROM whatsapp_message
                WHERE sender = %s OR receiver = %s
            ),
            latest_messages AS (
                SELECT
                    chat_user,
                    MAX(timestamp) AS last_message_time
                FROM user_messages
                GROUP BY chat_user
            )
            SELECT
                lm.chat_user AS user,
                um.message_content AS last_message,
                um.name,
                um.timestamp,
                um.status,
                CASE
                    WHEN um.sender = %s THEN 'sent'
                    ELSE 'received'
                END AS direction,
                CASE
                    WHEN um.status = 'read' THEN um.timestamp
                    ELSE NULL
                END AS seen_at
            FROM latest_messages lm
            JOIN user_messages um
            ON um.chat_user = lm.chat_user
            AND um.timestamp = lm.last_message_time
            ORDER BY um.timestamp DESC;

            """

            # Parameters for substitution
            params = [user_phone_number, user_phone_number, 
                      user_phone_number, user_phone_number]
            
            # Execute the query with parameters
            cursor.execute(query, params)

            # Fetch and structure the results
            results = cursor.fetchall()

            if not results:
                print(f"No results found for user {user_phone_number}.")
                return []

            # Ensure cursor.description is available
            columns = [col[0] for col in cursor.description] if cursor.description else []
            
            print(columns)


        # Return results as a list of dictionaries
        return [dict(zip(columns, row)) for row in results]
    except Exception as e:
        print(f"Error fetching chats: {str(e)}")
        return []
