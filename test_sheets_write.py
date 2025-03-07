import os
import logging
import json
from datetime import datetime
from app.services.receipt_extraction_service import prepare_for_google_sheets
from app.utils.whatsapp_utils import append_to_sheet, load_credentials
from google.oauth2.service_account import Credentials

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_sheet_write():
    """Test the complete process of formatting and writing to Google Sheets."""
    print("===== Testing Google Sheets Write =====\n")
    
    # Get environment variables
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
    
    # Create a mock receipt entry that simulates a manual form input
    mock_receipt = {
        "sender_name": "Debug Test",
        "what": "column test",
        "total_amount": "456",
        "iva": "21",
        "has_receipt": "no",  # Testing "no" value
        "store_name": "Test Company",
        "payment_method": "card",
        "charge_to": "test",
        "comments": "debug run",
        "when": "20/04/2024"  # Testing date field
    }
    
    print("\nMock receipt data:")
    for key, value in mock_receipt.items():
        print(f"  {key}: {value}")
    
    # Step 1: Format the receipt data using prepare_for_google_sheets
    print("\nStep 1: Formatting receipt data...")
    formatted_values = prepare_for_google_sheets(mock_receipt)
    
    print("\nFormatted values (returned from prepare_for_google_sheets):")
    for i, value in enumerate(formatted_values):
        print(f"  {i}: {value}")
    
    # Step 2: Append to Google Sheets
    print("\nStep 2: Appending to Google Sheets...")
    receipt_num = append_to_sheet(creds, sheet_id, formatted_values)
    
    if receipt_num:
        print(f"\n✅ Successfully wrote to Google Sheets with receipt #{receipt_num}!")
        print("\nPlease check your Google Sheet to verify the column order is correct.")
        print("The data should have been written with:")
        print(f"- Receipt #: {receipt_num}")
        print(f"- Date: {formatted_values[0]} (should be in the 'when' column)")
        print(f"- Who: {formatted_values[1]}")
        print(f"- What: {formatted_values[2]}")
        print(f"- Receipt value: {formatted_values[5]} (should be 'no')")
        return True
    else:
        print("\n❌ Failed to write to Google Sheets!")
        return False

if __name__ == "__main__":
    success = test_sheet_write()
    if success:
        print("\nTest completed successfully!")
    else:
        print("\nTest failed.") 