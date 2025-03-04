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
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
    return response

# Test with different phone number formats
formats = [
    "+972542292507",  # With plus
    "972542292507",   # Without plus
    "0542292507"      # Local format
]

message = "Testing different phone number formats. If you receive this, please reply."

for format in formats:
    print(f"\nTesting with phone number format: {format}")
    data = get_text_message_input(format, message)
    send_message(data)

print("\nChecking environment variables:")
print(f"PHONE_NUMBER_ID: {os.getenv('PHONE_NUMBER_ID')}")
print(f"VERSION: {os.getenv('VERSION')}")
# Don't print the full access token for security
print(f"ACCESS_TOKEN: {os.getenv('ACCESS_TOKEN')[:10]}...") 