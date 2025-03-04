import os
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def verify_webhook(url, verify_token):
    """Test the webhook verification endpoint"""
    test_url = f"{url}?hub.mode=subscribe&hub.verify_token={verify_token}&hub.challenge=CHALLENGE_ACCEPTED"
    print(f"Testing webhook verification at: {test_url}")
    
    try:
        response = requests.get(test_url)
        print(f"Status code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200 and response.text == "CHALLENGE_ACCEPTED":
            print("✅ Webhook verification is working correctly!")
        else:
            print("❌ Webhook verification failed!")
    except Exception as e:
        print(f"Error: {str(e)}")

def test_webhook_message(url):
    """Test sending a message to the webhook"""
    print(f"\nTesting webhook message handling at: {url}")
    
    test_payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "123456789",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "1234567890",
                        "phone_number_id": "123456789"
                    },
                    "contacts": [{
                        "profile": {
                            "name": "Test User"
                        },
                        "wa_id": "972542292507"
                    }],
                    "messages": [{
                        "from": "972542292507",
                        "id": "wamid.test123",
                        "timestamp": "1677673605",
                        "text": {
                            "body": "Test message from verification script"
                        },
                        "type": "text"
                    }]
                },
                "field": "messages"
            }]
        }]
    }
    
    try:
        response = requests.post(url, json=test_payload)
        print(f"Status code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("✅ Webhook message handling is working correctly!")
        else:
            print("❌ Webhook message handling failed!")
    except Exception as e:
        print(f"Error: {str(e)}")

def print_webhook_config_instructions():
    """Print instructions for configuring the webhook in Meta Developer Portal"""
    print("\n=== Meta Developer Portal Webhook Configuration ===")
    print("1. Go to your Meta Developer Portal > WhatsApp > Configuration")
    print("2. Set the following values:")
    print("   - Callback URL: https://your-tunnel-url.loca.lt/webhook")
    print("   - Verify Token:", os.getenv("VERIFY_TOKEN", "1234"))
    print("3. Click 'Verify and Save'")
    print("4. Subscribe to the 'messages' field")
    print("\nIf you've changed your localtunnel URL, you'll need to update the Callback URL.")

if __name__ == "__main__":
    # Get the current localtunnel URL
    tunnel_url = input("Enter your current localtunnel URL (e.g., https://stupid-groups-throw.loca.lt): ")
    
    # Make sure the URL doesn't end with a slash
    if tunnel_url.endswith("/"):
        tunnel_url = tunnel_url[:-1]
    
    # Add /webhook to the URL
    webhook_url = f"{tunnel_url}/webhook"
    
    # Get the verify token from .env or use default
    verify_token = os.getenv("VERIFY_TOKEN", "1234")
    
    # Verify the webhook
    verify_webhook(webhook_url, verify_token)
    
    # Test sending a message to the webhook
    test_webhook_message(webhook_url)
    
    # Print instructions for configuring the webhook
    print_webhook_config_instructions() 