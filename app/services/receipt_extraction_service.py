import base64
import sys
import io
import json
import logging
import os
import tempfile
from typing import Dict, Optional, List, Any, Tuple
from io import BytesIO

# Clear any proxy environment variables that might be causing issues
os.environ.pop("HTTP_PROXY", None)
os.environ.pop("HTTPS_PROXY", None)
os.environ.pop("http_proxy", None)
os.environ.pop("https_proxy", None)

import requests
from openai import OpenAI
from PIL import Image
try:
    from pdf2image import convert_from_bytes
except ImportError:
    logging.warning("pdf2image not available - PDF processing will be disabled")
    convert_from_bytes = None

# Initialize OpenAI client - moved to function to avoid initialization at module level
def get_openai_client():
    # Print the OpenAI SDK version for debugging
    import openai
    import inspect
    import httpx
    logging.info(f"Using OpenAI SDK version: {openai.__version__}")
    
    # Use the proper initialization method based on the OpenAI SDK version
    try:
        # For newer versions (1.x.x) - create a client with the correct parameters
        # Create an httpx client with the correct proxy parameter (not proxies)
        http_client = httpx.Client(timeout=60.0)
        
        # Initialize the OpenAI client with the http_client
        client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            http_client=http_client
        )
        logging.info(f"Successfully created OpenAI client with custom HTTP client")
        return client
    except Exception as e:
        logging.error(f"Error initializing OpenAI client: {str(e)}")
        # Fallback for older versions or if the above fails
        try:
            # Try the simplest possible initialization
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            logging.info(f"Successfully created OpenAI client with fallback")
            return client
        except Exception as e2:
            logging.error(f"Fallback method also failed: {str(e2)}")
            raise RuntimeError(f"Could not initialize OpenAI client: {str(e)}, then: {str(e2)}")

# OpenAI API configuration
OPENAI_MODEL = "gpt-4o"  # Using gpt-4o for better image analysis
OPENAI_MAX_TOKENS = 4096  # Set token limit based on complexity of receipts
OPENAI_TEMPERATURE = 0.0  # Use 0 temperature for deterministic outputs
EXTRACTION_DELAY = 0.5  # Add delay between extraction attempts if needed

# Updated schema to include the "what" field
RECEIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "what": {
            "type": "string",
            "description": "Description of the purchase or product (what was bought)"
        },
        "store_name": {
            "type": "string",
            "description": "The name of the store or vendor as shown on the receipt"
        },
        "total_amount": {
            "type": "string",
            "description": "The total amount paid, including currency symbol if available"
        },
        "iva": {
            "type": "string",
            "description": "The VAT/IVA tax amount, including currency symbol if available"
        }
    },
    "required": ["what", "store_name", "total_amount"]
}

# Updated prompt to extract the "what" field as well
EXTRACTION_PROMPT = """
Analyze this receipt image and extract the following key information:
1. What: Brief description of the purchase (what was bought - items or services)
2. Store name: The business name that issued the receipt
3. Total amount: The total amount paid (including any taxes)
4. IVA/VAT amount: The Spanish VAT tax amount (if shown on receipt)

Important guidelines:
- If a field isn't visible or doesn't exist, leave it empty
- Maintain original formatting (currency symbols, etc.)
- For amounts, extract exactly as shown on the receipt (with currency symbols if present)
- Respond ONLY with the JSON data according to the schema - no other text

When extracting the "what" field:
- Provide a brief description of what was purchased
- If multiple items, summarize (e.g., "Office supplies", "Computer equipment")
- If not clearly visible, infer from context or mark as "unknown"

When extracting the store name:
- Use the most prominent business name on the receipt
- Don't include slogans or addresses

When extracting amounts:
- Preserve the exact format shown on receipt
- Include currency symbols if present
- If multiple totals exist, choose the final/largest one

IMPORTANT: Return your response as a JSON object with EXACTLY these field names:
{
  "what": "Description of purchase",
  "store_name": "Name of the store",
  "total_amount": "Total amount with currency",
  "iva": "VAT amount if available"
}

Be precise and accurate in your extraction.
"""

def preprocess_image(image: bytes) -> Image.Image:
    """Preprocess an image for optimal OCR and analysis."""
    try:
        # Load image from bytes
        img = Image.open(io.BytesIO(image))
        
        # Convert to RGB if needed
        if img.mode != 'RGB':
            img = img.convert('RGB')
            
        # Optional: Enhance image for better OCR
        # from PIL import ImageEnhance
        # enhancer = ImageEnhance.Contrast(img)
        # img = enhancer.enhance(1.5)  # Increase contrast
        
        return img
    except Exception as e:
        logging.error(f"Error preprocessing image: {str(e)}")
        raise

def convert_pdf_to_images(pdf_bytes: bytes) -> List[Image.Image]:
    """Convert PDF file to a list of PIL Image objects."""
    if convert_from_bytes is None:
        logging.error("PDF conversion is not available - pdf2image not installed")
        return []
        
    try:
        # Convert PDF directly from bytes to reduce disk I/O
        images = convert_from_bytes(pdf_bytes, dpi=200)  # Reduced DPI to save memory
        return images
    except Exception as e:
        logging.error(f"Error converting PDF to images: {str(e)}")
        return []

def extract_receipt_details(file_content, content_type="image"):
    """
    Extract details from a receipt image or PDF.
    
    Args:
        file_content: Binary content of the file (image or PDF)
        content_type: Type of content ('image' or 'pdf')
        
    Returns:
        Tuple of (extracted_details, error_message) where error_message is None on success
    """
    try:
        if content_type == "pdf":
            # For PDFs, we need to convert to image first
            try:
                # Import here to avoid dependency issues
                from pdf2image import convert_from_bytes
                
                # Convert first page of PDF to image
                images = convert_from_bytes(file_content, first_page=1, last_page=1)
                
                if not images:
                    return None, "Failed to convert PDF to image"
                
                # Process the first page image
                with BytesIO() as image_buffer:
                    # Use JPEG format with reduced quality to save bandwidth
                    images[0].save(image_buffer, format="JPEG", quality=70, optimize=True)
                    image_buffer.seek(0)
                    image_content = image_buffer.read()
                
                # Now extract from the image
                return extract_from_image(base64.b64encode(image_content).decode())
                
            except ImportError as e:
                logging.warning(f"PDF conversion failed due to missing dependencies: {str(e)}")
                return None, "PDF processing not available"
                
        else:  # Default to image
            # Optimize image before sending to OpenAI
            try:
                with Image.open(BytesIO(file_content)) as img:
                    # Resize large images to save bandwidth
                    max_size = 1600  # Max dimension
                    if max(img.size) > max_size:
                        ratio = max_size / max(img.size)
                        new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                        img = img.resize(new_size, Image.LANCZOS)
                    
                    # Convert to RGB if needed (e.g., for PNG with transparency)
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    # Save optimized image
                    with BytesIO() as buffer:
                        img.save(buffer, format="JPEG", quality=80, optimize=True)
                        buffer.seek(0)
                        optimized_content = buffer.read()
                
                # Extract from the optimized image
                return extract_from_image(base64.b64encode(optimized_content).decode())
                
            except Exception as e:
                logging.warning(f"Image optimization failed, using original: {str(e)}")
                # Fall back to using the original image
                return extract_from_image(base64.b64encode(file_content).decode())
                
    except Exception as e:
        logging.error(f"Error in extract_receipt_details: {str(e)}")
        return None, f"{str(e)}"

def format_extracted_details_for_whatsapp(details):
    """
    Format extracted receipt details for display in WhatsApp.
    
    Args:
        details: Dictionary of extracted receipt details
        
    Returns:
        Formatted message string
    """
    # Required fields that must be present
    required_fields = ["what", "store_name", "total_amount"]
    
    # Ensure all required fields are present
    for field in required_fields:
        if field not in details or not details[field]:
            if field == "what":
                details[field] = "Purchase"  # Default value for missing what field
            elif field == "store_name":
                details[field] = "Unknown Store"  # Default value for missing store name
            elif field == "total_amount":
                details[field] = "0"  # Default value for missing amount
    
    # Build a readable message with all extracted information
    message = []
    
    # What was purchased
    what = details.get("what", "Purchase")
    message.append(f"What: {what}")
    
    # Amount
    total_amount = details.get("total_amount", "")
    if total_amount:
        # Check if the amount already has a currency symbol
        if not any(symbol in total_amount for symbol in ['€', '£', '$']):
            total_amount = f"{total_amount} €"
        message.append(f"Amount (euros): {total_amount}")
    else:
        message.append("Amount (euros): 0.00 €")
    
    # IVA (VAT)
    iva = details.get("iva", "")
    if iva:
        # Check if the IVA already has a currency symbol
        if not any(symbol in iva for symbol in ['€', '£', '$']):
            iva = f"{iva} €"
        message.append(f"IVA (euros): {iva}")
    else:
        message.append("IVA (euros): ")
    
    # Store name
    store_name = details.get("store_name", "")
    message.append(f"Store name: {store_name}")
    
    # Payment Method (if available)
    payment_method = details.get("payment_method", "")
    if payment_method:
        message.append(f"Payment method: {payment_method}")
    
    # Charge To (if available)
    charge_to = details.get("charge_to", "")
    if charge_to:
        message.append(f"Charge to: {charge_to}")
    
    # Additional comments/notes (if any)
    comments = details.get("comments", "")
    if comments:
        message.append(f"Comments: {comments}")
        
    return "\n".join(message)

def prepare_for_google_sheets(details):
    """
    Prepare the extracted receipt details for insertion into Google Sheets.
    
    Args:
        details: Dictionary of extracted receipt details
        
    Returns:
        List of values in the order expected by Google Sheets
    """
    # Log received details for debugging
    logging.info(f"Preparing these details for Google Sheets: {details}")
    
    # The order of fields in Google Sheets
    fields_order = ["what", "amount", "iva", "receipt", "store_name", "payment_method", "charge_to", "comments"]
    
    # Initialize an empty list with the correct length
    values = [""] * len(fields_order)
    
    # Map the extracted details to the corresponding fields
    if details:
        # Map what field (index 0)
        if "what" in details and details["what"]:
            values[0] = details["what"]
        
        # Map amount field (index 1)
        # First check for total_amount (from OpenAI extraction) and then amount (from manual entry)
        amount_value = None
        if "total_amount" in details and details["total_amount"]:
            amount_value = details["total_amount"]
            logging.info(f"Found total_amount field: {amount_value}")
        elif "amount" in details and details["amount"]:
            amount_value = details["amount"]
            logging.info(f"Found amount field: {amount_value}")
            
        if amount_value is not None:
            # Simply pass the amount value as is - no complex formatting
            # Remove any currency symbols but keep the decimal as is
            amount_str = str(amount_value).replace('€', '').strip()
            logging.info(f"Prepared amount for Google Sheets (simple): {amount_str}")
            values[1] = amount_str
        else:
            logging.warning("No amount or total_amount field found in receipt details")
        
        # Map IVA field (index 2)
        if "iva" in details and details["iva"]:
            # Simply pass the IVA value as is - no complex formatting
            iva_str = str(details["iva"]).replace('€', '').strip()
            logging.info(f"Prepared IVA for Google Sheets (simple): {iva_str}")
            values[2] = iva_str
        
        # Always set receipt to yes (index 3)
        values[3] = "yes"
        
        # Map store name field (index 4)
        if "store_name" in details and details["store_name"]:
            values[4] = details["store_name"]
        
        # Map payment method field (index 5) if available
        if "payment_method" in details and details["payment_method"]:
            values[5] = details["payment_method"]
        
        # Map charge_to field (index 6) if available
        if "charge_to" in details and details["charge_to"]:
            values[6] = details["charge_to"]
        
        # Map comments field (index 7) if available
        if "comments" in details and details["comments"]:
            values[7] = details["comments"]
    
    # Log the values being returned for debugging
    logging.info(f"Prepared values for Google Sheets: {values}")
    
    return values

def extract_from_image(base64_image):
    """
    Extract receipt details from a base64-encoded image using OpenAI's Vision API.
    
    Args:
        base64_image: Base64-encoded image data
        
    Returns:
        Dictionary of extracted receipt details, or None if extraction failed and an error message
    """
    try:
        client = get_openai_client()
        
        # Create the request to the OpenAI API with the image
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            max_tokens=OPENAI_MAX_TOKENS,
            temperature=OPENAI_TEMPERATURE,
            messages=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": "Extract the receipt details from this image."},
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
        
        # Extract and parse the JSON from the API response
        result_text = response.choices[0].message.content
        
        # Log the response content for debugging
        logging.info(f"OpenAI API response content (first 200 chars): {result_text[:200]}...")
        
        try:
            # Parse the JSON response
            result_json = json.loads(result_text)
            
            # Log the parsed JSON for debugging
            logging.info(f"Complete parsed JSON from OpenAI: {json.dumps(result_json, indent=2, ensure_ascii=False)}")
            
            # Normalize field names - convert from OpenAI format to our expected schema
            normalized_json = {}
            
            # Map of OpenAI's field names to our expected schema names
            field_map = {
                "What": "what",
                "what": "what",
                "Store name": "store_name", 
                "store_name": "store_name",
                "Total amount": "total_amount",
                "total_amount": "total_amount",
                "IVA/VAT amount": "iva",
                "iva": "iva",
                "IVA": "iva"
            }
            
            # Convert fields using the map
            for key, value in result_json.items():
                normalized_key = field_map.get(key)
                if normalized_key:
                    normalized_json[normalized_key] = value
                else:
                    # Keep any other fields as-is
                    normalized_json[key.lower().replace(" ", "_")] = value
            
            logging.info(f"Normalized JSON fields: {', '.join(normalized_json.keys())}")
            
            # Validate the JSON against our schema
            for field in ["what", "store_name", "total_amount"]:
                if field not in normalized_json:
                    logging.warning(f"Missing required field after normalization: {field}")
                    # Add default values for missing fields
                    if field == "what":
                        normalized_json[field] = "Purchase"
                    elif field == "store_name":
                        normalized_json[field] = "Unknown Store"
                    elif field == "total_amount":
                        normalized_json[field] = "0"
            
            # Return the normalized JSON
            return normalized_json, None
        except json.JSONDecodeError:
            logging.error(f"Failed to parse JSON response: {result_text}")
            return None, "Invalid JSON response from OpenAI"
            
    except Exception as e:
        logging.error(f"Error in extract_from_image: {str(e)}")
        return None, f"{str(e)}" 