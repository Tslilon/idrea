import os
import json
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_text_message_input(recipient, text):
    return json.dumps(
        {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }
    )

def send_message(data):
    headers = {
        "Content-type": "application/json",
        "Authorization": f"Bearer {os.getenv('ACCESS_TOKEN')}",
    }

    url = f"https://graph.facebook.com/{os.getenv('VERSION')}/{os.getenv('PHONE_NUMBER_ID')}/messages"

    response = requests.post(url, data=data, headers=headers)
    print(f"Status code: {response.status_code}")
    print(f"Response: {response.text}")
    return response

# Get the first recipient from the list
recipient = os.getenv('RECIPIENT_WAID').split(',')[0]
print(f"Sending message to: {recipient}")

data = get_text_message_input(recipient, "Test message from Python script")
response = send_message(data) 