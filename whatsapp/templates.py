import requests
from django.conf import settings

def create_facebook_template(name, language, components):
    """
    Create a WhatsApp message template on Facebook Cloud API.

    :param name: Name of the template.
    :param language: Language code (e.g., 'en_US').
    :param components: A list of components that define the structure of the template.
    :return: Response object from the API request.
    """
    # Facebook access token and phone number ID from Django settings
    access_token = settings.WHATSAPP_ACCESS_TOKEN
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    whatsapp_ba_app_id = settings.WHATSAPP_BA_APP_ID

    # URL to create a new message template
    url = f'https://graph.facebook.com/v20.0/{whatsapp_ba_app_id}/message_templates'

    # Request headers
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json',
    }

    # Payload for the template
    payload = {
        "name": name,
        "category": "MARKETING",
        "language": language,
        "components": components
    }

    print(payload)

    # Make the POST request to create the template
    response = requests.post(url, json=payload, headers=headers)

    # Return the response object (you can process this further as needed)
    return response.json()


def get_templates(waba_id):
    print("Fetching templates for WABA ID:", waba_id)
    try:
        url = f"https://graph.facebook.com/v19.0/{waba_id}/message_templates?access_token={settings.WHATSAPP_ACCESS_TOKEN}"
        result = requests.get(url)
        result.raise_for_status()          
        x = result.json()
        if 'error' in x:
            raise Exception(f"Error fetching templates: {x['error']['message']}")
        templates = x.get('data', [])
        print(templates)
        response = []
        #and template.get('name') != "hello_world"
        for template in templates:
            if template.get('status') == "APPROVED":
                response.append(template)                
        return response

    except requests.exceptions.RequestException as req_err:
        print(f"Request error occurred: {req_err}")
    except ValueError as json_err:
        print(f"JSON decoding error: {json_err}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
