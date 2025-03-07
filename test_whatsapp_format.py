import sys
import os
import logging
import json
from datetime import datetime

# Add the parent directory to the path so we can import the app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the relevant functions from whatsapp_utils
from app.utils.whatsapp_utils import parse_manual_receipt_entry, prepare_for_google_sheets, load_credentials, append_to_sheet

# Configure logging to show debugging information
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def test_field_recognition():
    """Test that our parser can recognize fields in various formats"""
    print("\n=== Testing Field Recognition Capabilities ===\n")
    
    # Test various ways users might enter amount fields
    test_inputs = [
        # Original format
        """What: Office supplies
Amount (euros): 42.50
IVA (euros): 8.93
When: 15/06/2023
Receipt: yes
Store name: Office Depot
Payment method: credit card
Charge to: CompanyX
Comments: For the new employees""",

        # Different amount formats
        """What: Office supplies
AMOUNT: 42.50
iva: 8.93
When: 15/06/2023
Receipt: yes
Store name: Office Depot
Payment method: credit card
Charge to: CompanyX
Comments: For the new employees""",

        # With extra text in amount fields
        """What: Office supplies
Amount in euros: 42.50
IVA Euros: 8.93
When: 15/06/2023
Receipt: yes
Store name: Office Depot
Payment method: credit card
Charge to: CompanyX
Comments: For the new employees""",

        # Mixed case
        """What: Office supplies
AmOuNt: 42.50
IvA: 8.93
When: 15/06/2023
Receipt: yes
Store name: Office Depot
Payment method: credit card
Charge to: CompanyX
Comments: For the new employees"""
    ]
    
    for i, test_input in enumerate(test_inputs):
        print(f"\nTest Case #{i+1}:")
        print("-" * 40)
        print(test_input)
        print("-" * 40)
        
        # Parse the input
        result = parse_manual_receipt_entry(test_input)
        
        # Check if the amounts were correctly recognized
        if 'total_amount' in result:
            print(f"✓ Amount correctly recognized: {result['total_amount']}")
        else:
            print("✗ Amount not recognized")
            
        if 'iva' in result:
            print(f"✓ IVA correctly recognized: {result['iva']}")
        else:
            print("✗ IVA not recognized")
            
        # Print all recognized fields for debugging
        print("\nAll recognized fields:")
        for key, value in result.items():
            print(f"  {key}: {value}")
        
        print("\n")

def test_whatsapp_input():
    """Test a real WhatsApp input format and see if we can successfully process it"""
    print("\n=== Testing Real WhatsApp Input Format ===\n")
    
    # Simulate a WhatsApp message
    whatsapp_message = """What: Plant for office
Amount euros: 20.00
IVA euros: 4.2
When: 15/06/2023
Receipt: yes
Store name: Florist Shop
Payment method: credit card
Charge to: Office
Comments: For reception desk"""
    
    # Parse the input
    result = parse_manual_receipt_entry(whatsapp_message)
    
    # Print the result
    print("Parsed fields:")
    for key, value in result.items():
        print(f"  {key}: {value}")
    
    # Format for sheets
    formatted_values = prepare_for_google_sheets(result)
    
    # Print the formatted values
    print("\nFormatted for Google Sheets:")
    print(formatted_values)
    
    # Try to append to the sheet if we have credentials
    try:
        creds = load_credentials()
        if creds:
            # Your sheet ID (replace with actual ID for testing)
            # sheet_id = "your-sheet-id-here"
            # result = append_to_sheet(creds, sheet_id, formatted_values)
            # print(f"\nAppended to sheet: {result}")
            print("\nCredentials loaded successfully (skipping actual append)")
        else:
            print("\nNo credentials available for sheet append")
    except Exception as e:
        print(f"\nError with credentials: {str(e)}")

def test_empty_fields():
    """Test with a format that has empty fields"""
    print("\n=== Testing Format with Empty Fields ===\n")
    
    # User-provided test format with empty fields
    test_input = """What: test
Amount (euros): 123
IVA (euros): 
When: 20/04/2024
Receipt: yes
Store name: 
Payment method: 
Charge to: 
Comments:"""
    
    print("Input message:")
    print("-" * 40)
    print(test_input)
    print("-" * 40)
    
    # Parse the input
    result = parse_manual_receipt_entry(test_input)
    
    # Check essential fields
    print("\nKey field detection:")
    if 'what' in result:
        print(f"✓ What field detected: {result['what']}")
    else:
        print("✗ What field not detected")
        
    if 'total_amount' in result:
        print(f"✓ Amount field detected: {result['total_amount']}")
    else:
        print("✗ Amount field not detected")
        
    if 'iva' in result:
        print(f"✓ IVA field detected: {result['iva']}")
    else:
        print("✗ IVA field not present or empty")
        
    if 'when' in result:
        print(f"✓ When field detected: {result['when']}")
    else:
        print("✗ When field not detected")
    
    # Print all parsed fields
    print("\nAll parsed fields:")
    for key, value in result.items():
        print(f"  {key}: '{value}'")
    
    # Format for Google Sheets
    formatted_values = prepare_for_google_sheets(result)
    
    # Print the formatted values
    print("\nFormatted for Google Sheets:")
    print(formatted_values)
    
    # Verify the IVA field in the formatted values (should be empty or handle properly)
    iva_index = 4  # IVA is typically in position 4 in the formatted list
    if len(formatted_values) > iva_index:
        print(f"\nIVA field in formatted output: '{formatted_values[iva_index]}'")
    else:
        print("\nIVA field not present in formatted output")

if __name__ == "__main__":
    # Run all tests
    test_field_recognition()
    test_whatsapp_input()
    test_empty_fields()  # Added new test for empty fields 