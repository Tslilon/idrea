import os
import sys
import json
from app.services.receipt_extraction_service import extract_receipt_details, format_extracted_details_for_whatsapp
from app.utils.whatsapp_utils import process_text_message, load_credentials, get_receipt_number

def test_text_message():
    """Test processing a text message with receipt details"""
    print("Testing text message processing...")
    
    # Sample text message with receipt details
    text = """What: Office supplies
Amount: 50€
IVA: 10.50€
Receipt: yes
Store name: Office Depot
Payment method: card
Charge to: Marketing
Comments: Monthly supplies"""
    
    # Load credentials for Google API
    try:
        creds = load_credentials()
        print("✅ Credentials loaded successfully")
    except Exception as e:
        print(f"❌ Error loading credentials: {str(e)}")
        return
    
    # Get the next receipt number
    try:
        sheet_id = os.getenv("GOOGLE_SHEET_ID")
        if not sheet_id:
            print("❌ GOOGLE_SHEET_ID environment variable not set")
            return
            
        receipt_num = get_receipt_number(creds, sheet_id)
        print(f"✅ Next receipt number: {receipt_num}")
    except Exception as e:
        print(f"❌ Error getting receipt number: {str(e)}")
        return
    
    # Process the text message
    try:
        # We'll just print what would happen instead of actually sending messages
        print("\nProcessing text message:")
        print("-" * 50)
        print(text)
        print("-" * 50)
        
        # Call the function that would process this in the real system
        # But modify it to just return the result instead of sending messages
        result = process_text_message_test(text, "Test User", creds, "+1234567890")
        print(f"\n✅ Text message processed: {result}")
    except Exception as e:
        print(f"❌ Error processing text message: {str(e)}")

def process_text_message_test(text, name, creds, sender_waid):
    """Test version of process_text_message that doesn't send actual messages"""
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    
    # Check if this looks like a receipt form submission
    form_fields = ["What", "Amount", "Store name"]
    form_detected = sum(1 for field in form_fields if field in text) >= 2
    
    if form_detected:
        # This looks like a form submission, so parse it and save to Google Sheets
        parts = text.split('\n')
        update_data = [name]
        
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
            
            # Store in parsed_data
            parsed_data[key] = value
        
        # Check if we have the minimal required fields
        required_fields = ["What", "Amount"]
        missing_fields = [field for field in required_fields if field not in parsed_data]
        
        if missing_fields:
            # In real system, we'd send a message about missing fields
            missing_text = ", ".join(missing_fields)
            return f"Missing fields: {missing_text}"
            
        # Process the data for Google Sheets
        fields_to_process = ["What", "Amount", "IVA", "Receipt", "Store name", "Payment method", "Charge to", "Comments"]
        
        for field in fields_to_process:
            value = parsed_data.get(field, "")
            update_data.append(value)
            
        # In a real system, we'd write to Google Sheets here
        # receipt_num = append_to_sheet(creds, sheet_id, update_data)
        
        # For testing, we'll just print what would be saved
        print("\nData that would be saved to Google Sheets:")
        for i, field in enumerate(["Name"] + fields_to_process):
            print(f"{field}: {update_data[i]}")
        
        # Return what would be sent to the user
        return f"Receipt details would be saved with receipt #{get_receipt_number(creds, sheet_id)}"
    else:
        # If it's not a form submission, we'd send the form template
        return "Would send form template"

def test_image_extraction():
    """Test extracting details from a sample image"""
    print("\nTesting image extraction...")
    print("Note: This requires an actual image file and OpenAI API key")
    
    # Check if OpenAI API key is set
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY environment variable not set")
        return
    
    # Ask for an image path
    image_path = input("Enter path to a receipt image (or press Enter to skip): ")
    if not image_path:
        print("Skipping image extraction test")
        return
    
    # Check if the file exists
    if not os.path.exists(image_path):
        print(f"❌ File not found: {image_path}")
        return
    
    # Read the image file
    try:
        with open(image_path, 'rb') as f:
            image_content = f.read()
        print(f"✅ Image loaded: {image_path}")
    except Exception as e:
        print(f"❌ Error reading image: {str(e)}")
        return
    
    # Extract receipt details
    try:
        receipt_details, status = extract_receipt_details(image_content, "image")
        
        if receipt_details:
            print("\n✅ Receipt details extracted:")
            print(json.dumps(receipt_details, indent=2))
            
            # Format for WhatsApp
            message = format_extracted_details_for_whatsapp(receipt_details)
            print("\nFormatted message for WhatsApp:")
            print("-" * 50)
            print(message)
            print("-" * 50)
        else:
            print(f"❌ Failed to extract receipt details: {status}")
    except Exception as e:
        print(f"❌ Error in extraction: {str(e)}")

if __name__ == "__main__":
    print("Receipt Extraction Test Script")
    print("=" * 50)
    
    # Test text message processing
    test_text_message()
    
    # Test image extraction
    test_image_extraction() 