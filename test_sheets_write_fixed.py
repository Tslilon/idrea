import os
import logging
from googleapiclient.discovery import build
from app.utils.whatsapp_utils import load_credentials, get_receipt_number

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def append_to_sheet_with_fixed_columns(credentials, sheet_id, receipt_data):
    """Append to sheet with explicit column mapping."""
    if credentials is None:
        logging.error("Cannot append to Google Sheet: credentials are not available")
        return None
    
    try:
        service = build('sheets', 'v4', credentials=credentials)

        # Specify the sheet
        sheet_name = 'iDrea'  # Update this with your actual sheet name
        
        # Get the next receipt number
        next_receipt_number = get_receipt_number(credentials, sheet_id)
        if next_receipt_number is None:
            logging.error("Failed to get next receipt number")
            return None

        # Create values with explicit column assignments
        # This ensures each value goes to the right column regardless of the order
        receipt_date = receipt_data.get("receipt_date", "")  # Should be in YYYY-MM-DD HH:MM format
        
        # Create an array with all the values
        values = [
            next_receipt_number,           # A: Receipt number
            receipt_date,                  # B: When
            receipt_data.get("who", ""),   # C: Who
            receipt_data.get("what", ""),  # D: What
            receipt_data.get("amount", ""), # E: Amount
            receipt_data.get("iva", ""),   # F: IVA
            receipt_data.get("receipt", "yes"), # G: Receipt
            receipt_data.get("store", ""), # H: Store name
            receipt_data.get("payment", ""), # I: Payment method
            receipt_data.get("charge", ""), # J: Charge to
            receipt_data.get("comments", ""), # K: Comments
            receipt_data.get("company", ""), # L: Company
            receipt_data.get("invoice_number", ""), # M: Invoice number
            receipt_data.get("supplier_id", "") # N: Supplier ID
        ]
        
        logging.info(f"Final values being appended to Google Sheet: {values}")
        
        # Format the data for the API
        body = {'values': [values]}

        # Call the Sheets API
        result = service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=f'{sheet_name}!A:K',
            valueInputOption='USER_ENTERED',
            body=body).execute()

        logging.info(f"{result.get('updates').get('updatedCells')} cells appended.")
        
        return next_receipt_number
    except Exception as e:
        logging.error(f"Error appending to Google Sheet: {str(e)}")
        return None

def test_fixed_column_write():
    """Test appending to Google Sheets with fixed column positions."""
    print("===== Testing Google Sheets Write with Fixed Columns =====\n")
    
    # Get sheet ID
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        print("Error: GOOGLE_SHEET_ID environment variable not set.")
        return False
    
    # Load credentials
    creds = load_credentials()
    if creds is None:
        print("Error: Could not load Google API credentials.")
        return False
    
    print(f"Successfully loaded credentials.")
    
    # Create a test receipt with explicit column values
    test_receipt = {
        "receipt_date": "2024-04-20 12:00",  # The date in YYYY-MM-DD HH:MM format
        "who": "FIXED TEST",  # Sender name
        "what": "column test fixed",  # Description
        "amount": "789",  # Amount
        "iva": "10",  # IVA
        "receipt": "no",  # Receipt status
        "store": "Test Store Fixed",  # Store name
        "payment": "cash",  # Payment method
        "charge": "test dept",  # Charge to
        "comments": "fixed columns test"  # Comments
    }
    
    print("\nTest receipt data:")
    for key, value in test_receipt.items():
        print(f"  {key}: {value}")
    
    # Append to Google Sheets with fixed columns
    receipt_num = append_to_sheet_with_fixed_columns(creds, sheet_id, test_receipt)
    
    if receipt_num:
        print(f"\n✅ Successfully wrote to Google Sheets with receipt #{receipt_num}!")
        print("\nPlease check your Google Sheet to verify the column order is correct.")
        print("The data should have been written with FIXED column positions to avoid any issues.")
        return True
    else:
        print("\n❌ Failed to write to Google Sheets!")
        return False

if __name__ == "__main__":
    success = test_fixed_column_write()
    if success:
        print("\nTest completed successfully!")
    else:
        print("\nTest failed.") 