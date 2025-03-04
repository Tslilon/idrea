import logging
import json

from flask import Blueprint, request, jsonify, current_app

from .decorators.security import signature_required
from .utils.whatsapp_utils import (
    process_whatsapp_message,
    is_valid_whatsapp_message,
)

webhook_blueprint = Blueprint("webhook", __name__)


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
        logging.info(f"Processing webhook data in handle_message: {json.dumps(data, indent=2)}")
        
        # Check if this is a WhatsApp API event
        if "object" in data and data["object"] == "whatsapp_business_account":
            # Extract the message data
            if "entry" in data and len(data["entry"]) > 0:
                entry = data["entry"][0]
                logging.info(f"Processing entry: {json.dumps(entry, indent=2)}")
                
                if "changes" in entry and len(entry["changes"]) > 0:
                    change = entry["changes"][0]
                    logging.info(f"Processing change: {json.dumps(change, indent=2)}")
                    
                    if "value" in change:
                        value = change["value"]
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
                            logging.info("No messages found in the webhook payload")
                    else:
                        logging.warning("No 'value' field in the change object")
                else:
                    logging.warning("No 'changes' field in the entry object")
            else:
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
def webhook_get():
    return verify()

@webhook_blueprint.route("/webhook", methods=["POST"])
# Temporarily commenting out the signature_required decorator to see if that's the issue
# @signature_required
def webhook_post():
    logging.info("Received webhook POST request")
    try:
        # Log the raw request payload
        logging.info(f"Webhook payload: {request.get_data(as_text=True)}")
        
        # Get the request body
        data = request.get_json()
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
def health_check():
    """
    Simple health check endpoint to verify the application is running.
    """
    return jsonify({
        "status": "healthy",
        "version": "1.0.1",
        "environment": current_app.config.get("ENV", "production")
    }), 200


