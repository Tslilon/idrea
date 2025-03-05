import os
import base64
import logging
from app.services.receipt_extraction_service import extract_from_image

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Path to the example receipt image
IMAGE_PATH = "example_receipt.jpg"

def encode_image_to_base64(image_path):
    """Encode an image file to base64."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def test_receipt_extraction():
    """Test the receipt extraction function with an example image."""
    print("Testing receipt extraction with the updated function...")
    
    # Encode the image to base64
    base64_image = encode_image_to_base64(IMAGE_PATH)
    
    # Call the extract_from_image function
    result, error = extract_from_image(base64_image)
    
    if error:
        print(f"Error: {error}")
        return False
    else:
        print("Extraction result:")
        for key, value in result.items():
            print(f"  {key}: {value}")
        
        # Verify that all required fields are present
        required_fields = ["what", "store_name", "total_amount"]
        missing_fields = [field for field in required_fields if field not in result]
        
        if missing_fields:
            print(f"Missing required fields: {', '.join(missing_fields)}")
            return False
        else:
            print("All required fields are present!")
            
            # Check if 'what' field contains English text (non-scientific evaluation)
            # English typically doesn't have words with all caps like "BOLSA TODO DULCE"
            if "BOLSA TODO DULCE" in result["what"]:
                print("Warning: Product name might not have been translated to English")
            
            return True

if __name__ == "__main__":
    success = test_receipt_extraction()
    if success:
        print("\nTest passed successfully!")
    else:
        print("\nTest failed.") 