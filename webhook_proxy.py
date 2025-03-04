import os
import requests
from flask import Flask, request, Response
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Get the target URL from environment variable or use default
TARGET_URL = os.getenv("TARGET_WEBHOOK_URL", "https://great-mangos-doubt.loca.lt/webhook")

@app.route('/webhook', methods=['GET', 'POST'])
def proxy():
    """
    Proxy webhook requests to the target URL
    """
    # Log the incoming request
    print(f"Received {request.method} request to /webhook")
    
    if request.method == 'GET':
        # Handle verification request
        hub_mode = request.args.get('hub.mode')
        hub_verify_token = request.args.get('hub.verify_token')
        hub_challenge = request.args.get('hub.challenge')
        
        print(f"Verification request: mode={hub_mode}, token={hub_verify_token}, challenge={hub_challenge}")
        
        # Forward the verification request
        target_url = f"{TARGET_URL}?hub.mode={hub_mode}&hub.verify_token={hub_verify_token}&hub.challenge={hub_challenge}"
        try:
            response = requests.get(target_url)
            print(f"Forwarded verification request to {target_url}")
            print(f"Response: {response.status_code} - {response.text}")
            return Response(response.text, status=response.status_code)
        except Exception as e:
            print(f"Error forwarding verification request: {str(e)}")
            return "Error", 500
    
    elif request.method == 'POST':
        # Handle webhook event
        try:
            # Get the request data
            data = request.get_json() if request.is_json else request.data
            headers = {key: value for key, value in request.headers if key != 'Host'}
            
            # Log the webhook payload
            print(f"Webhook payload: {data}")
            
            # Forward the webhook event
            response = requests.post(TARGET_URL, json=data, headers=headers)
            print(f"Forwarded webhook event to {TARGET_URL}")
            print(f"Response: {response.status_code} - {response.text}")
            
            return Response(response.text, status=response.status_code)
        except Exception as e:
            print(f"Error forwarding webhook event: {str(e)}")
            return "Error", 500

if __name__ == '__main__':
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port) 