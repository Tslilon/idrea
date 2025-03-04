import os
import sys
import json
from app.services.receipt_extraction_service import extract_receipt_details, format_extracted_details_for_whatsapp

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
    
    # Test image extraction
    test_image_extraction() 