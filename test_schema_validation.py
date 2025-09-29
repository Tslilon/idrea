import os
import base64
import json
import httpx
import logging
from typing import Optional
from pydantic import BaseModel
from openai import OpenAI

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define the receipt schema using Pydantic
class ReceiptDetails(BaseModel):
    what: str
    store_name: str
    total_amount: str
    iva: Optional[str] = None
    company: Optional[str] = None

# Path to the example receipt image
IMAGE_PATH = "example_receipt.jpg"

# OpenAI model to use
MODEL = "gpt-4o-mini"

def get_openai_client():
    """Initialize and return an OpenAI client."""
    try:
        # Create an httpx client with proper timeout
        http_client = httpx.Client(timeout=60.0)
        
        # Initialize the OpenAI client with the http_client
        client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            http_client=http_client
        )
        logging.info("Successfully created OpenAI client with custom HTTP client")
        return client
    except Exception as e:
        logging.error(f"Error initializing OpenAI client: {str(e)}")
        # Fallback
        try:
            # Try the simplest possible initialization
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            logging.info("Successfully created OpenAI client with fallback")
            return client
        except Exception as e2:
            logging.error(f"Fallback method also failed: {str(e2)}")
            raise RuntimeError(f"Could not initialize OpenAI client: {str(e)}, then: {str(e2)}")

def encode_image_to_base64(image_path):
    """Encode an image file to base64."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def extract_receipt_details_with_schema():
    """Extract receipt details from the image using OpenAI's structured outputs feature."""
    # Get the OpenAI client
    client = get_openai_client()
    
    # Encode the image to base64
    base64_image = encode_image_to_base64(IMAGE_PATH)
    
    # Define the JSON schema to enforce
    json_schema = {
        "type": "object",
        "properties": {
            "what": {"type": "string"},
            "store_name": {"type": "string"},
            "total_amount": {"type": "string"},
            "iva": {"type": "string"},
            "company": {"type": "string"}
        },
        "required": ["what", "store_name", "total_amount"]
    }
    
    try:
        # Create the API request with structured outputs
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": """
                    Extract receipt details and return as a JSON object with EXACTLY the following fields:
                    - what: A brief description of what was purchased (items or services)
                    - store_name: The name of the store or business that issued the receipt
                    - total_amount: The total amount paid (as a string)
                    - iva: The VAT/IVA tax amount (if available, as a string)
                    - company: The paying company from the closed list: NADLAN VRGN HOLDINGS SL, DILIGENTE RE MANAGEMENT SL, NADLAN ROSENFELD (only if clearly identifiable)
                    
                    IMPORTANT: The JSON response MUST contain the fields 'what', 'store_name', and 'total_amount'.
                    Return the extracted information in a flat JSON structure, not nested under other objects.
                """},
                {
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": "Please analyze this receipt image and extract the key details."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            response_format={"type": "json_object"}
        )
        
        # Extract the response content
        content = response.choices[0].message.content
        print("Raw API response content:")
        print(content)
        
        # Parse the JSON response
        result = json.loads(content)
        
        # Validate with Pydantic
        validated_result = ReceiptDetails(**result)
        print("\nValidated result (after Pydantic validation):")
        print(validated_result.model_dump_json(indent=2))
        
        return validated_result
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return None

if __name__ == "__main__":
    print("Testing receipt extraction with schema validation...")
    result = extract_receipt_details_with_schema()
    if result:
        print("\nExtraction successful!")
    else:
        print("\nExtraction failed.") 