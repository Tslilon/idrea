import logging
import json

from flask import Blueprint, request, jsonify, current_app
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from .decorators.security import signature_required
from .utils.whatsapp_utils import (
    process_whatsapp_message,
    is_valid_whatsapp_message,
)

webhook_blueprint = Blueprint("webhook", __name__)


def get_real_ip():
    """Get the real IP address from X-Forwarded-For header when behind a proxy"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    elif request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    else:
        return get_remote_address()


# Initialize limiter for this blueprint
limiter = Limiter(
    key_func=get_real_ip,
    storage_uri="memory://"
)


def handle_message():
    """
    Handle incoming webhook events from the WhatsApp API.

    This function processes incoming WhatsApp messages and other events,
    such as delivery statuses. If the event is a valid message, it gets
    processed. If the incoming payload is not a recognized WhatsApp event,
    it returns an error.
    """
    try:
        # Get the request body
        data = request.get_json()
        
        # Check if this contains actual messages or just status updates
        contains_messages = False
        if "object" in data and data["object"] == "whatsapp_business_account":
            if "entry" in data and len(data["entry"]) > 0:
                entry = data["entry"][0]
                if "changes" in entry and len(entry["changes"]) > 0:
                    change = entry["changes"][0]
                    if "value" in change:
                        value = change["value"]
                        if "messages" in value and len(value["messages"]) > 0:
                            contains_messages = True
        
        # Only log detailed info if this contains actual messages or debugging is enabled
        if contains_messages:
            logging.info(f"Processing webhook data with messages: {json.dumps(data, indent=2)}")
        else:
            # Minimal logging for status updates
            if "entry" in data and len(data["entry"]) > 0 and "changes" in data["entry"][0]:
                change = data["entry"][0]["changes"][0]
                if "value" in change and "statuses" in change["value"]:
                    status = change["value"]["statuses"][0]["status"]
                    msg_id = change["value"]["statuses"][0]["id"]
                    logging.debug(f"Status update: {status} for message {msg_id}")
        
        # Process all webhooks as before
        if "object" in data and data["object"] == "whatsapp_business_account":
            # Extract the message data
            if "entry" in data and len(data["entry"]) > 0:
                entry = data["entry"][0]
                if contains_messages:
                    logging.info(f"Processing entry: {json.dumps(entry, indent=2)}")
                
                if "changes" in entry and len(entry["changes"]) > 0:
                    change = entry["changes"][0]
                    if contains_messages:
                        logging.info(f"Processing change: {json.dumps(change, indent=2)}")
                    
                    if "value" in change:
                        value = change["value"]
                        if contains_messages:
                            logging.info(f"Processing value: {json.dumps(value, indent=2)}")
                        
                        # Check if there are messages
                        if "messages" in value and len(value["messages"]) > 0:
                            # Process each message
                            for message in value["messages"]:
                                logging.info(f"Processing message: {json.dumps(message, indent=2)}")
                                
                                # Validate the message format
                                if is_valid_whatsapp_message(message):
                                    # Process the message
                                    phone_number_id = value.get("metadata", {}).get("phone_number_id")
                                    logging.info(f"Using phone_number_id: {phone_number_id}")
                                    
                                    process_whatsapp_message(message, phone_number_id)
                                else:
                                    logging.warning(f"Invalid message format: {message}")
                        else:
                            if contains_messages:
                                logging.info("No messages found in the webhook payload")
                    else:
                        if contains_messages:
                            logging.warning("No 'value' field in the change object")
                else:
                    if contains_messages:
                        logging.warning("No 'changes' field in the entry object")
            else:
                if contains_messages:
                    logging.warning("No 'entry' field in the webhook payload")
            
            # Return a 200 OK response to acknowledge receipt of the event
            return jsonify({"status": "success"}), 200
        else:
            # Not a WhatsApp API event
            logging.warning(f"Received non-WhatsApp event: {data}")
            return jsonify({"status": "error", "message": "Not a WhatsApp API event"}), 400
    except Exception as e:
        logging.error(f"Error processing webhook: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500


# Required webhook verifictaion for WhatsApp
def verify():
    # Parse params from the webhook verification request
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    # Check if a token and mode were sent
    if mode and token:
        # Check the mode and token sent are correct
        if mode == "subscribe" and token == current_app.config["VERIFY_TOKEN"]:
            # Respond with 200 OK and challenge token from the request
            logging.info("WEBHOOK_VERIFIED")
            return challenge, 200
        else:
            # Responds with '403 Forbidden' if verify tokens do not match
            logging.info("VERIFICATION_FAILED")
            return jsonify({"status": "error", "message": "Verification failed"}), 403
    else:
        # Responds with '400 Bad Request' if verify tokens do not match
        logging.info("MISSING_PARAMETER")
        return jsonify({"status": "error", "message": "Missing parameters"}), 400


@webhook_blueprint.route("/webhook", methods=["GET"])
@limiter.limit("10 per minute")  # Allow webhook verification
def webhook_get():
    return verify()

@webhook_blueprint.route("/webhook", methods=["POST"])
@limiter.limit("100 per minute")  # Allow legitimate WhatsApp messages
# Temporarily commenting out the signature_required decorator to see if that's the issue
# @signature_required
def webhook_post():
    logging.info("Received webhook POST request")
    try:
        # Get the request body
        data = request.get_json()
        
        # Check if this contains actual messages or just status updates
        contains_messages = False
        if "object" in data and data["object"] == "whatsapp_business_account":
            if "entry" in data and len(data["entry"]) > 0:
                entry = data["entry"][0]
                if "changes" in entry and len(entry["changes"]) > 0:
                    change = entry["changes"][0]
                    if "value" in change:
                        value = change["value"]
                        if "messages" in value and len(value["messages"]) > 0:
                            contains_messages = True
        
        # Only log detailed webhook payload if it contains actual messages
        if contains_messages:
            # Log the raw request payload for actual messages
            logging.info(f"Webhook payload: {request.get_data(as_text=True)}")
            logging.info(f"Parsed webhook data: {json.dumps(data, indent=2)}")
        
        # Check if this is a WhatsApp API event
        if "object" in data and data["object"] == "whatsapp_business_account":
            # Process the message
            handle_message()
            return jsonify({"status": "success"}), 200
        else:
            # Not a WhatsApp API event
            logging.warning(f"Received non-WhatsApp event: {data}")
            return jsonify({"status": "error", "message": "Not a WhatsApp API event"}), 400
    except Exception as e:
        logging.error(f"Error processing webhook: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

# Add a simple health check endpoint
@webhook_blueprint.route("/health", methods=["GET"])
@limiter.limit("30 per minute")  # Allow health checks but limit scanning
def health_check():
    """
    Simple health check endpoint to verify the application is running.
    """
    return jsonify({
        "status": "healthy",
        "version": "1.0.1",
        "environment": current_app.config.get("ENV", "production")
    }), 200

# Add a rate-limited catch-all route for security scanning attempts
@webhook_blueprint.route('/', defaults={'path': ''})
@webhook_blueprint.route('/<path:path>')
@limiter.limit("5 per minute")  # Very restrictive for unknown paths
def catch_all(path):
    """
    Catch-all route for security scanning attempts.
    Returns 404 but logs the attempt for monitoring.
    """
    real_ip = get_real_ip()
    user_agent = request.headers.get('User-Agent', 'Unknown')
    logging.warning(f"Security scan attempt detected: {request.method} {request.url} from {real_ip} - User-Agent: {user_agent}")
    return jsonify({"error": "Not found"}), 404


