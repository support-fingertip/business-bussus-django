# import requests

# SENDGRID_API_KEY = "API_KKEY"

# def send_email(to_email, subject, content):
#     url = "https://api.sendgrid.com/v3/mail/send"
#     headers = {
#         "Authorization": f"Bearer {SENDGRID_API_KEY}",
#         "Content-Type": "application/json"
#     }
#     payload = {
#         "personalizations": [
#             {
#                 "to": [{"email": to_email}],
#                 "subject": subject
#             }
#         ],
#         "from": {
#             "email": "divya@fingertipplus.com"  # Replace with your verified sender email
#         },
#         "content": [
#             {
#                 "type": "text/plain",
#                 "value": content
#             }
#         ]
#     }

#     response = requests.post(url, headers=headers, json=payload)
#     print(response.status_code, response.text)

# # Example usage:
# send_email("shreyahippa@gmail.com", "Hello from SendGrid", "This is a test email from SendGrid API!")

# def run():
#     print("Running")


call= [
        {'id': 'fLds_f55f3eeb-f9b', 'required': True, 'unique_field': True, 'external_id': None, 'custom_report_type': None, 'custom_field': None, 'ai_prediction': None, 'auto_number': None, 'display_format': None, 'starting_number': None, 'default_value_in_checkbox': None, 'pickup_values': None, 'decimal_places': None, 'default_value': None, 'geolocation_notation': None, 'mask_type': None, 'mask_character': None, 'visible_lines': None, 'number_length': None, 'datatype': 'text', 'name': 'name', 'description': None, 'help': None, 'length': '128', 'object_name': 'call', 'label': 'Name', 'delete_record_type': None, 'parent_object': None, 'created_date': '2025-05-30', 'created_by': None, 'last_modified_date': '2025-05-30', 'last_modified_by': '2025-05-30 09:03:53.997219+00', 'object_id': '3440fcdbd9', 'is_modifiable': True, 'relationship_name': None, 'help_text': None},
        {'id': 'fLds_2dcf184b-264', 'required': False, 'unique_field': None, 'external_id': None, 'custom_report_type': None, 'custom_field': None, 'ai_prediction': None, 'auto_number': None, 'display_format': None, 'starting_number': None, 'default_value_in_checkbox': None, 'pickup_values': None, 'decimal_places': None, 'default_value': None, 'geolocation_notation': None, 'mask_type': None, 'mask_character': None, 'visible_lines': None, 'number_length': None, 'datatype': '64', 'name': 'last_modified_by_id', 'description': None, 'help': None, 'length': None, 'object_name': 'call', 'label': 'Last Modified By', 'delete_record_type': None, 'parent_object': 'users', 'created_date': '2025-05-30', 'created_by': None, 'last_modified_date': '2025-05-30', 'last_modified_by': '2025-05-30 09:03:53.997219+00', 'object_id': '3440fcdbd9', 'is_modifiable': True, 'relationship_name': None, 'help_text': None},
        {'id': 'fLds_20b59032-2b2', 'required': False, 'unique_field': None, 'external_id': None, 'custom_report_type': None, 'custom_field': None, 'ai_prediction': None, 'auto_number': None, 'display_format': None, 'starting_number': None, 'default_value_in_checkbox': None, 'pickup_values': None, 'decimal_places': None, 'default_value': None, 'geolocation_notation': None, 'mask_type': None, 'mask_character': None, 'visible_lines': None, 'number_length': None, 'datatype': 'datetime', 'name': 'last_modified_date', 'description': None, 'help': None, 'length': None, 'object_name': 'call', 'label': 'Last Modified Date', 'delete_record_type': None, 'parent_object': None, 'created_date': '2025-05-30', 'created_by': None, 'last_modified_date': '2025-05-30', 'last_modified_by': '2025-05-30 09:03:53.997219+00', 'object_id': '3440fcdbd9', 'is_modifiable': True, 'relationship_name': None, 'help_text': None},
        {'id': 'fLds_9c80c52c-960', 'required': False, 'unique_field': None, 'external_id': None, 'custom_report_type': None, 'custom_field': None, 'ai_prediction': None, 'auto_number': None, 'display_format': None, 'starting_number': None, 'default_value_in_checkbox': None, 'pickup_values': None, 'decimal_places': None, 'default_value': None, 'geolocation_notation': None, 'mask_type': None, 'mask_character': None, 'visible_lines': None, 'number_length': None, 'datatype': 'datetime', 'name': 'created_date', 'description': None, 'help': None, 'length': None, 'object_name': 'call', 'label': 'Created Date', 'delete_record_type': None, 'parent_object': None, 'created_date': '2025-05-30', 'created_by': None, 'last_modified_date': '2025-05-30', 'last_modified_by': '2025-05-30 09:03:53.997219+00', 'object_id': '3440fcdbd9', 'is_modifiable': True, 'relationship_name': None, 'help_text': None},
        {'id': 'fLds_1d31b02f-f32', 'required': False, 'unique_field': None, 'external_id': None, 'custom_report_type': None, 'custom_field': None, 'ai_prediction': None, 'auto_number': None, 'display_format': None, 'starting_number': None, 'default_value_in_checkbox': None, 'pickup_values': None, 'decimal_places': None, 'default_value': None, 'geolocation_notation': None, 'mask_type': None, 'mask_character': None, 'visible_lines': None, 'number_length': None, 'datatype': 'text', 'name': 'organisation', 'description': None, 'help': None, 'length': None, 'object_name': 'call', 'label': 'Organisation', 'delete_record_type': None, 'parent_object': None, 'created_date': '2025-05-30', 'created_by': None, 'last_modified_date': '2025-05-30', 'last_modified_by': '2025-05-30 09:03:53.997219+00', 'object_id': '3440fcdbd9', 'is_modifiable': True, 'relationship_name': None, 'help_text': None},
        {'id': 'aaf0f0e4eb', 'required': False, 'unique_field': False, 'external_id': None, 'custom_report_type': None, 'custom_field': None, 'ai_prediction': None, 'auto_number': None, 'display_format': None, 'starting_number': None, 'default_value_in_checkbox': None, 'pickup_values': None, 'decimal_places': None, 'default_value': None, 'geolocation_notation': None, 'mask_type': None, 'mask_character': None, 'visible_lines': None, 'number_length': None, 'datatype': 'phone', 'name': 'from_number', 'description': None, 'help': None, 'length': None, 'object_name': None, 'label': 'From Number', 'delete_record_type': None, 'parent_object': None, 'created_date': '2025-05-30', 'created_by': None, 'last_modified_date': '2025-05-30', 'last_modified_by': None, 'object_id': '3440fcdbd9', 'is_modifiable': True, 'relationship_name': None, 'help_text': None},
        {'id': '294313b7c5', 'required': False, 'unique_field': False, 'external_id': None, 'custom_report_type': None, 'custom_field': None, 'ai_prediction': None, 'auto_number': None, 'display_format': None, 'starting_number': None, 'default_value_in_checkbox': None, 'pickup_values': None, 'decimal_places': None, 'default_value': None, 'geolocation_notation': None, 'mask_type': None, 'mask_character': None, 'visible_lines': None, 'number_length': None, 'datatype': 'phone', 'name': 'to_number', 'description': None, 'help': None, 'length': None, 'object_name': None, 'label': 'To Number', 'delete_record_type': None, 'parent_object': None, 'created_date': '2025-05-30', 'created_by': None, 'last_modified_date': '2025-05-30', 'last_modified_by': None, 'object_id': '3440fcdbd9', 'is_modifiable': True, 'relationship_name': None, 'help_text': None},
        {'id': 'a1f9d0dee4', 'required': False, 'unique_field': False, 'external_id': None, 'custom_report_type': None, 'custom_field': None, 'ai_prediction': None, 'auto_number': None, 'display_format': None, 'starting_number': None, 'default_value_in_checkbox': None, 'pickup_values': None, 'decimal_places': None, 'default_value': None, 'geolocation_notation': None, 'mask_type': None, 'mask_character': None, 'visible_lines': None, 'number_length': None, 'datatype': 'datetime', 'name': 'start_time', 'description': None, 'help': None, 'length': None, 'object_name': None, 'label': 'Start Time', 'delete_record_type': None, 'parent_object': None, 'created_date': '2025-05-30', 'created_by': None, 'last_modified_date': '2025-05-30', 'last_modified_by': None, 'object_id': '3440fcdbd9', 'is_modifiable': True, 'relationship_name': None, 'help_text': None},
        {'id': 'cd35122aa3', 'required': False, 'unique_field': False, 'external_id': None, 'custom_report_type': None, 'custom_field': None, 'ai_prediction': None, 'auto_number': None, 'display_format': None, 'starting_number': None, 'default_value_in_checkbox': None, 'pickup_values': None, 'decimal_places': None, 'default_value': None, 'geolocation_notation': None, 'mask_type': None, 'mask_character': None, 'visible_lines': None, 'number_length': None, 'datatype': 'datetime', 'name': 'end_time', 'description': None, 'help': None, 'length': None, 'object_name': None, 'label': 'End Time', 'delete_record_type': None, 'parent_object': None, 'created_date': '2025-05-30', 'created_by': None, 'last_modified_date': '2025-05-30', 'last_modified_by': None, 'object_id': '3440fcdbd9', 'is_modifiable': True, 'relationship_name': None, 'help_text': None},
        {'id': 'eb2eaa9d0b', 'required': False, 'unique_field': False, 'external_id': None, 'custom_report_type': None, 'custom_field': None, 'ai_prediction': None, 'auto_number': None, 'display_format': None, 'starting_number': None, 'default_value_in_checkbox': None, 'pickup_values': None, 'decimal_places': None, 'default_value': None, 'geolocation_notation': None, 'mask_type': None, 'mask_character': None, 'visible_lines': None, 'number_length': None, 'datatype': 'number', 'name': 'duration', 'description': None, 'help': None, 'length': None, 'object_name': None, 'label': 'Duration', 'delete_record_type': None, 'parent_object': None, 'created_date': '2025-05-30', 'created_by': None, 'last_modified_date': '2025-05-30', 'last_modified_by': None, 'object_id': '3440fcdbd9', 'is_modifiable': True, 'relationship_name': None, 'help_text': None},
        {'id': 'bef0157dba', 'required': False, 'unique_field': False, 'external_id': None, 'custom_report_type': None, 'custom_field': None, 'ai_prediction': None, 'auto_number': None, 'display_format': None, 'starting_number': None, 'default_value_in_checkbox': None, 'pickup_values': None, 'decimal_places': None, 'default_value': None, 'geolocation_notation': None, 'mask_type': None, 'mask_character': None, 'visible_lines': None, 'number_length': None, 'datatype': 'text', 'name': 'call_type', 'description': None, 'help': None, 'length': None, 'object_name': None, 'label': 'Call Type', 'delete_record_type': None, 'parent_object': None, 'created_date': '2025-05-30', 'created_by': None, 'last_modified_date': '2025-05-30', 'last_modified_by': None, 'object_id': '3440fcdbd9', 'is_modifiable': True, 'relationship_name': None, 'help_text': None},
        {'id': 'dd71b8c378', 'required': False, 'unique_field': False, 'external_id': None, 'custom_report_type': None, 'custom_field': None, 'ai_prediction': None, 'auto_number': None, 'display_format': None, 'starting_number': None, 'default_value_in_checkbox': None, 'pickup_values': None, 'decimal_places': None, 'default_value': None, 'geolocation_notation': None, 'mask_type': None, 'mask_character': None, 'visible_lines': None, 'number_length': None, 'datatype': 'text', 'name': 'call_status', 'description': None, 'help': None, 'length': None, 'object_name': None, 'label': 'Call Status', 'delete_record_type': None, 'parent_object': None, 'created_date': '2025-05-30', 'created_by': None, 'last_modified_date': '2025-05-30', 'last_modified_by': None, 'object_id': '3440fcdbd9', 'is_modifiable': True, 'relationship_name': None, 'help_text': None},
        {'id': '9b3909deb1', 'required': False, 'unique_field': False, 'external_id': None, 'custom_report_type': None, 'custom_field': None, 'ai_prediction': None, 'auto_number': None, 'display_format': None, 'starting_number': None, 'default_value_in_checkbox': None, 'pickup_values': None, 'decimal_places': None, 'default_value': None, 'geolocation_notation': None, 'mask_type': None, 'mask_character': None, 'visible_lines': None, 'number_length': None, 'datatype': 'text', 'name': 'recording_file', 'description': None, 'help': None, 'length': None, 'object_name': None, 'label': 'Recording File', 'delete_record_type': None, 'parent_object': None, 'created_date': '2025-05-30', 'created_by': None, 'last_modified_date': '2025-05-30', 'last_modified_by': None, 'object_id': '3440fcdbd9', 'is_modifiable': True, 'relationship_name': None, 'help_text': None},
        {'id': 'fb6e19d2cc', 'required': False, 'unique_field': False, 'external_id': None, 'custom_report_type': None, 'custom_field': None, 'ai_prediction': None, 'auto_number': None, 'display_format': None, 'starting_number': None, 'default_value_in_checkbox': None, 'pickup_values': None, 'decimal_places': None, 'default_value': None, 'geolocation_notation': None, 'mask_type': None, 'mask_character': None, 'visible_lines': None, 'number_length': None, 'datatype': 'text', 'name': 'call_id', 'description': None, 'help': None, 'length': None, 'object_name': None, 'label': 'Call Id', 'delete_record_type': None, 'parent_object': None, 'created_date': '2025-05-30', 'created_by': None, 'last_modified_date': '2025-05-30', 'last_modified_by': None, 'object_id': '3440fcdbd9', 'is_modifiable': True, 'relationship_name': None, 'help_text': None},
        {'id': '7282f865a4', 'required': False, 'unique_field': False, 'external_id': None, 'custom_report_type': None, 'custom_field': None, 'ai_prediction': None, 'auto_number': None, 'display_format': None, 'starting_number': None, 'default_value_in_checkbox': None, 'pickup_values': None, 'decimal_places': None, 'default_value': None, 'geolocation_notation': None, 'mask_type': None, 'mask_character': None, 'visible_lines': None, 'number_length': None, 'datatype': 'text', 'name': 'disposition', 'description': None, 'help': None, 'length': None, 'object_name': None, 'label': 'Disposition', 'delete_record_type': None, 'parent_object': None, 'created_date': '2025-05-30', 'created_by': None, 'last_modified_date': '2025-05-30', 'last_modified_by': None, 'object_id': '3440fcdbd9', 'is_modifiable': True, 'relationship_name': None, 'help_text': None},
        {'id': '4048432b99', 'required': False, 'unique_field': False, 'external_id': None, 'custom_report_type': None, 'custom_field': None, 'ai_prediction': None, 'auto_number': None, 'display_format': None, 'starting_number': None, 'default_value_in_checkbox': None, 'pickup_values': None, 'decimal_places': None, 'default_value': None, 'geolocation_notation': None, 'mask_type': None, 'mask_character': None, 'visible_lines': None, 'number_length': None, 'datatype': 'text', 'name': 'description', 'description': None, 'help': None, 'length': None, 'object_name': None, 'label': 'Description', 'delete_record_type': None, 'parent_object': None, 'created_date': '2025-05-30', 'created_by': None, 'last_modified_date': '2025-05-30', 'last_modified_by': None, 'object_id': '3440fcdbd9', 'is_modifiable': True, 'relationship_name': None, 'help_text': None},
        {'id': 'f57df01829', 'required': False, 'unique_field': False, 'external_id': None, 'custom_report_type': None, 'custom_field': None, 'ai_prediction': None, 'auto_number': None, 'display_format': None, 'starting_number': None, 'default_value_in_checkbox': None, 'pickup_values': None, 'decimal_places': None, 'default_value': None, 'geolocation_notation': None, 'mask_type': None, 'mask_character': None, 'visible_lines': None, 'number_length': None, 'datatype': 'text', 'name': 'matched_record_id', 'description': None, 'help': None, 'length': None, 'object_name': None, 'label': 'Matched record ', 'delete_record_type': None, 'parent_object': None, 'created_date': '2025-05-30', 'created_by': None, 'last_modified_date': '2025-05-30', 'last_modified_by': None, 'object_id': '3440fcdbd9', 'is_modifiable': True, 'relationship_name': None, 'help_text': None},
        {'id': 'f3988980c9', 'required': False, 'unique_field': False, 'external_id': None, 'custom_report_type': None, 'custom_field': None, 'ai_prediction': None, 'auto_number': None, 'display_format': None, 'starting_number': None, 'default_value_in_checkbox': None, 'pickup_values': None, 'decimal_places': None, 'default_value': None, 'geolocation_notation': None, 'mask_type': None, 'mask_character': None, 'visible_lines': None, 'number_length': None, 'datatype': 'text', 'name': 'matched_object', 'description': None, 'help': None, 'length': None, 'object_name': None, 'label': 'Matched object', 'delete_record_type': None, 'parent_object': None, 'created_date': '2025-05-30', 'created_by': None, 'last_modified_date': '2025-05-30', 'last_modified_by': None, 'object_id': '3440fcdbd9', 'is_modifiable': True, 'relationship_name': None, 'help_text': None},
        {'id': 'fLds_95271f4b-3b7', 'required': False, 'unique_field': None, 'external_id': None, 'custom_report_type': None, 'custom_field': None, 'ai_prediction': None, 'auto_number': None, 'display_format': None, 'starting_number': None, 'default_value_in_checkbox': None, 'pickup_values': None, 'decimal_places': None, 'default_value': None, 'geolocation_notation': None, 'mask_type': None, 'mask_character': None, 'visible_lines': None, 'number_length': None, 'datatype': 'lookup_relationship', 'name': 'owner_id', 'description': None, 'help': None, 'length': '64', 'object_name': 'call', 'label': 'Owner', 'delete_record_type': None, 'parent_object': 'users', 'created_date': '2025-05-30', 'created_by': None, 'last_modified_date': '2025-05-30', 'last_modified_by': '2025-05-30 09:03:53.997219+00', 'object_id': '3440fcdbd9', 'is_modifiable': True, 'relationship_name': 'owner', 'help_text': None},
        {'id': 'fLds_4b1665fd-547', 'required': False, 'unique_field': None, 'external_id': None, 'custom_report_type': None, 'custom_field': None, 'ai_prediction': None, 'auto_number': None, 'display_format': None, 'starting_number': None, 'default_value_in_checkbox': None, 'pickup_values': None, 'decimal_places': None, 'default_value': None, 'geolocation_notation': None, 'mask_type': None, 'mask_character': None, 'visible_lines': None, 'number_length': None, 'datatype': 'lookup_relationship', 'name': 'created_by_id', 'description': None, 'help': None, 'length': '64', 'object_name': 'call', 'label': 'Created By', 'delete_record_type': None, 'parent_object': 'users', 'created_date': '2025-05-30', 'created_by': None, 'last_modified_date': '2025-05-30', 'last_modified_by': '2025-05-30 09:03:53.997219+00', 'object_id': '3440fcdbd9', 'is_modifiable': True, 'relationship_name': 'created_by', 'help_text': None},
        {'id': '74865ba7cf', 'required': False, 'unique_field': False, 'external_id': None, 'custom_report_type': None, 'custom_field': None, 'ai_prediction': None, 'auto_number': None, 'display_format': None, 'starting_number': None, 'default_value_in_checkbox': None, 'pickup_values': None, 'decimal_places': None, 'default_value': None, 'geolocation_notation': None, 'mask_type': None, 'mask_character': None, 'visible_lines': None, 'number_length': None, 'datatype': 'lookup', 'name': 'telephony_id', 'description': None, 'help': None, 'length': None, 'object_name': None, 'label': 'Telephony ID', 'delete_record_type': None, 'parent_object': None, 'created_date': '2025-05-30', 'created_by': None, 'last_modified_date': '2025-05-30', 'last_modified_by': None, 'object_id': '3440fcdbd9', 'is_modifiable': True, 'relationship_name': None, 'help_text': None},
    ]


db_filelds = ["start_time",
            "organisation",
            "last_modified_date",
            "from_number",
            "last_modified_date",
            "last_modified_by_id",
            "to_number",
            "created_by_id",
            "created_by_id",
            "description",
            "created_date",
            "last_modified_by_id",
            "call_type",
            "matched_object",
            "end_time",
            "owner_id",
            "created_date",
            "name",
            "organisation",
            "matched_record_id",
            "call_id",
            "call_status",
            "owner_id",
            "is_deleted",
            "disposition",
            "duration",
            "name",
            "recording_file"
]

field_names = [c["name"] for c in call if c.get("name")]


for cl in db_filelds:
    if cl not in field_names:
        print(cl)



print(len(call))



print(len(db_filelds))