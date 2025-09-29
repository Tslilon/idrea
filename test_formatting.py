import os
import logging
from datetime import datetime
from app.services.receipt_extraction_service import prepare_for_google_sheets

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_prepare_for_google_sheets():
    """Test the prepare_for_google_sheets function with sample receipt data."""
    print("Testing prepare_for_google_sheets formatting...")
    
    # Create a mock receipt entry that simulates a manual form input
    mock_receipt = {
        "sender_name": "Test User",
        "what": "test item",
        "total_amount": "123",
        "iva": "",
        "has_receipt": "yes",
        "store_name": "Test Store",
        "payment_method": "",
        "charge_to": "",
        "comments": "",
        "when": "20/04/2024"  # This is the date field
    }
    
    # Call prepare_for_google_sheets
    formatted_values = prepare_for_google_sheets(mock_receipt)
    
    print("\nFormatted Values (to be sent to Google Sheets):")
    print(f"Length: {len(formatted_values)}")
    for i, value in enumerate(formatted_values):
        print(f"{i}: {value}")
    
    # Expected columns in order
    expected_columns = [
        "when", "who", "what", "amount", "IVA", "receipt", 
        "store name", "payment method", "charge to", "comments", "company"
    ]
    
    print("\nExpected columns mapping:")
    for i, column_name in enumerate(expected_columns):
        if i < len(formatted_values):
            print(f"{column_name}: {formatted_values[i]}")
        else:
            print(f"{column_name}: MISSING!")
    
    # Verify the date is properly formatted as the first element
    if formatted_values and '2024-04-20' in formatted_values[0]:
        print("\n✅ Date is correctly formatted and positioned as the first element!")
    else:
        print("\n❌ Date formatting or positioning issue!")
        if formatted_values:
            print(f"First element is: {formatted_values[0]}")
    
    return formatted_values

def simulate_append_to_sheet(values_list):
    """Simulate what append_to_sheet does with the formatted values."""
    print("\nSimulating append_to_sheet function...")
    
    # Add a mock receipt number
    receipt_number = 999
    
    # Process values with formatting (simplified version of what append_to_sheet does)
    processed_values = []
    for value in values_list:
        # Just pass through the values for this test
        processed_values.append(value)
    
    # Add receipt number at the beginning
    final_values = [receipt_number] + processed_values
    
    print("\nFinal values to be written to Google Sheets:")
    print(f"Length: {len(final_values)}")
    for i, value in enumerate(final_values):
        print(f"{i}: {value}")
    
    # Expected columns with receipt number
    expected_columns = [
        "number", "when", "who", "what", "amount", "IVA", "receipt", 
        "store name", "payment method", "charge to", "comments"
    ]
    
    print("\nFinal columns mapping:")
    for i, column_name in enumerate(expected_columns):
        if i < len(final_values):
            print(f"{column_name}: {final_values[i]}")
        else:
            print(f"{column_name}: MISSING!")
    
    return final_values

if __name__ == "__main__":
    print("=== Testing Google Sheets Formatting ===\n")
    
    # Test prepare_for_google_sheets
    formatted_values = test_prepare_for_google_sheets()
    
    # Test simulated append_to_sheet
    final_values = simulate_append_to_sheet(formatted_values)
    
    print("\n=== Test Complete ===") 