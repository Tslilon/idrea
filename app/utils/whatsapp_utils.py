from datetime import datetime
import logging
import os
import json
import requests
import re
import shelve
import uuid
from flask import request

from flask import current_app, jsonify
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

# Import our new receipt extraction service
from app.services.receipt_extraction_service import (
    format_extracted_details_for_whatsapp,
    prepare_for_google_sheets
)

# Additional imports and code
# from app.services.openai_service import generate_response
# from google.oauth2.credentials import Credentials
# from google_auth_oauthlib.flow import InstalledAppFlow
# from google.auth.transport.requests import Request
# from google.auth.exceptions import RefreshError


def log_http_response(response):
    logging.info(f"Status: {response.status_code}")
    logging.info(f"Content-type: {response.headers.get('content-type')}")
    logging.info(f"Body: {response.text}")


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


def update_admins(update_text, senders_number):
    # Update the admins of the image sent:
    # try:
    admins = os.getenv("RECIPIENT_WAID")
    admins = admins.split(",")
    print(admins)
    for admin in admins:
        data_admin = get_text_message_input(admin, update_text)
        if admin != senders_number:
            send_message(data_admin)
    # except:
    #     pass


def generate_response(message_body):
    # Define the expected format
    expected_format = ["What", "Amount"]

    # Check if the message follows the expected format
    if all(item in message_body for item in expected_format):
        return "Processing your update..."
    else:
        return None


def send_message(data):
    headers = {
        "Content-type": "application/json",
        "Authorization": f"Bearer {os.getenv('ACCESS_TOKEN')}",
    }

    url = f"https://graph.facebook.com/{os.getenv('VERSION')}/{os.getenv('PHONE_NUMBER_ID')}/messages"

    try:
        response = requests.post(
            url, data=data, headers=headers, timeout=10
        )  # 10 seconds timeout as an example
        response.raise_for_status()  # Raises an HTTPError if the HTTP request returned an unsuccessful status code
    except requests.Timeout:
        logging.error("Timeout occurred while sending message")
        return jsonify({"status": "error", "message": "Request timed out"}), 408
    except (
            requests.RequestException
    ) as e:  # This will catch any general request exception
        logging.error(f"Request failed due to: {e}")
        return jsonify({"status": "error", "message": "Failed to send message"}), 500
    else:
        # Process the response as normal
        log_http_response(response)
        return response


def process_text_for_whatsapp(text):
    # Remove brackets
    pattern = r"\【.*?\】"
    # Substitute the pattern with an empty string
    text = re.sub(pattern, "", text).strip()

    # Pattern to find double asterisks including the word(s) in between
    pattern = r"\*\*(.*?)\*\*"

    # Replacement pattern with single asterisks
    replacement = r"*\1*"

    # Substitute occurrences of the pattern with the replacement
    whatsapp_style_text = re.sub(pattern, replacement, text)

    return whatsapp_style_text


def upload_image_to_drive(credentials, folder_id, file_path, file_name):
    if credentials is None:
        logging.error("Cannot upload to Google Drive: credentials are not available")
        return None
    
    try:
        service = build('drive', 'v3', credentials=credentials)
        file_metadata = {
            'name': file_name,
            'parents': [folder_id]
        }
        media = MediaFileUpload(file_path, mimetype='image/jpeg')  # Adjust mimetype if necessary
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        file_id = file.get('id')
        logging.info(f"File uploaded to Google Drive with ID: {file_id}")
        
        # Create and return a shareable link
        drive_link = f"https://drive.google.com/file/d/{file_id}/view"
        return drive_link
    except Exception as e:
        logging.error(f"Error uploading file to Google Drive: {str(e)}")
        return None


def process_whatsapp_message(message, phone_number_id):
    """
    Process a WhatsApp message.
    
    Args:
        message: The message object
        phone_number_id: The phone number ID to use for sending responses
    """
    try:
        # Log the message for debugging
        logging.info(f"Processing message: {json.dumps(message, indent=2)}")
        
        # Check if the message is valid
        if not is_valid_whatsapp_message(message):
            logging.error("Invalid message format")
            return
        
        # Get the sender's WhatsApp ID
        sender_waid = message.get("from")
        if not sender_waid:
            logging.error("No sender ID found in the message")
            return
        
        # Format the sender ID with a plus sign if needed
        if not sender_waid.startswith("+"):
            sender_waid = f"+{sender_waid}"
        
        # Load credentials for Google services
        creds = load_credentials()
        if creds is None:
            logging.warning("Google API credentials not available. Some functionality will be limited.")
            # We'll continue processing but functions that require credentials will handle the None case
        
        folder_id = os.getenv("GOOGLE_FOLDER_ID")
        sheet_id = os.getenv("GOOGLE_SHEET_ID")
        
        # Get the message type
        message_type = message.get("type")
        
        # Get contact information if available
        # Try to get the actual name from the contacts field if available
        name = "User"  # Default name
        
        try:
            # Extract name from the contacts field
            contacts = message.get("contacts", [])
            if contacts and len(contacts) > 0:
                profile = contacts[0].get("profile", {})
                if profile and "name" in profile:
                    name = profile["name"]
                    logging.info(f"Found contact name from message: {name}")
            
            # If we didn't find the name in the message directly, it might be in the parent data structure
            if name == "User" and hasattr(request, 'json') and request.json:
                data = request.json
                if "entry" in data and len(data["entry"]) > 0:
                    entry = data["entry"][0]
                    if "changes" in entry and len(entry["changes"]) > 0:
                        change = entry["changes"][0]
                        if "value" in change and "contacts" in change["value"] and len(change["value"]["contacts"]) > 0:
                            profile = change["value"]["contacts"][0].get("profile", {})
                            if profile and "name" in profile:
                                name = profile["name"]
                                logging.info(f"Found contact name from request: {name}")
        except Exception as e:
            logging.error(f"Error getting contact name: {str(e)}")
        
        logging.info(f"Using name: {name} for sender: {sender_waid}")
        
        # Process different message types
        if message_type == "text":
            # Handle text message
            try:
                text = message["text"]["body"]
                logging.info(f"Received text message: {text}")
                
                # Update the admins
                update_admins(f"{name} sent:\n\n{text}", sender_waid)
                
                # Process the text message
                process_text_message(text, name, creds, sender_waid)
            except Exception as e:
                logging.error(f"Error processing text message: {str(e)}")
                data = get_text_message_input(sender_waid, "I encountered an error while processing your message. Please try again.")
                send_message(data)
        
        elif message_type == "image":
            # Handle image message
            try:
                logging.info("Processing image message")
                process_image_message(message, name, creds, sender_waid, folder_id)
            except Exception as e:
                logging.error(f"Error processing image message: {str(e)}")
                data = get_text_message_input(sender_waid, "I encountered an error while processing your image. Please try again.")
                send_message(data)
        
        elif message_type == "document":
            # Handle document message
            try:
                logging.info("Processing document message")
                process_document_message(message, name, creds, sender_waid, folder_id)
            except Exception as e:
                logging.error(f"Error processing document message: {str(e)}")
                data = get_text_message_input(sender_waid, "I encountered an error while processing your document. Please try again.")
                send_message(data)
        
        else:
            # Handle unsupported message type
            logging.warning(f"Unsupported message type: {message_type}")
            data = get_text_message_input(sender_waid, "I don't support this type of message yet. Please send a text message, image, or document.")
            send_message(data)
    
    except Exception as e:
        logging.error(f"Error processing WhatsApp message: {str(e)}")
        return


def get_document_url_from_whatsapp(document_id):
    """
    Fetches the URL of a document from WhatsApp using the document ID.

    Parameters:
    document_id (str): The ID of the document.

    Returns:
    str: The URL of the document, or None if the request fails.
    """
    url = f"https://graph.facebook.com/v20.0/{document_id}"  # Updated to v20.0
    headers = {
        "Authorization": f"Bearer {os.getenv('ACCESS_TOKEN')}",
    }

    try:
        logging.info(f"Fetching document URL for document ID: {document_id}")
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            document_data = response.json()
            document_url = document_data.get("url")
            if document_url:
                logging.info(f"Successfully retrieved document URL (first 50 chars): {document_url[:50]}...")
                return document_url
            else:
                logging.error(f"No URL found in the response: {document_data}")
                return None
        else:
            logging.error(f"Error fetching document URL: Status code {response.status_code}, Response: {response.text[:200]}")
            return None
    except Exception as e:
        logging.error(f"Exception fetching document URL: {str(e)}")
        return None


def upload_document_to_drive(credentials, folder_id, file_path, file_name):
    if credentials is None:
        logging.error("Cannot upload to Google Drive: credentials are not available")
        return None
    
    try:
        # Similar to upload_image_to_drive but adjust mimetype for PDFs
        mimetype = 'application/pdf'  # For PDF files

        service = build('drive', 'v3', credentials=credentials)
        file_metadata = {'name': file_name, 'parents': [folder_id]}
        media = MediaFileUpload(file_path, mimetype=mimetype)
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        file_id = file.get('id')
        logging.info(f"Document uploaded to Google Drive with ID: {file_id}")
        
        # Create and return a shareable link
        drive_link = f"https://drive.google.com/file/d/{file_id}/view"
        return drive_link
    except Exception as e:
        logging.error(f"Error uploading document to Google Drive: {str(e)}")
        return None


def download_document(document_url):
    """
    Download a document from a given URL.

    Parameters:
    document_url (str): The URL of the document to download.

    Returns:
    response: The response object containing the document content.
    """
    headers = {
        "Authorization": f"Bearer {os.getenv('ACCESS_TOKEN')}",
        "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
    }

    try:
        logging.info(f"Downloading document from URL (first 50 chars): {document_url[:50]}...")
        response = requests.get(document_url, headers=headers, timeout=30, stream=True)
        
        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '')
            logging.info(f"Downloaded content type: {content_type}")
            
            if 'text/html' in content_type:
                logging.error(f"Received HTML instead of document data. Response: {response.text[:200]}")
                return None
                
            return response
        else:
            logging.error(f"Failed to download document: Status code {response.status_code}, Response: {response.text[:200]}")
            return None
    except requests.RequestException as e:
        logging.error(f"Request failed during document download: {str(e)}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error during document download: {str(e)}")
        return None


def process_text_message(text, name, creds, sender_waid):
    """
    Process a text message from WhatsApp.
    
    Args:
        text: The message text
        name: The sender's name
        creds: Google API credentials
        sender_waid: The sender's WhatsApp ID
    """
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    logging.info(f"Processing text message: '{text}' from {sender_waid}, name: {name}")
    
    # Check if we have stored receipt details for this user
    stored_receipt = get_stored_receipt(sender_waid)
    
    # Handle confirmation responses
    text_lower = text.lower().strip()
    
    # Handle confirmation keywords
    if text_lower in ["confirm", "yes"]:
        if stored_receipt:
            # User is confirming extracted receipt details
            logging.info("User confirming receipt details")
            
            # Get the receipt number that was created earlier
            # Prepare the data from previously extracted receipt
            update_data = [stored_receipt.get("sender_name", name)]  # Use stored name or fallback to current name
            
            fields_to_process = ["what", "amount", "iva", "receipt", "store_name", "payment_method", "charge_to", "comments"]
            for field in fields_to_process:
                update_data.append(stored_receipt.get(field, ""))
            
            # Remove the stored receipt
            delete_stored_receipt(sender_waid)
            
            # Write to Google Sheets
            receipt_num = append_to_sheet(creds, sheet_id, update_data)
            
            # Send confirmation
            first_name = get_first_name(name)
            confirm_message = f"Thank you {first_name}! I've saved your receipt details. Your receipt number is {receipt_num}."
            data = get_text_message_input(sender_waid, confirm_message)
            send_message(data)
            
            # Update admins
            admin_message = f"{name} confirmed receipt details. Receipt {receipt_num} added to spreadsheet."
            update_admins(admin_message, sender_waid)
            
            return
        else:
            # No stored receipt details for this user
            first_name = get_first_name(name)
            data = get_text_message_input(sender_waid, f"I'm sorry {first_name}, I don't have any pending receipt details to confirm. You can send a new receipt image or enter details manually.")
            send_message(data)
            return
    
    # Handle cancellation responses
    elif text_lower in ["cancel", "no"]:
        if stored_receipt:
            # User wants to cancel the receipt
            logging.info("User cancelling receipt")
            
            # Check if there's a drive link to delete
            drive_link = stored_receipt.get("drive_link", "")
            if drive_link:
                # Extract file ID from drive link
                # Drive links are in the format: https://drive.google.com/file/d/FILE_ID/view
                try:
                    file_id = drive_link.split("/d/")[1].split("/")[0]
                    delete_result = delete_file_from_drive(creds, file_id)
                    if delete_result:
                        logging.info(f"Deleted receipt file {file_id} from Drive during cancellation")
                    else:
                        logging.warning(f"Failed to delete receipt file {file_id} from Drive during cancellation")
                except Exception as e:
                    logging.error(f"Error extracting file ID from drive link: {str(e)}")
            
            # Remove the stored receipt
            delete_stored_receipt(sender_waid)
            
            # Send confirmation of cancellation
            first_name = get_first_name(name)
            cancel_message = f"Okay {first_name}, I've cancelled this receipt. All information and uploaded files have been deleted."
            data = get_text_message_input(sender_waid, cancel_message)
            send_message(data)
            
            # Update admins
            admin_message = f"{name} cancelled their receipt submission."
            if drive_link:
                admin_message += " The uploaded file was deleted from Drive."
            update_admins(admin_message, sender_waid)
            
            return
        else:
            # No stored receipt details for this user
            first_name = get_first_name(name)
            data = get_text_message_input(sender_waid, f"I'm sorry {first_name}, I don't have any pending receipt details to cancel. You can send a new receipt image or enter details manually.")
            send_message(data)
            return
    
    # Handle field updates for an existing receipt
    elif stored_receipt and not (text_lower in ["confirm", "yes", "cancel", "no"]):
        # User is providing updates to receipt fields
        logging.info("User providing receipt detail updates")
        
        # Check for field patterns like "Field: value"
        updates = {}
        lines = text.split('\n')
        
        for line in lines:
            # Look for field: value patterns
            match = re.match(r'(.*?):\s*(.*)', line.strip())
            if match:
                field_name = match.group(1).strip().lower()
                field_value = match.group(2).strip()
                
                # Map user-friendly field names to internal names
                field_mapping = {
                    "what": "what",
                    "amount": "amount",
                    "iva": "iva",
                    "store name": "store_name",
                    "payment method": "payment_method",
                    "charge to": "charge_to", 
                    "comments": "comments"
                }
                
                if field_name in field_mapping:
                    normalized_field = field_mapping[field_name]
                    
                    # Format amount and IVA fields to ensure proper number formatting
                    if field_name in ["amount", "iva"]:
                        try:
                            # Try to parse as number and format
                            clean_value = field_value.replace('€', '').replace(',', '.').strip()
                            value_float = float(clean_value)
                            field_value = f"{value_float:.2f} €"
                        except ValueError:
                            # If not a valid number, keep as is but log
                            logging.warning(f"Invalid number format for {field_name}: {field_value}")
                    
                    updates[normalized_field] = field_value
                    logging.info(f"Updating field {normalized_field} to {field_value}")
        
        # Update the stored receipt with the new values
        if updates:
            current_receipt = get_stored_receipt(sender_waid)
            for field, value in updates.items():
                current_receipt[field] = value
            store_extracted_receipt(sender_waid, current_receipt, name)
            
            # Format the updated receipt details
            updated_message = format_extracted_details_for_whatsapp(current_receipt)
            
            # Show what fields were updated
            changes = [f"✓ {field.title().replace('_', ' ')}: {value}" for field, value in updates.items()]
            update_confirmation = "Updated:\n" + "\n".join(changes)
            
            response = (
                f"{update_confirmation}\n\n"
                f"Updated receipt details:\n\n"
                f"{updated_message}\n\n"
                f"Reply \"yes\" or \"confirm\" to finalize or continue editing."
            )
            data = get_text_message_input(sender_waid, response)
            send_message(data)
            
            return
        else:
            # No valid fields found to update
            response = (
                f"I couldn't identify any fields to update. Please use this format:\n\n"
                f"Payment method: [cash/card/transfer]\n"
                f"Charge to: [personal/company/project]\n"
                f"Comments: [any additional notes]"
            )
            data = get_text_message_input(sender_waid, response)
            send_message(data)
            
            return

    # Define field mappings for flexible matching
    field_mappings = {
        "what": "What",
        "amount": "Amount",
        "amount (euros)": "Amount",
        "iva": "IVA",
        "iva (euros)": "IVA",
        "receipt": "Receipt",
        "store name": "Store name",
        "payment method": "Payment method",
        "charge to": "Charge to",
        "comments": "Comments"
    }
    
    # Check if this looks like a receipt form submission - use case-insensitive matching
    form_fields = ["what", "amount", "store name"]
    form_detected = sum(1 for field in form_fields if field in text_lower) >= 2
    
    logging.info(f"Form detected: {form_detected}")
    
    if form_detected:
        # This looks like a form submission, so parse it and save to Google Sheets
        parts = text.split('\n')
        update_data = [name]  # Use the actual name from WhatsApp
        
        logging.info(f"Form detected. Using sender name: {name}")
        
        # Create a dictionary to store the parsed fields
        parsed_data = {}
        for part in parts:
            if not part.strip():
                continue
                
            # Find the partition between key and value
            partition_index = part.find(':')
            if partition_index == -1:
                continue
                
            # Extract key and value
            key = part[:partition_index].strip()
            value = part[partition_index+1:].strip()
            
            # Skip if value is empty
            if not value:
                continue
                
            # Clean up the key (remove formatting)
            key = key.replace('*', '')
            
            # Normalize the key using our mappings (case-insensitive)
            key_lower = key.lower()
            if key_lower in field_mappings:
                normalized_key = field_mappings[key_lower]
                parsed_data[normalized_key] = value
                logging.info(f"Mapped field '{key}' to '{normalized_key}' with value '{value}'")
            else:
                # If no mapping found, use the original key
                parsed_data[key] = value
                logging.info(f"Using original field '{key}' with value '{value}'")
        
        # Check if we have the minimal required fields
        required_fields = ["What", "Amount"]
        missing_fields = [field for field in required_fields if field not in parsed_data]
        
        if missing_fields:
            # Send message about missing fields
            missing_text = ", ".join(missing_fields)
            text = f"Please provide the missing fields: {missing_text}. Your form submission is incomplete."
            data = get_text_message_input(sender_waid, text)
            send_message(data)
            return
        
        # Process the data for Google Sheets
        fields_to_process = ["What", "Amount", "IVA", "Receipt", "Store name", "Payment method", "Charge to", "Comments"]
        
        for field in fields_to_process:
            value = parsed_data.get(field, "")
            
            # Process numeric fields - but don't convert format here, just clean up
            # The conversion to European format will happen in append_to_sheet
            if field in ["Amount", "IVA"] and value:
                # Clean up any text around numbers
                # We'll leave the actual number formatting (commas/periods) as is
                # Just remove currency symbols and other non-numeric chars except . and ,
                value = re.sub(r'[^\d.,\-]', '', value)
                
                # If value starts with a comma or period, add a 0 before it
                if value.startswith('.') or value.startswith(','):
                    value = '0' + value
                
                # If value ends with a comma or period, remove it
                if value.endswith('.') or value.endswith(','):
                    value = value[:-1]
            
            update_data.append(value)
        
        # Write to Google Sheets
        receipt_num = append_to_sheet(creds, sheet_id, update_data)
        
        # Send confirmation to user with receipt number
        text = f'Receipt details saved! Receipt #{receipt_num} has been added to our system. If you have a receipt image/pdf, please send it with "{receipt_num}" in the caption.'
        data = get_text_message_input(sender_waid, text)
        send_message(data)
        
        # Update admins
        update_admins(f"Receipt #{receipt_num} added by {name}", sender_waid)
        
        # Clean up any stored receipt details
        delete_stored_receipt(sender_waid)
    else:
        # If it's not a form submission, send the form template
        logging.info(f"Sending form template to {sender_waid}")
        first_name = get_first_name(name)
        template_message = (f"Hi {first_name}! Please provide the receipt details in the following format:\n\n"
                "*What*: \n"
                "*Amount* (euros): \n"
                "IVA (euros): \n"
                "Receipt: yes\n"
                "Store name: \n"
                "Payment method: \n"
                "Charge to: \n"
                "Comments: \n\n"
                "or send the receipt image/pdf.\n"
                "Do not include a caption for automatic extraction.")
        logging.info(f"Template message: {template_message[:50]}...")
        data = get_text_message_input(sender_waid, template_message)
        response = send_message(data)
        logging.info(f"Template message response: {response.status_code}")
        logging.info(f"Template message response body: {response.text[:100]}")


def parse_manual_receipt_entry(text):
    """
    Parse a manual receipt entry from the user.
    Expected format is a series of lines with "Field: Value"
    
    Args:
        text: The message text from the user
        
    Returns:
        Dictionary with parsed receipt details
    """
    # Define field mappings (WhatsApp field name -> internal field name)
    field_mappings = {
        "Store name": "store_name",
        "Amount": "total_amount",
        "IVA": "iva",
        "Receipt": "has_receipt",
        "Payment method": "payment_method",
        "Charge to": "charge_to",
        "Comments": "comments",
        "Date": "date",
        "What": "description"
    }
    
    # Initialize result dictionary
    result = {}
    
    # Split text into lines
    lines = text.split('\n')
    
    # Process each line
    for line in lines:
        # Skip empty lines
        if not line.strip():
            continue
            
        # Find the partition between key and value
        partition_index = line.find(':')
        if partition_index == -1:
            continue
            
        # Extract key and value
        key = line[:partition_index].strip()
        value = line[partition_index+1:].strip()
        
        # Skip if either key or value is empty
        if not key or not value:
            continue
            
        # Remove any formatting like * for bold
        key = key.replace('*', '')
        
        # Map the field name if possible
        internal_key = field_mappings.get(key)
        if not internal_key:
            # Try case-insensitive match
            for k, v in field_mappings.items():
                if k.lower() == key.lower():
                    internal_key = v
                    break
                    
        if not internal_key:
            # Still not found, just use the key directly
            internal_key = key.lower().replace(' ', '_')
            
        # Process special fields
        if internal_key == "total_amount" or internal_key == "iva":
            # Replace comma with period for decimal
            value = value.replace(',', '.')
            # Remove the last character if it is a period
            if value.endswith('.'):
                value = value[:-1]
            # If there are two periods, remove the first one
            if value.count('.') == 2:
                first_period_index = value.find('.')
                value = value[:first_period_index] + value[first_period_index + 1:]
            # Remove non-numeric characters
            value = re.sub(r'[^\d.]+', '', value)
                
        elif internal_key == "has_receipt":
            # Convert yes/no or true/false to boolean
            value = value.lower() in ["yes", "true", "1", "y"]
            
        # Store the value
        result[internal_key] = value
        
    return result


def is_valid_whatsapp_message(message):
    """
    Check if the message object has a valid WhatsApp message structure.
    
    Args:
        message: A single message object from the webhook payload
        
    Returns:
        bool: True if the message has a valid structure, False otherwise
    """
    # Check if this is a valid WhatsApp message (has text, image, or document component)
    return bool(
        (message.get("type") == "text" and message.get("text")) or
        (message.get("type") == "image" and message.get("image")) or
        (message.get("type") == "document" and message.get("document")) or
        (message.get("type") == "audio" and message.get("audio")) or
        (message.get("type") == "video" and message.get("video"))
    )


SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
google_creds_json = 'data/credentials.json'


def get_client_info():
    try:
        with open(google_creds_json) as f:
            data = json.load(f)
        
        # Try to get credentials from both standard OAuth and service account formats
        if 'installed' in data:
            # OAuth client format
            client_id = data['installed']['client_id']
            client_secret = data['installed']['client_secret']
            return client_id, client_secret
        elif 'client_id' in data:
            # Service account format - extract client_id directly
            client_id = data['client_id']
            # No client_secret in service accounts but we need a value
            client_secret = "service_account"
            logging.info("Using service account client ID for OAuth operations")
            return client_id, client_secret
        else:
            logging.warning(f"No recognized credential format found in {google_creds_json}")
            return None, None
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        logging.warning(f"Error loading OAuth credentials: {str(e)}")
        return None, None


# Initialize CLIENT_ID and CLIENT_SECRET, but don't fail if they're not available
CLIENT_ID, CLIENT_SECRET = get_client_info()


def refresh_access_token(refresh_token):
    if not CLIENT_ID or not CLIENT_SECRET:
        logging.error("Cannot refresh token: OAuth client credentials not available")
        return None, None
        
    params = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',
    }
    response = requests.post('https://oauth2.googleapis.com/token', data=params)
    if response.status_code == 200:
        new_tokens = response.json()
        return new_tokens['access_token'], new_tokens.get('refresh_token', refresh_token)
    else:
        print(f"Failed to refresh token: {response.content}")
        return None, None


from google.oauth2 import service_account
import googleapiclient.discovery


def load_credentials():
    try:
        SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE')
        if not SERVICE_ACCOUNT_FILE or not os.path.exists(SERVICE_ACCOUNT_FILE):
            logging.error(f"Service account file not found at {SERVICE_ACCOUNT_FILE}. Authentication will fail.")
            return None
        
        # Define the scopes required by your application
        SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']

        # Load the JSON content and create credentials from it
        try:
            with open(SERVICE_ACCOUNT_FILE, 'r') as json_file:
                service_account_info = json.load(json_file)
            
            # Create credentials directly from the parsed JSON
            creds = service_account.Credentials.from_service_account_info(
                service_account_info,
                scopes=SCOPES
            )
            logging.info(f"Successfully loaded credentials from service account info")
            return creds
        except json.JSONDecodeError as json_error:
            logging.error(f"Invalid JSON in service account file: {str(json_error)}")
            return None
        except Exception as load_error:
            logging.error(f"Failed to create credentials from service account info: {str(load_error)}")
            return None
    except Exception as e:
        logging.error(f"Error loading service account credentials: {str(e)}")
        return None


def get_receipt_number(credentials, sheet_id):
    if credentials is None:
        logging.error("Cannot get receipt number: credentials are not available")
        return None
    
    try:
        service = build('sheets', 'v4', credentials=credentials)

        # Specify the sheet and range to read.
        range_to_read = 'iDrea!A2:A'  # Assuming 'A2:A' contains receipt numbers, adjust as needed

        # Call the Sheets API to read data
        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=sheet_id,
                range=range_to_read).execute()
                
            values = result.get('values', [])

            # Extract receipt numbers and find the max
            receipt_numbers = [int(row[0]) for row in values if row and row[0].isdigit()]
            max_receipt_number = max(receipt_numbers, default=0)  # Default to 0 if list is empty

            return max_receipt_number + 1
        except HttpError as api_error:
            if "invalid_grant" in str(api_error) and "JWT Signature" in str(api_error):
                logging.error(f"JWT Signature error: {str(api_error)}")
                # Try to reload credentials
                logging.info("Attempting to reload credentials and retry...")
                new_credentials = load_credentials()
                if new_credentials:
                    # Recursive call with new credentials - only retry once
                    logging.info("Retrying with new credentials")
                    return get_receipt_number(new_credentials, sheet_id)
                else:
                    logging.error("Failed to reload credentials")
                    return None
            else:
                # Other API errors
                logging.error(f"Google API error getting receipt number: {str(api_error)}")
                return None
    except Exception as e:
        logging.error(f"Error getting receipt number: {str(e)}")
        return None


def append_to_sheet(credentials, sheet_id, values_list):
    if credentials is None:
        logging.error("Cannot append to Google Sheet: credentials are not available")
        return None
    
    try:
        service = build('sheets', 'v4', credentials=credentials)

        # Specify the sheet and the range where data will be appended.
        range = 'iDrea!A:K'  # Update this with your actual sheet name and range

        # Convert timestamp to readable format
        time = datetime.now().strftime('%Y-%m-%d %H:%M')

        # Get the next receipt number
        next_receipt_number = get_receipt_number(credentials, sheet_id)
        if next_receipt_number is None:
            logging.error("Failed to get next receipt number")
            return None
        
        # Process values but with minimal formatting - preserve exact decimal values
        processed_values = []
        for value in values_list:
            if isinstance(value, str) and value:
                # Check if this looks like a numeric value (amount or IVA)
                # First, standardize to US format (period as decimal) for processing
                cleaned_value = value.strip()
                
                # Convert comma to period for standard processing
                if ',' in cleaned_value:
                    cleaned_value = cleaned_value.replace(',', '.')
                
                # Now check if it's a valid number
                if cleaned_value and (cleaned_value.replace('.', '', 1).isdigit() or 
                                    (cleaned_value.startswith('-') and cleaned_value[1:].replace('.', '', 1).isdigit())):
                    try:
                        # Parse as float for standardization
                        num_value = float(cleaned_value)
                        
                        # Just save the exact value as a string with European formatting (comma as decimal)
                        # This is the simplest approach to preserve exact values
                        euro_format = str(num_value).replace('.', ',')
                        
                        processed_values.append(euro_format)
                        logging.info(f"Formatted number (simple): {value} -> {euro_format}")
                    except ValueError:
                        # If conversion fails, keep the original
                        processed_values.append(value)
                        logging.info(f"Could not convert to number, keeping original: {value}")
                else:
                    processed_values.append(value)  # Non-string values
            else:
                processed_values.append(value)  # Non-string values

        # Prepare the data to append.
        values = [next_receipt_number, time] + processed_values
        body = {'values': [values]}

        # Log the values being sent to Google Sheets
        logging.info(f"Appending to Google Sheet: {values}")

        # Call the Sheets API
        result = service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=range,
            valueInputOption='USER_ENTERED',
            body=body).execute()

        logging.info(f"{result.get('updates').get('updatedCells')} cells appended.")
        
        return next_receipt_number
    except Exception as e:
        logging.error(f"Error appending to Google Sheet: {str(e)}")
        return None


def get_image_url_from_whatsapp(image_id):
    """
    Fetches the URL of an image from WhatsApp using the image ID.

    Parameters:
    image_id (str): The ID of the image.
    access_token (str): Access token for the WhatsApp Business API.

    Returns:
    str: The URL of the image.
    """
    url = f"https://graph.facebook.com/v20.0/{image_id}"  # Updated to v20.0
    headers = {
        "Authorization": f"Bearer {os.getenv('ACCESS_TOKEN')}",
    }

    try:
        logging.info(f"Fetching image URL for image ID: {image_id}")
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            image_data = response.json()
            image_url = image_data.get("url")
            if image_url:
                logging.info(f"Successfully retrieved image URL (first 50 chars): {image_url[:50]}...")
                return image_url
            else:
                logging.error(f"No URL found in the response: {image_data}")
                return None
        else:
            logging.error(f"Error fetching image URL: Status code {response.status_code}, Response: {response.text[:200]}")
            return None
    except Exception as e:
        logging.error(f"Exception fetching image URL: {str(e)}")
        return None


# Remove the receipt storage functions since we won't need approval
# Instead, we'll store temporary extracted data to assist the user

def store_extracted_receipt(wa_id, receipt_details, sender_name="User"):
    """Store extracted receipt details for a user
    
    Args:
        wa_id: The WhatsApp ID of the user
        receipt_details: The receipt details dictionary
        sender_name: The name of the sender (defaults to "User")
    """
    # Log receipt details before modification
    logging.info(f"Storing receipt details (before modification): {receipt_details}")
    
    # Make a copy of the receipt details to avoid modifying the original
    modified_details = receipt_details.copy()
    
    # Add the sender's name to the receipt details
    modified_details["sender_name"] = sender_name
    
    # Ensure receipt=yes is set
    modified_details["receipt"] = "yes"
    
    # Ensure consistent field naming
    # Check for total_amount and map it to amount if amount doesn't exist
    if "total_amount" in modified_details and "amount" not in modified_details:
        modified_details["amount"] = modified_details["total_amount"]
        logging.info(f"Mapped total_amount to amount: {modified_details['amount']}")
    
    # Ensure amount and IVA values just have currency symbols removed, no other formatting
    for field in ["amount", "total_amount", "iva"]:
        if field in modified_details and modified_details[field]:
            # Ensure the value is a string
            value = str(modified_details[field])
            
            # Remove any currency symbols but keep everything else as is
            modified_details[field] = value.replace('€', '').strip()
            logging.info(f"Cleaned {field} value: {value} -> {modified_details[field]}")
    
    # Log final receipt details after modification
    logging.info(f"Storing receipt details (after modification): {modified_details}")
    
    with shelve.open("receipts_db", writeback=True) as receipts_shelf:
        receipts_shelf[wa_id] = modified_details

def get_stored_receipt(wa_id):
    """Retrieve stored receipt details for a user."""
    with shelve.open("receipts_db") as receipts_shelf:
        return receipts_shelf.get(wa_id, None)

def delete_stored_receipt(wa_id):
    """Delete stored receipt details for a user after processing."""
    with shelve.open("receipts_db", writeback=True) as receipts_shelf:
        if wa_id in receipts_shelf:
            del receipts_shelf[wa_id]


def process_image_message(message, name, creds, sender_waid, folder_id):
    """
    Process an image message from WhatsApp.
    
    Args:
        message: The image message object
        name: The sender's name
        creds: Google API credentials
        sender_waid: The sender's WhatsApp ID
        folder_id: Google Drive folder ID for storing images
    """
    try:
        # Get image information
        image_id = message["image"]["id"]
        caption = message["image"].get("caption", "").strip()
        
        logging.info(f"Processing image with ID: {image_id}, Caption: {caption}")
        
        # Get the image URL from WhatsApp
        image_url = get_image_url_from_whatsapp(image_id)
        
        if not image_url:
            logging.error("Failed to get image URL from WhatsApp")
            data = get_text_message_input(sender_waid, "I couldn't download your image. Please try again.")
            send_message(data)
            return
        
        # Download the image with proper error handling
        try:
            logging.info(f"Downloading image from URL (first 50 chars): {image_url[:50]}...")
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                "Authorization": f"Bearer {os.getenv('ACCESS_TOKEN')}"
            }
            response = requests.get(image_url, headers=headers, timeout=30, stream=True)
            
            if response.status_code != 200:
                logging.error(f"Failed to download image: Status code {response.status_code}, Response: {response.text[:200]}")
                data = get_text_message_input(sender_waid, "I couldn't download your image. Please try again.")
                send_message(data)
                return
            
            # Check if we got actual image data
            content_type = response.headers.get('Content-Type', '')
            logging.info(f"Downloaded content type: {content_type}")
            
            if 'text/html' in content_type:
                logging.error(f"Received HTML instead of image data. Response: {response.text[:200]}")
                data = get_text_message_input(sender_waid, "I couldn't download your image. Please try again.")
                send_message(data)
                return
            
            # Determine file extension based on content type
            extension = ".jpg"  # Default extension
            if content_type:
                if 'image/png' in content_type:
                    extension = ".png"
                elif 'image/gif' in content_type:
                    extension = ".gif"
                elif 'image/webp' in content_type:
                    extension = ".webp"
                elif 'image/jpeg' in content_type:
                    extension = ".jpg"
                # Add more mappings as needed
            
            # Save the image temporarily
            temp_dir = "data/temp_receipts"
            os.makedirs(temp_dir, exist_ok=True)
            
            # Process differently based on whether a caption was provided or not
            if caption:
                # Use the caption directly as part of the filename
                safe_caption = re.sub(r'[^\w\s-]', '', caption).replace(' ', '_')
                file_path = os.path.join(temp_dir, f"{safe_caption}{extension}")
                
                with open(file_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                logging.info(f"Image saved temporarily to {file_path}")
                
                # Upload to Google Drive
                file_name = f"{safe_caption}{extension}"
                drive_link = upload_image_to_drive(creds, folder_id, file_path, file_name)
                
                if drive_link:
                    # Send confirmation message
                    first_name = get_first_name(name)
                    confirmation_message = f"Thank you {first_name}! Your receipt image for #{safe_caption} has been saved to Google Drive."
                    data = get_text_message_input(sender_waid, confirmation_message)
                    send_message(data)
                    
                    # Update admins
                    admin_message = f"{name} sent a receipt image for #{safe_caption}.\nDrive link: {drive_link}"
                    update_admins(admin_message, sender_waid)
                else:
                    first_name = get_first_name(name)
                    data = get_text_message_input(sender_waid, f"I'm sorry {first_name}, I couldn't save your receipt image to Google Drive. Please try again.")
                    send_message(data)
                
                # Clean up the temporary file
                try:
                    os.remove(file_path)
                    logging.info(f"Temporary file {file_path} removed")
                except Exception as e:
                    logging.error(f"Error removing temporary file: {str(e)}")
            else:
                # No caption, process as a new receipt
                file_path = os.path.join(temp_dir, f"receipt_temp_{uuid.uuid4()}{extension}")
                
                with open(file_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                logging.info(f"Image saved temporarily to {file_path}")
                
                # Process the image for receipt extraction
                try:
                    # First, get a single receipt number to use for both the file and the receipt
                    receipt_number = get_receipt_number(creds, os.getenv("GOOGLE_SHEET_ID"))
                    filename = f"{receipt_number}{extension}"
                    
                    # Upload to Google Drive
                    drive_link = upload_image_to_drive(creds, folder_id, file_path, filename)
                    logging.info(f"Image uploaded to Google Drive: {drive_link}")
                    
                    # Now extract receipt details using OCR/AI
                    from app.services.receipt_extraction_service import extract_receipt_details, format_extracted_details_for_whatsapp
                    
                    with open(file_path, "rb") as f:
                        image_data = f.read()
                    
                    # Clean up the temporary file after reading it
                    try:
                        os.remove(file_path)
                        logging.info(f"Temporary file {file_path} removed")
                    except Exception as e:
                        logging.error(f"Error removing temporary file: {str(e)}")
                    
                    receipt_details, error = extract_receipt_details(image_data, "image")
                    
                    if error:
                        logging.error(f"Error extracting receipt details: {error}")
                        first_name = get_first_name(name)
                        data = get_text_message_input(sender_waid, f"I'm sorry {first_name}, I couldn't extract details from your receipt. Please try sending a clearer image or enter the details manually.")
                        send_message(data)
                        return
                    
                    # Log extracted details before modification
                    logging.info(f"Extracted receipt details: {receipt_details}")
                    
                    # Add the Google Drive link to the receipt details
                    if drive_link:
                        receipt_details["drive_link"] = drive_link
                        logging.info(f"Added Drive link to receipt details: {drive_link}")
                    
                    # Format the extracted details for WhatsApp
                    formatted_message = format_extracted_details_for_whatsapp(receipt_details)
                    
                    # Store the extracted receipt details for this user
                    store_extracted_receipt(sender_waid, receipt_details, name)
                    
                    # Send the formatted message with the receipt number
                    first_name = get_first_name(name)
                    confirmation_message = (
                        f"Hi {first_name}! I've extracted the following details from your receipt:\n\n"
                        f"{formatted_message}\n\n"
                        f"Receipt #{receipt_number} has been created.\n\n"
                        f"✏️ To add or correct information, reply with any of these fields:\n"
                        f"What:\n"
                        f"Amount:\n"
                        f"IVA:\n"
                        f"Store name:\n"
                        f"Payment method:\n"
                        f"Charge to:\n"
                        f"Comments:\n\n"
                        f"✅ To confirm without adding information, reply \"confirm\" or \"yes\".\n"
                        f"❌ To cancel this receipt, reply \"cancel\" or \"no\"."
                    )
                    data = get_text_message_input(sender_waid, confirmation_message)
                    send_message(data)
                    
                    # Update admins
                    admin_message = f"{name} sent a receipt image. Details extracted:\n\n{formatted_message}\n\nReceipt {receipt_number} created."
                    if drive_link:
                        admin_message += f"\nDrive link: {drive_link}"
                    update_admins(admin_message, sender_waid)
                    
                except Exception as e:
                    logging.error(f"Error in receipt extraction: {str(e)}")
                    data = get_text_message_input(sender_waid, "I encountered an error while processing your receipt. Please try again or enter the details manually.")
                    send_message(data)
            
        except Exception as e:
            logging.error(f"Error downloading image: {str(e)}")
            data = get_text_message_input(sender_waid, "I couldn't download your image. Please try again.")
            send_message(data)
            
    except Exception as e:
        logging.error(f"Error processing image message: {str(e)}")
        data = get_text_message_input(sender_waid, "I couldn't process your image. Please try again.")
        send_message(data)


def process_document_message(message, name, creds, sender_waid, folder_id):
    """
    Process a document message from WhatsApp.
    
    Args:
        message: The document message object
        name: The sender's name
        creds: Google API credentials
        sender_waid: The sender's WhatsApp ID
        folder_id: Google Drive folder ID for storing documents
    """
    try:
        # Get document information
        document_id = message["document"]["id"]
        caption = message["document"].get("caption", "").strip()
        filename = message["document"].get("filename", "document.pdf")
        mime_type = message["document"].get("mime_type", "application/pdf")
        
        logging.info(f"Processing document with ID: {document_id}, Caption: {caption}, Filename: {filename}, MIME type: {mime_type}")
        
        # Get the document URL from WhatsApp
        document_url = get_document_url_from_whatsapp(document_id)
        
        if not document_url:
            logging.error("Failed to get document URL from WhatsApp")
            data = get_text_message_input(sender_waid, "I couldn't download your document. Please try again.")
            send_message(data)
            return
        
        # Download the document with proper error handling
        try:
            logging.info(f"Downloading document from URL (first 50 chars): {document_url[:50]}...")
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                "Authorization": f"Bearer {os.getenv('ACCESS_TOKEN')}"
            }
            response = requests.get(document_url, headers=headers, timeout=30, stream=True)
            
            if response.status_code != 200:
                logging.error(f"Failed to download document: Status code {response.status_code}, Response: {response.text[:200]}")
                data = get_text_message_input(sender_waid, "I couldn't download your document. Please try again.")
                send_message(data)
                return
            
            # Check if we got actual document data
            content_type = response.headers.get('Content-Type', '')
            logging.info(f"Downloaded content type: {content_type}")
            
            if 'text/html' in content_type:
                logging.error(f"Received HTML instead of document data. Response: {response.text[:200]}")
                data = get_text_message_input(sender_waid, "I couldn't download your document. Please try again.")
                send_message(data)
                return
            
            # Save the document temporarily
            temp_dir = "data/temp_receipts"
            os.makedirs(temp_dir, exist_ok=True)
            
            # Process differently based on whether a caption was provided or not
            if caption:
                # Use the caption directly as part of the filename
                safe_caption = re.sub(r'[^\w\s-]', '', caption).replace(' ', '_')
                file_extension = os.path.splitext(filename)[1] or ".pdf"
                file_path = os.path.join(temp_dir, f"{safe_caption}{file_extension}")
                
                with open(file_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                logging.info(f"Document saved temporarily to {file_path}")
                
                # Upload to Google Drive
                file_name = f"{safe_caption}{file_extension}"
                drive_link = upload_document_to_drive(creds, folder_id, file_path, file_name)
                
                if drive_link:
                    # Send confirmation message
                    first_name = get_first_name(name)
                    confirmation_message = f"Thank you {first_name}! Your receipt document for #{safe_caption} has been saved to Google Drive."
                    data = get_text_message_input(sender_waid, confirmation_message)
                    send_message(data)
                    
                    # Update admins
                    admin_message = f"{name} sent a receipt document for #{safe_caption}.\nDrive link: {drive_link}"
                    update_admins(admin_message, sender_waid)
                else:
                    first_name = get_first_name(name)
                    data = get_text_message_input(sender_waid, f"I'm sorry {first_name}, I couldn't save your receipt document to Google Drive. Please try again.")
                    send_message(data)
                
                # Clean up the temporary file
                try:
                    os.remove(file_path)
                    logging.info(f"Temporary file {file_path} removed")
                except Exception as e:
                    logging.error(f"Error removing temporary file: {str(e)}")
            else:
                # No caption, process as a new receipt
                file_extension = os.path.splitext(filename)[1] or ".pdf"
                file_path = os.path.join(temp_dir, f"receipt_temp_{uuid.uuid4()}{file_extension}")
                
                with open(file_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                logging.info(f"Document saved temporarily to {file_path}")
                
                # Process the document for receipt extraction
                try:
                    # First, get a single receipt number to use for both the file and the receipt
                    receipt_number = get_receipt_number(creds, os.getenv("GOOGLE_SHEET_ID"))
                    drive_filename = f"{receipt_number}{file_extension}"
                    
                    # Upload to Google Drive
                    drive_link = upload_document_to_drive(creds, folder_id, file_path, drive_filename)
                    logging.info(f"Document uploaded to Google Drive: {drive_link}")
                    
                    # Extract receipt details using OCR/AI
                    from app.services.receipt_extraction_service import extract_receipt_details, format_extracted_details_for_whatsapp
                    
                    with open(file_path, "rb") as f:
                        document_data = f.read()
                    
                    # Clean up the temporary file
                    try:
                        os.remove(file_path)
                        logging.info(f"Temporary file {file_path} removed")
                    except Exception as e:
                        logging.error(f"Error removing temporary file: {str(e)}")
                    
                    receipt_details, error = extract_receipt_details(document_data, "pdf")
                    
                    if error:
                        logging.error(f"Error extracting receipt details: {error}")
                        first_name = get_first_name(name)
                        data = get_text_message_input(sender_waid, f"I'm sorry {first_name}, I couldn't extract details from your receipt. Please try sending a clearer document or enter the details manually.")
                        send_message(data)
                        return
                    
                    # Format the extracted details for WhatsApp
                    formatted_message = format_extracted_details_for_whatsapp(receipt_details)
                    
                    # Store the extracted receipt details for this user and add the drive link
                    if drive_link:
                        receipt_details["drive_link"] = drive_link
                    store_extracted_receipt(sender_waid, receipt_details, name)
                    
                    # Send the formatted message with the receipt number
                    first_name = get_first_name(name)
                    confirmation_message = (
                        f"Hi {first_name}! I've extracted the following details from your receipt:\n\n"
                        f"{formatted_message}\n\n"
                        f"Receipt #{receipt_number} has been created.\n\n"
                        f"✏️ To add or correct information, reply with any of these fields:\n"
                        f"What:\n"
                        f"Amount:\n"
                        f"IVA:\n"
                        f"Store name:\n"
                        f"Payment method:\n"
                        f"Charge to:\n"
                        f"Comments:\n\n"
                        f"✅ To confirm without adding information, reply \"confirm\" or \"yes\".\n"
                        f"❌ To cancel this receipt, reply \"cancel\" or \"no\"."
                    )
                    data = get_text_message_input(sender_waid, confirmation_message)
                    send_message(data)
                    
                    # Update admins
                    admin_message = f"{name} sent a receipt document. Details extracted:\n\n{formatted_message}\n\nReceipt {receipt_number} created."
                    if drive_link:
                        admin_message += f"\nDrive link: {drive_link}"
                    update_admins(admin_message, sender_waid)
                    
                except Exception as e:
                    logging.error(f"Error in receipt extraction: {str(e)}")
                    data = get_text_message_input(sender_waid, "I encountered an error while processing your receipt. Please try again or enter the details manually.")
                    send_message(data)
                    
                    # Make sure to clean up the temporary file if it still exists
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            logging.info(f"Temporary file {file_path} removed after error")
                    except Exception as ex:
                        logging.error(f"Error removing temporary file after extraction error: {str(ex)}")
            
        except Exception as e:
            logging.error(f"Error downloading document: {str(e)}")
            data = get_text_message_input(sender_waid, "I couldn't download your document. Please try again.")
            send_message(data)
    
    except Exception as e:
        logging.error(f"Error processing document message: {str(e)}")
        data = get_text_message_input(sender_waid, "I couldn't process your document. Please try again.")
        send_message(data)


def handle_receipt_confirmation(sender_waid, text, creds, name):
    """Handle receipt confirmation from user"""
    stored_receipt = get_stored_receipt(sender_waid)
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    
    # Check if we have stored receipt data for this user
    if not stored_receipt:
        first_name = get_first_name(name)
        data = get_text_message_input(sender_waid, f"I'm sorry {first_name}, I don't have any pending receipt details to confirm. You can send a new receipt image or enter details manually.")
        send_message(data)
        return True
    
    # User is confirming extracted receipt details
    logging.info(f"User confirming receipt details: {stored_receipt}")
    
    # Use prepare_for_google_sheets to get the values in the correct order
    update_data = prepare_for_google_sheets(stored_receipt)
    logging.info(f"Prepared data for Google Sheets: {update_data}")
    
    # Remove the stored receipt
    delete_stored_receipt(sender_waid)
    
    # Write to Google Sheets
    receipt_num = append_to_sheet(creds, sheet_id, update_data)
    
    # Send confirmation
    first_name = get_first_name(name)
    confirm_message = f"Thank you {first_name}! I've saved your receipt details. Your receipt number is {receipt_num}."
    data = get_text_message_input(sender_waid, confirm_message)
    send_message(data)
    
    # Update admins
    admin_message = f"{name} confirmed receipt details. Receipt {receipt_num} added to spreadsheet."
    if "drive_link" in stored_receipt:
        admin_message += f"\nDrive link: {stored_receipt['drive_link']}"
    update_admins(admin_message, sender_waid)
    
    return True


def delete_file_from_drive(credentials, file_id):
    """
    Delete a file from Google Drive.
    
    Args:
        credentials: Google API credentials
        file_id: ID of the file to delete
        
    Returns:
        Boolean indicating success
    """
    if credentials is None:
        logging.error("Cannot delete file from Google Drive: credentials are not available")
        return False
        
    try:
        service = build('drive', 'v3', credentials=credentials)
        service.files().delete(fileId=file_id).execute()
        logging.info(f"Deleted file {file_id} from Google Drive")
        return True
    except Exception as e:
        logging.error(f"Error deleting file from Google Drive: {str(e)}")
        return False


def get_first_name(full_name):
    """
    Extract the first name from a full name.
    
    Args:
        full_name: The full name of the user
        
    Returns:
        str: The first name
    """
    if not full_name:
        return ""
    
    # Split the name and return the first part
    return full_name.split()[0]
