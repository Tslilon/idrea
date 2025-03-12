import os
import base64
import logging
import json
from app.services.receipt_extraction_service import extract_receipt_details

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Path to the target PDF file
PDF_PATH = "data/temp_receipts/868.pdf"

def test_pdf_extraction():
    """Test the PDF receipt extraction function with a specific PDF file."""
    print("\n=== Testing PDF Receipt Extraction ===\n")
    
    # Check if the PDF file exists
    if not os.path.exists(PDF_PATH):
        print(f"Error: Test PDF file not found at {PDF_PATH}")
        return False
    
    print(f"Using PDF file: {PDF_PATH}")
    
    # Read the PDF file
    with open(PDF_PATH, "rb") as pdf_file:
        pdf_content = pdf_file.read()
    
    print(f"PDF file size: {len(pdf_content)} bytes")
    
    # Call the extract_receipt_details function for PDF processing
    result, error = extract_receipt_details(pdf_content, content_type="pdf")
    
    if error:
        print(f"Error during extraction: {error}")
        return False
    else:
        print("\nExtraction result:")
        # Print formatted results
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        # Verify required fields
        required_fields = ["what", "store_name", "total_amount", "iva", "date"]
        missing_fields = [field for field in required_fields if field not in result or not result[field]]
        
        if missing_fields:
            print(f"\nWarning: Missing or empty required fields: {', '.join(missing_fields)}")
        else:
            print("\nAll required fields are present and filled!")
        
        # Check specific field values
        if result.get("what", "").strip():
            print(f"\nWhat: {result['what']} ✓")
        else:
            print("\nWarning: 'what' field is empty or not descriptive enough")
            
        if result.get("store_name", "").strip():
            print(f"Store: {result['store_name']} ✓")
        else:
            print("Warning: 'store_name' field is empty")
            
        if result.get("total_amount", "").strip():
            print(f"Total: {result['total_amount']} ✓")
        else:
            print("Warning: 'total_amount' field is empty")
            
        if result.get("iva", "").strip():
            print(f"IVA: {result['iva']} ✓")
        else:
            print("Note: 'iva' field is empty (might be correct if not on receipt)")
            
        if result.get("date", "").strip():
            print(f"Date: {result['date']} ✓")
        else:
            print("Warning: 'date' field is empty")
        
        return True

if __name__ == "__main__":
    success = test_pdf_extraction()
    
    print("\n=== Test Summary ===")
    if success:
        print("✅ PDF extraction test completed successfully!")
    else:
        print("❌ PDF extraction test failed.") 