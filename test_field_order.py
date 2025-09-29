import os
import logging
import json
from datetime import datetime

# Add the parent directory to the path so we can import the app modules
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the relevant functions
from app.utils.whatsapp_utils import parse_manual_receipt_entry, append_to_sheet, load_credentials
from app.services.receipt_extraction_service import prepare_for_google_sheets

# Configure logging to show debugging information
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def test_field_order():
    """
    Test that fields are properly ordered from parsing through to appending to Google Sheets
    """
    print("\n=== Testing Field Order ===\n")
    
    # 1. Sample input
    test_input = """What: test
Amount (euros): 123
IVA (euros): 
When: 20/04/2024
Receipt: yes
Store name: 
Company: NADLAN VRGN HOLDINGS SL
Payment method: 
Charge to: 
Comments:"""
    
    print("Input message:")
    print("-" * 40)
    print(test_input)
    print("-" * 40)
    
    # 2. Parse the input
    parsed_data = parse_manual_receipt_entry(test_input)
    print("\nParsed data:")
    for key, value in parsed_data.items():
        print(f"  {key}: '{value}'")
        
    # 3. Add sender name (simulating the real flow)
    parsed_data["sender_name"] = "Test User"
    
    # 4. Prepare data for Google Sheets
    print("\nPreparing for Google Sheets...")
    formatted_values = prepare_for_google_sheets(parsed_data)
    
    # Check the order of formatted values
    print("\nFormatted values (in order):")
    for i, value in enumerate(formatted_values):
        print(f"  {i}: {value}")
    
    # Verify the expected order
    expected_order = [
        "when (date)",
        "who (sender)",
        "what",
        "amount",
        "iva",
        "receipt",
        "store_name",
        "payment_method",
        "charge_to",
        "comments",
        "company"
    ]
    
    print("\nVerifying field order:")
    for i, field in enumerate(expected_order):
        if i < len(formatted_values):
            print(f"  Position {i} should be {field}: '{formatted_values[i]}'")
        else:
            print(f"  Position {i} missing: should be {field}")
    
    # 5. Optional: Test append_to_sheet function (but don't actually write to sheet)
    try:
        # Load credentials (needed to create the service)
        creds = load_credentials()
        if creds:
            print("\nSimulating append to sheet (not actually writing)...")
            # We'll mock this part to avoid actually writing to the sheet
            # Create a mock service function for append
            
            # Trace through how append_to_sheet would process the values
            if len(formatted_values) >= 11:
                when_date = formatted_values[0]
                who = formatted_values[1]
                what = formatted_values[2]
                amount = formatted_values[3]
                iva = formatted_values[4]
                receipt_value = formatted_values[5]
                
                print("\nHow append_to_sheet would extract values:")
                print(f"  When: '{when_date}'")
                print(f"  Who: '{who}'")
                print(f"  What: '{what}'")
                print(f"  Amount: '{amount}'")
                print(f"  IVA: '{iva}'")
                print(f"  Receipt: '{receipt_value}'")
                
                print("\nFinal row that would be written (with receipt number):")
                receipt_num = 999  # Mock receipt number
                final_values = [
                    receipt_num,
                    when_date,
                    who,
                    what,
                    amount,
                    iva,
                    receipt_value,
                    formatted_values[6] if len(formatted_values) > 6 else "",  # store_name
                    formatted_values[7] if len(formatted_values) > 7 else "",  # payment_method
                    formatted_values[8] if len(formatted_values) > 8 else "",  # charge_to
                    formatted_values[9] if len(formatted_values) > 9 else "",  # comments
                    formatted_values[10] if len(formatted_values) > 10 else "" # company
                ]
                print(f"  {final_values}")
        else:
            print("\nNo credentials available for testing append_to_sheet")
    except Exception as e:
        print(f"\nError testing append_to_sheet: {str(e)}")

if __name__ == "__main__":
    test_field_order() 