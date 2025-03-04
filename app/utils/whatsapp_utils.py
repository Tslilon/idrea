from datetime import datetime
import logging
import os
import json
import requests
import re

from flask import current_app, jsonify
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

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
    service = build('drive', 'v3', credentials=credentials)
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    media = MediaFileUpload(file_path, mimetype='image/jpeg')  # Adjust mimetype if necessary
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    print("File ID: %s" % file.get('id'))

    return file.get('id')


def process_whatsapp_message(body):
    name = body["entry"][0]["changes"][0]["value"]["contacts"][0]["profile"]["name"]
    sender_waid = body["entry"][0]["changes"][0]["value"]["contacts"][0]["wa_id"]
    sender_waid = f"+{sender_waid}"

    # OpenAI Integration
    # wa_id = body["entry"][0]["changes"][0]["value"]["contacts"][0]["wa_id"]
    # response = generate_response(message_body, wa_id, name)
    # response = process_text_for_whatsapp(response)

    creds = load_credentials()
    folder_id = os.getenv("GOOGLE_FOLDER_ID")

    entry = body["entry"][0]
    changes = entry["changes"][0]
    message_data = changes["value"]
    message_type = message_data["messages"][0].get("type")

    if message_type == "document":
        document_info = message_data["messages"][0]["document"]
        # print(document_info)
        document_caption = document_info.get("caption")
        filename = document_info.get("filename")
        document_id = document_info.get("id")

        if document_caption:
            file_name = document_caption
        else:
            file_name = filename

        # Update the admins:
        update_admins(f"{name} sent a document ({file_name})", sender_waid)

        document_url = get_document_url_from_whatsapp(document_id)  # Implement this function

        document_response = download_document(document_url)

        if document_response.status_code == 200:
            temp_document_path = os.path.join('data/temp_receipts/', file_name)

            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(temp_document_path), exist_ok=True)

            with open(temp_document_path, 'wb') as file:
                file.write(document_response.content)

            upload_document_to_drive(creds, folder_id, temp_document_path, file_name)

            os.remove(temp_document_path)
            # Send success message
            text = f'Saved file! (#{file_name})'
            data = get_text_message_input(sender_waid, text)
            send_message(data)
            # Update the admins:
            update_admins(text, sender_waid)

        else:
            print('error downloading document')  # Handle failure to download document
            # Send an error message to the user or log the error
            data = get_text_message_input(sender_waid, f'Error saving file')
            send_message(data)

    elif message_type == "image":

        # Handle image message
        image_info = message_data["messages"][0]["image"]
        image_id = image_info.get("id")
        image_caption = image_info.get("caption")

        if image_caption:
            # Process the caption as a text message
            file_name = image_caption
        else:
            file_name = image_id

        # Update the admins:
        update_admins(f"{name} sent an image ({file_name})", sender_waid)

        image_url = get_image_url_from_whatsapp(image_id)  # Implement this function

        def download_image(image_url):
            headers = {
                "Authorization": f"Bearer {os.getenv('ACCESS_TOKEN')}",
            }

            response = requests.get(image_url, headers=headers)
            return response

        # Download the image
        image_response = download_image(image_url)

        if image_response.status_code == 200:

            # Save the image to a temporary file
            temp_image_path = os.path.join('data/temp_receipts/', file_name)
            with open(temp_image_path, 'wb') as file:
                file.write(image_response.content)

            # Upload the image to Google Drive
            upload_image_to_drive(creds, folder_id, temp_image_path, file_name)

            # Optionally, delete the temporary image file after upload
            os.remove(temp_image_path)
            text = f'Receipt added to our folder! (#{file_name})'
            data = get_text_message_input(sender_waid, text)
            send_message(data)

            update_admins(text, sender_waid)

        else:
            # Send an error message to the user or log the error
            print(f"Failed to download image. Status Code: {image_response.status_code}")
            print(f"Response Content: {image_response.content}")
    else:
        message = body["entry"][0]["changes"][0]["value"]["messages"][0]

        try:
            text = message["text"]["body"]
        except KeyError:
            text = 'EMPTY MSG'
            print('empty message sent (message["text"]["body"]) has no text')

        # Update the admins:
        update_admins(f"{name} sent:\n\n{text}", sender_waid)

        process_text_message(text, name, creds, sender_waid)


def get_document_url_from_whatsapp(document_id):
    """
    Fetches the URL of a document from WhatsApp using the document ID.

    Parameters:
    document_id (str): The ID of the document.

    Returns:
    str: The URL of the document, or None if the request fails.
    """
    url = f"https://graph.facebook.com/v18.0/{document_id}"  # Update API version as needed
    headers = {
        "Authorization": f"Bearer {os.getenv('ACCESS_TOKEN')}",
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        document_data = response.json()
        return document_data.get("url")  # Or the appropriate key based on the response
    else:
        logging.error(f"Error fetching document URL: {response.status_code}")
        return None


def upload_document_to_drive(credentials, folder_id, file_path, file_name):
    # Similar to upload_image_to_drive but adjust mimetype for PDFs
    mimetype = 'application/pdf'  # For PDF files

    service = build('drive', 'v3', credentials=credentials)
    file_metadata = {'name': file_name, 'parents': [folder_id]}
    media = MediaFileUpload(file_path, mimetype=mimetype)
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    print("File ID: %s" % file.get('id'))
    return file.get('id')


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
    }

    try:
        response = requests.get(document_url, headers=headers)
        response.raise_for_status()  # Raises an HTTPError for bad requests
    except requests.RequestException as e:
        logging.error(f"Request failed: {e}")
        return None

    return response


def process_text_message(text, name, creds, sender_waid):
    sheet_id = os.getenv("GOOGLE_SHEET_ID")

    # Check format and generate response
    response = generate_response(text)

    if response == "Processing your update...":
        # Parse the message
        parts = text.split('\n')
        update_data = [name]

        for part in parts:
            key, _, value = part.partition(':')
            key = key.strip()
            # print(key)
            value = value.strip()

            if (key == "Amount") | (key == "IVA"):
                # Replace comma with period for decimal
                value = value.replace(',', '.')
                # Remove the last character if it is a period
                if value.endswith('.'):
                    value = value[:-1]
                # If there are two periods, remove the first one
                if value.count('.') == 2:
                    first_period_index = value.find('.')
                    value = value[:first_period_index] + value[first_period_index + 1:]

                # Extract only digits and decimal points
                value = re.sub(r'[^\d.]+', '', value)
                try:
                    # Convert to float
                    value = float(value)
                except ValueError:
                    # Handle cases where conversion to float fails
                    value = value  # or any other default value or action

            update_data.append(value)

        # Write to Google Sheets
        receipt_num = append_to_sheet(creds, sheet_id, update_data)

        text = f'Update added to our list! (#{receipt_num})'
        data = get_text_message_input(sender_waid, text)
        send_message(data)

        # Update the admins:
        update_admins(text, sender_waid)

    else:

        data = ("*What*: \n"
                "*Amount* (euros): \n"
                "IVA (euros): \n"
                "Receipt: yes \n"
                "Store name: \n"
                "Payment method: \n"
                "Charge to: \n"
                "Comments: \n\n"
                "Knock-Knock! _Who's there?_ The IT guy! 👋")
        data = get_text_message_input(sender_waid, data)
        send_message(data)


def is_valid_whatsapp_message(body):
    """
    Check if the incoming webhook event has a valid WhatsApp message structure.
    """
    return (
            body.get("object")
            and body.get("entry")
            and body["entry"][0].get("changes")
            and body["entry"][0]["changes"][0].get("value")
            and body["entry"][0]["changes"][0]["value"].get("messages")
            and body["entry"][0]["changes"][0]["value"]["messages"][0]
    )


SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
google_creds_json = 'data/credentials.json'


def get_client_info():
    with open(google_creds_json) as f:
        data = json.load(f)
    client_id = data['installed']['client_id']
    client_secret = data['installed']['client_secret']
    return client_id, client_secret


CLIENT_ID, CLIENT_SECRET = get_client_info()


def refresh_access_token(refresh_token):
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

    SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE')
    # Define the scopes required by your application
    SCOPES = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']

    # Authenticate using the service account
    creds = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)

    return creds


def get_receipt_number(credentials, sheet_id):
    service = build('sheets', 'v4', credentials=credentials)

    # Specify the sheet and range to read.
    range_to_read = 'iDrea!A2:A'  # Assuming 'A2:A' contains receipt numbers, adjust as needed

    # Call the Sheets API to read data
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=range_to_read).execute()

    values = result.get('values', [])

    # Extract receipt numbers and find the max
    receipt_numbers = [int(row[0]) for row in values if row and row[0].isdigit()]
    max_receipt_number = max(receipt_numbers, default=0)  # Default to 0 if list is empty

    return max_receipt_number + 1


def append_to_sheet(credentials, sheet_id, values_list):
    service = build('sheets', 'v4', credentials=credentials)

    # Specify the sheet and the range where data will be appended.
    # For example, 'Sheet1' is the sheet name, and 'A:A' specifies the first column.
    range = 'iDrea!A:K'  # Update this with your actual sheet name and range

    # Convert timestamp to readable format (if necessary)
    time = datetime.now().strftime('%Y-%m-%d %H:%M')

    # Get the next receipt number
    next_receipt_number = get_receipt_number(credentials, sheet_id)

    # Prepare the data to append.
    values = [next_receipt_number, time] + values_list
    body = {'values': [values]}

    # Call the Sheets API
    result = service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=range,
        valueInputOption='USER_ENTERED',
        body=body).execute()

    print(f"{result.get('updates').get('updatedCells')} cells appended.")
    return next_receipt_number


def get_image_url_from_whatsapp(image_id):
    """
    Fetches the URL of an image from WhatsApp using the image ID.

    Parameters:
    image_id (str): The ID of the image.
    access_token (str): Access token for the WhatsApp Business API.

    Returns:
    str: The URL of the image.
    """
    url = f"https://graph.facebook.com/v18.0/{image_id}"  # Update API version as needed
    # print(url)
    headers = {
        "Authorization": f"Bearer {os.getenv('ACCESS_TOKEN')}",
    }

    response = requests.get(url, headers=headers)
    # print('response: ')
    # print(response)

    if response.status_code == 200:
        image_data = response.json()
        # print('image_data: ')
        # print(image_data['id'])

        # The exact key for the image URL depends on the API's response structure
        return image_data.get("url")  # Or the appropriate key based on the response
    else:
        # Log error or handle it as per your requirement
        print(f"Error fetching image URL: {response.status_code}")
        return None
