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
            
            # Make sure sender_name is included
            if "sender_name" not in stored_receipt:
                stored_receipt["sender_name"] = name
                
            # Use prepare_for_google_sheets to get the values in the correct order
            update_data = prepare_for_google_sheets(stored_receipt)
            
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
            update_admins(f"Receipt #{receipt_num} confirmed by {name}", sender_waid)
            
            return
        else:
            # No stored receipt to confirm
            response = "I don't have any pending receipt details to confirm. Please provide receipt details first."
            data = get_text_message_input(sender_waid, response)
            send_message(data)
            return
    
    # Handle cancellation keywords
    if text_lower in ["cancel", "no", "n"]:
        if stored_receipt:
            # User is cancelling the receipt
            logging.info(f"User cancelling receipt: {stored_receipt}")
            
            # Check if there's a Drive link in the stored receipt and delete the file
            if "drive_link" in stored_receipt and stored_receipt["drive_link"]:
                drive_link = stored_receipt["drive_link"]
                # Extract file ID from the Drive link
                file_id_match = re.search(r'/d/([^/]+)', drive_link)
                if file_id_match:
                    file_id = file_id_match.group(1)
                    logging.info(f"Attempting to delete file with ID {file_id} from Google Drive")
                    delete_success = delete_file_from_drive(creds, file_id)
                    if delete_success:
                        logging.info(f"Successfully deleted file {file_id} from Google Drive")
                    else:
                        logging.error(f"Failed to delete file {file_id} from Google Drive")
            
            # Remove the stored receipt
            delete_stored_receipt(sender_waid)
            
            # Send cancellation confirmation
            first_name = get_first_name(name)
            cancel_message = f"I've cancelled the receipt creation process, {first_name}. No data has been saved."
            data = get_text_message_input(sender_waid, cancel_message)
            send_message(data)
            
            # Update admins
            update_admins(f"{name} cancelled a receipt", sender_waid)
            
            return
        else:
            # No stored receipt to cancel
            response = "I don't have any pending receipt details to cancel."
            data = get_text_message_input(sender_waid, response)
            send_message(data)
            return
    
    # Handling receipt image caption requests
    if text.isdigit():
        response = f"Looking for receipt #{text}..."
        data = get_text_message_input(sender_waid, response)
        send_message(data)
        # Further handling would be done elsewhere
        return
    
    # Check if this is an edit request for an existing stored receipt
    if stored_receipt and not ":" in text:
        # Simple text without field markers - might be an update attempt
        response = "If you want to update a specific field, please use the format 'Field: New Value', for example 'Amount: 42.50'"
        data = get_text_message_input(sender_waid, response)
        send_message(data)
        return
        
    # If we have stored data and this looks like a field update
    if stored_receipt and ":" in text:
        # This might be an update to a specific field
        text_parts = text.split("\n")
        updates = {}
        
        for line in text_parts:
            if ":" in line:
                # Split at the first colon
                colon_index = line.find(":")
                field_name = line[:colon_index].strip().lower()
                field_value = line[colon_index+1:].strip()
                
                # Use our field normalization rules to get consistent field names
                normalized_field = None
                if "amount" in field_name:
                    normalized_field = "total_amount"
                elif "iva" in field_name:
                    normalized_field = "iva"
                elif "receipt" in field_name:
                    normalized_field = "has_receipt"
                elif "store" in field_name:
                    normalized_field = "store_name"
                elif "payment" in field_name:
                    normalized_field = "payment_method"
                elif "charge" in field_name:
                    normalized_field = "charge_to"
                elif "comments" in field_name or "notes" in field_name:
                    normalized_field = "comments"
                elif "what" in field_name or "description" in field_name:
                    normalized_field = "what"
                elif "when" in field_name or "date" in field_name:
                    normalized_field = "when"
                
                if normalized_field:
                    # Process special fields
                    # Process amount and IVA
                    if normalized_field in ["total_amount", "iva"]:
                        if field_value:
                            try:
                                # Try to clean up the value to be a valid number
                                # Remove any currency symbols
                                field_value = re.sub(r'[^\d.,\-]', '', field_value)
                                
                                # If value starts with a comma or period, add a 0 before it
                                if field_value.startswith('.') or field_value.startswith(','):
                                    field_value = '0' + field_value
                                    
                                # If value ends with a comma or period, remove it
                                if field_value.endswith('.') or field_value.endswith(','):
                                    field_value = field_value[:-1]
                                    
                                # Don't convert format here, just clean up
                                # The actual conversion to European format happens in append_to_sheet
                            except:
                                # If not a valid number, keep as is but log
                                logging.warning(f"Invalid number format for {field_name}: {field_value}")
                    
                    # Process date formats for "when"/"date" field
                    elif field_name in ["when", "date"]:
                        # If the value is the instruction text or empty, skip it
                        if not field_value or field_value.startswith("(can be empty"):
                            logging.info(f"Empty or instruction text detected in date field: '{field_value}'. Using current date.")
                            field_value = ""  # Will default to current date
                        else:
                            try:
                                # Try to parse the date in various formats
                                from datetime import datetime
                                date_formats = [
                                    "%d/%m/%Y",  # 31/12/2023
                                    "%d-%m-%Y",  # 31-12-2023
                                    "%d.%m.%Y",  # 31.12.2023
                                    "%d/%m/%y",  # 31/12/23
                                    "%d-%m-%y",  # 31-12-23
                                    "%d.%m.%y",  # 31.12.23
                                    "%Y-%m-%d",  # 2023-12-31 (ISO format)
                                    "%Y/%m/%d",  # 2023/12/31
                                    "%m/%d/%Y",  # 12/31/2023 (US format)
                                    "%b %d, %Y", # Dec 31, 2023
                                    "%d %b %Y"   # 31 Dec 2023
                                ]
                                
                                parsed_date = None
                                for fmt in date_formats:
                                    try:
                                        parsed_date = datetime.strptime(field_value, fmt)
                                        # Verify the parsed date is valid (catches things like 31/04/2024)
                                        # by checking if reformatting keeps the same day
                                        original_day = field_value.split('/')[0] if '/' in field_value else None
                                        if original_day and original_day.isdigit():
                                            if int(original_day) == parsed_date.day:
                                                break
                                            else:
                                                logging.warning(f"Invalid date detected: {field_value} - day doesn't match after parsing")
                                                parsed_date = None
                                                continue
                                        else:
                                            break
                                    except ValueError:
                                        continue
                                
                                if parsed_date:
                                    # Standardize to DD/MM/YYYY format
                                    field_value = parsed_date.strftime("%d/%m/%Y")
                                    logging.info(f"Parsed date '{field_value}' to standard format: {field_value}")
                                else:
                                    # If today or yesterday is specified
                                    if field_value.lower() == "today":
                                        field_value = datetime.now().strftime("%d/%m/%Y")
                                    elif field_value.lower() == "yesterday":
                                        from datetime import timedelta
                                        field_value = (datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y")
                                    else:
                                        # If we couldn't parse the date, log it but keep the value empty
                                        # so that the current date will be used
                                        logging.warning(f"Could not parse date format: {field_value}. Will use current date.")
                                        field_value = ""  # This will make the system use the current date
                            except Exception as e:
                                logging.warning(f"Error parsing date: {str(e)}. Using current date.")
                                field_value = ""  # This will make the system use the current date
                    
                    # Only add non-empty values to updates
                    if field_value:
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
                f"When: [today/yesterday/DD/MM/YYYY]\n"
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
        "when": "When",
        "date": "When",
        "comments": "Comments",
        "company": "Company"
    }
    
    # Check if this looks like a receipt form submission - use case-insensitive matching
    form_fields = ["what", "amount", "store name"]
    form_detected = sum(1 for field in form_fields if field in text_lower) >= 2
    
    logging.info(f"Form detected: {form_detected}")
    
    if form_detected:
        # This looks like a form submission, parse it and use our standard prepare_for_google_sheets
        # to ensure consistent field order
        parsed_data = parse_manual_receipt_entry(text)
        
        # Add the sender name
        parsed_data["sender_name"] = name
        
        # Use the standard field formatter to get consistent order
        formatted_values = prepare_for_google_sheets(parsed_data)
        
        # Write to Google Sheets using the standard field order
        receipt_num = append_to_sheet(creds, sheet_id, formatted_values)
        
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
                "When:\n"
                "_(leave empty for today's date, or use 'yesterday', or DD/MM/YYYY)_\n"
                "Receipt: yes\n"
                "Store name: \n"
                "Company: \n"
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
        "Amount (euros)": "total_amount",  # Handle "(euros)" version
        "IVA": "iva",
        "IVA (euros)": "iva",  # Handle "(euros)" version
        "Receipt": "has_receipt",
        "Payment method": "payment_method",
        "Charge to": "charge_to",
        "Comments": "comments",
        "Date": "date",
        "When": "when",
        "What": "what",  # Fixed: Previously was "description"
        "Company": "company"
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
        
        # Check for amount pattern in key (smarter detection)
        key_lower = key.lower()
        if "amount" in key_lower:
            internal_key = "total_amount"
        elif "iva" in key_lower:
            internal_key = "iva"
        else:
            # Map the field name if possible using existing logic
            internal_key = field_mappings.get(key)
            if not internal_key:
                # Try case-insensitive match
                for k, v in field_mappings.items():
                    if k.lower() == key_lower:
                        internal_key = v
                        break
                        
            if not internal_key:
                # Still not found, just use the key directly
                internal_key = key.lower().replace(' ', '_')
        
        # Log the field mapping for debugging
        logging.info(f"Field mapping: '{key}' -> '{internal_key}' with value '{value}'")
            
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
            # Add logging for debugging
            logging.info(f"Processed amount field '{internal_key}': '{value}'")
                
        elif internal_key == "has_receipt":
            # Keep as string value to match what the spreadsheet expects
            # Convert variants of "yes"/"no" to consistent format
            if value.lower() in ["yes", "true", "1", "y"]:
                value = "yes"
            elif value.lower() in ["no", "false", "0", "n"]:
                value = "no"
            # Otherwise keep the original value
        
        # Store the value
        result[internal_key] = value
        
    return result


def is_valid_whatsapp_message(message):
    """
    Check if the received message is a valid WhatsApp message.
    
    Args:
        message: The message object
        
    Returns:
        Boolean indicating if the message is valid
    """
    if not message or not isinstance(message, dict):
        return False
    if "type" not in message:
        return False
    
    msg_type = message.get("type")
    if msg_type == "text" and message.get("text"):
        return True
    elif msg_type == "image" and message.get("image"):
        return True
    elif msg_type == "document" and message.get("document"):
        return True
    
    return False


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
            
            # Use a persistent file to track the latest assigned receipt number
            # This ensures numbers aren't reused even if receipts are cancelled
            tracking_file = "latest_receipt_number.txt"
            latest_tracked_number = 0
            
            # Read the latest tracked number from file
            try:
                if os.path.exists(tracking_file):
                    with open(tracking_file, "r") as f:
                        latest_tracked_number = int(f.read().strip())
                        logging.info(f"Read latest tracked receipt number: {latest_tracked_number}")
            except Exception as e:
                logging.error(f"Error reading tracked receipt number: {str(e)}")
            
            # CHANGED: Always prioritize the Google Sheet's max number over the tracking file
            # If there are entries in the sheet, use sheet max + 1, otherwise use tracking file + 1
            if receipt_numbers:  # If we have entries in the sheet
                next_receipt_number = max_receipt_number + 1
                # Also update the tracking file if it's behind
                if next_receipt_number > latest_tracked_number:
                    latest_tracked_number = next_receipt_number
            else:
                # No entries in the sheet, use tracking file + 1
                next_receipt_number = latest_tracked_number + 1
            
            # Save the new number to the tracking file
            try:
                with open(tracking_file, "w") as f:
                    f.write(str(next_receipt_number))
                logging.info(f"Saved new receipt number {next_receipt_number} to tracking file")
            except Exception as e:
                logging.error(f"Error saving tracked receipt number: {str(e)}")

            return next_receipt_number
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

        # Log the received values list for debugging
        logging.info(f"Values to append to sheet: {values_list}")
        
        # The order from prepare_for_google_sheets is:
        # [when, who, what, amount, IVA, receipt, store_name, payment_method, charge_to, comments, company]
        
        # Ensure we have at least some values
        if not values_list:
            logging.error("Empty values list provided to append_to_sheet")
            return None
            
        # Extract key values CORRECTLY according to the prepare_for_google_sheets order
        when_date = values_list[0] if len(values_list) > 0 else ""
        who = values_list[1] if len(values_list) > 1 else ""
        what = values_list[2] if len(values_list) > 2 else ""
        amount = values_list[3] if len(values_list) > 3 else ""
        iva = values_list[4] if len(values_list) > 4 else ""
        receipt_value = values_list[5] if len(values_list) > 5 else "yes"
        store_name = values_list[6] if len(values_list) > 6 else ""
        payment_method = values_list[7] if len(values_list) > 7 else ""
        charge_to = values_list[8] if len(values_list) > 8 else ""
        comments = values_list[9] if len(values_list) > 9 else ""
        company = values_list[10] if len(values_list) > 10 else ""
        
        # Log extracted key values for debugging
        logging.info(f"Extracted key values from values_list:")
        logging.info(f"  When: {when_date}")
        logging.info(f"  Who: {who}")
        logging.info(f"  What: {what}")
        logging.info(f"  Amount: {amount}")
        logging.info(f"  IVA: {iva}")
        
        # Check if receipt_number is provided in the values list (last element if available)
        stored_receipt_number = values_list[11] if len(values_list) > 11 else None
        
        # Get the next receipt number or use the stored one if available
        if stored_receipt_number:
            next_receipt_number = int(stored_receipt_number)
            logging.info(f"Using stored receipt number: {next_receipt_number}")
        else:
            next_receipt_number = get_receipt_number(credentials, sheet_id)
            logging.info(f"Generated new receipt number: {next_receipt_number}")
            
        if next_receipt_number is None:
            logging.error("Failed to get next receipt number")
            return None
        
        # Process values with format conversion
        processed_values = []
        
        # Process amount, keeping European formatting
        if amount and isinstance(amount, str):
            cleaned_amount = amount.strip().replace('€', '')
            if ',' in cleaned_amount:
                processed_amount = cleaned_amount  # Already has European formatting
            else:
                try:
                    # Convert to float and then to European format
                    num_value = float(cleaned_amount.replace(',', '.'))
                    processed_amount = str(num_value).replace('.', ',')
                except ValueError:
                    processed_amount = cleaned_amount
            logging.info(f"Processed amount: {amount} -> {processed_amount}")
        else:
            processed_amount = amount
        
        # Process IVA, keeping European formatting
        if iva and isinstance(iva, str):
            cleaned_iva = iva.strip().replace('€', '')
            if ',' in cleaned_iva:
                processed_iva = cleaned_iva  # Already has European formatting
            else:
                try:
                    # Convert to float and then to European format
                    num_value = float(cleaned_iva.replace(',', '.'))
                    processed_iva = str(num_value).replace('.', ',')
                except ValueError:
                    processed_iva = cleaned_iva
            logging.info(f"Processed IVA: {iva} -> {processed_iva}")
        else:
            processed_iva = iva
        
        # Create final values array with FIXED column positions
        # Each value goes to the right column with actual field names
        final_values = [
            next_receipt_number,  # A: Receipt number
            when_date,            # B: When (date)
            who,                  # C: Who (sender name)
            what,                 # D: What (description)
            processed_amount,     # E: Amount
            processed_iva,        # F: IVA
            receipt_value,        # G: Receipt
            store_name,           # H: Store name
            payment_method,       # I: Payment method
            charge_to,            # J: Charge to
            comments,             # K: Comments
            company               # L: Company
        ]
        
        # Log full details of the final values for debugging
        logging.info(f"Final values being appended to Google Sheet: {final_values}")
        
        body = {'values': [final_values]}

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
        
        # For images, we need to check differently since filename isn't directly available
        # If caption looks like a filename with common image extensions, treat as no caption
        if caption and (caption.lower().endswith('.jpg') or caption.lower().endswith('.jpeg') 
                      or caption.lower().endswith('.png') or caption.lower().endswith('.gif') 
                      or caption.lower().endswith('.webp')):
            logging.info(f"Caption appears to be a filename ({caption}). Treating as no caption.")
            caption = ""
        
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
                # Generate a unique filename for temporary storage
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
                    drive_filename = f"{receipt_number}{extension}"
                    
                    # Upload to Google Drive
                    drive_link = upload_image_to_drive(creds, folder_id, file_path, drive_filename)
                    logging.info(f"Image uploaded to Google Drive: {drive_link}")
                    
                    # Extract receipt details using OCR/AI
                    from app.services.receipt_extraction_service import extract_receipt_details, format_extracted_details_for_whatsapp
                    
                    with open(file_path, "rb") as f:
                        image_data = f.read()
                    
                    # Clean up the temporary file
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
                    
                    # Format the extracted details for WhatsApp
                    formatted_message = format_extracted_details_for_whatsapp(receipt_details)
                    
                    # Store the extracted receipt details for this user and add the drive link
                    if drive_link:
                        receipt_details["drive_link"] = drive_link
                    
                    # Add the receipt number to the receipt details
                    receipt_details["receipt_number"] = receipt_number
                    logging.info(f"Added receipt number {receipt_number} to receipt details")
                    
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
                        f"When:\n"
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
                    
                    # Make sure to clean up the temporary file if it still exists
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            logging.info(f"Temporary file {file_path} removed after extraction error")
                    except Exception as ex:
                        logging.error(f"Error removing temporary file after extraction error: {str(ex)}")
            
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
        
        # Check if caption equals filename - treat as no caption if they match
        if caption == filename:
            logging.info(f"Caption matches filename exactly ({caption}). Treating as no caption.")
            caption = ""
        
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
                    
                    # Add the receipt number to the receipt details
                    receipt_details["receipt_number"] = receipt_number
                    logging.info(f"Added receipt number {receipt_number} to receipt details")
                    
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
                        f"When:\n"
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
                            logging.info(f"Temporary file {file_path} removed after extraction error")
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
