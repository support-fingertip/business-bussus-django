import requests
from django.conf import settings

def send_whatsapp_message(contact, receiver_number, message_content, type):
    # Endpoint URL to send message
    url = f'https://graph.facebook.com/v21.0/{contact}/messages'
    # print(f"Sending message to {receiver_number} via WhatsApp API..., {url}")
    # print(settings.WHATSAPP_ACCESS_TOKEN)

    # Headers with Authorization token
    headers = {
        'Authorization': f'Bearer {settings.WHATSAPP_ACCESS_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    # Message data
    data = {
        "messaging_product": "whatsapp",
        "to": receiver_number,
        "type": type,
        type: message_content
    }

    # Sending the message via POST request
    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        # Extract the message ID from the response
        response_data = response.json()        
        if 'error' in response_data:
            error_message = response_data['error']
            print(f"Error sending message: {error_message}")
            raise Exception(f"Error sending message: {error_message}")

        message_id = response_data['messages'][0]['id']  # Extracting the message ID
        return message_id  # Return the message ID if needed
    else:
        print(f"Failed to send message: {response.text}")
        raise Exception(f"Failed to send message: {response.text}")
    

def get_long_lived_token(short_lived_token):
    try:
        url = f"https://graph.facebook.com/v23.0/oauth/access_token?client_id=1354196032303282&client_secret=38ed1fd2631f571bac6e3a5f13f4a874&grant_type=authorization_code&code={short_lived_token}"
        response = requests.get(url)
        
        if response.status_code == 200:
            data = response.json()
            print("Long-Lived Token:", data['access_token'])
            return data['access_token']
        else:
            print(f"Error fetching long-lived token: {response.status_code}")
            print(response.text)
    except Exception as error:
        print("Error fetching long-lived token:", error)

def subscribe_to_webhooks(waba_id, token):
    url = f'https://graph.facebook.com/v22.0/{waba_id}/subscribed_apps'
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    response = requests.post(url, headers=headers)
    if response.status_code == 200:
        response_data = response.json()
        print(f"Subscribed to webhooks successfully! Response: {response_data}")
        return response_data
    else:
        print(f"Failed to subscribe to webhooks: {response.text}")
        raise Exception(f"Failed to subscribe to webhooks: {response.text}")

def register_account(payload, number_id):
    url = f'https://graph.facebook.com/v22.0/{number_id}/register'
    headers = {
        'Authorization': f'Bearer {settings.WHATSAPP_ACCESS_TOKEN}',
        'Content-Type': 'application/json'
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        response_data = response.json()
        print(f"Account registered successfully! Response: {response_data}")
        return response_data
    else:
        print(f"Failed to register account: {response.text}")
        raise Exception(f"Failed to register account: {response.text}")
    

def get_whatsapp_phone_numbers(waba_id):
    url = f'https://graph.facebook.com/v22.0/{waba_id}/phone_numbers'
    headers = {
        'Authorization': f'Bearer {settings.WHATSAPP_ACCESS_TOKEN}',
        'Content-Type': 'application/json'
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        response_data = response.json()
        print(f"Fetched WhatsApp phone numbers successfully! Response: {response_data}")
        return response_data
    else:
        print(f"Failed to fetch WhatsApp phone numbers: {response.text}")
        raise Exception(f"Failed to fetch WhatsApp phone numbers: {response.text}")