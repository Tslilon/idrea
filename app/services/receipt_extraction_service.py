import base64
import sys
import io
import json
import logging
import os
import tempfile
from typing import Dict, Optional, List, Any, Tuple
from io import BytesIO
import re
from datetime import datetime, timedelta

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
OPENAI_MODEL = "gpt-4o-mini"  # Using gpt-4o for better image analysis
OPENAI_MAX_TOKENS = 4096  # Set token limit based on complexity of receipts
OPENAI_TEMPERATURE = 0.0  # Use 0 temperature for deterministic outputs
EXTRACTION_DELAY = 0.5  # Add delay between extraction attempts if needed

# Updated schema to include the "what" field
RECEIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "what": {
            "type": "string",
            "description": "Concise description of the purchase or product (what was bought) in English"
        },
        "store_name": {
            "type": "string",
            "description": "The name of the store or vendor as shown on the receipt"
        },
        "total_amount": {
            "type": "string",
            "description": "The total amount paid"
        },
        "iva": {
            "type": "string",
            "description": "The VAT/IVA tax amount"
        },
        "date": {
            "type": "string",
            "description": "The date of the transaction in DD/MM/YYYY format if available"
        }
    },
    "required": ["what", "store_name", "total_amount", "iva", "date"],
    "additionalProperties": False
}

EXTRACTION_PROMPT = """
Analyze this receipt image and extract the following key information:
1. What: Brief up to 5 words description of the purchase (what was bought - name of the items or services, etc., and translate to English if suitable. if it's a lot of itmes, give the category. E.g. "White sugar packets from Dirty Harry (500 units of 7 grams)" -> "White sugar packets")
2. Store name: The business name that issued the receipt
3. Total amount: The total amount paid (including any taxes)
4. IVA/VAT amount: The Spanish VAT tax amount (if shown on receipt)
5. Date: The date of the transaction (if shown on receipt)

Important guidelines:
- If a field isn't visible or doesn't exist, leave it empty
- Maintain original formatting
- For amounts, extract exactly as shown on the receipt (no need for the currency symbol)

When extracting the "what" field:
- Provide a very brief description of what was purchased
- If multiple items, summarize (e.g., "Office supplies", "Computer equipment")
- If not clearly visible, infer from context or mark as "unknown"

When extracting the store name:
- Use the most prominent business name on the receipt
- Don't include slogans or addresses

When extracting amounts:
- If multiple totals exist, choose the final/largest one

When extracting the date:
- Use the format DD/MM/YYYY if possible
- If multiple dates are shown, choose the transaction/purchase date
- If no date is visible, leave this field empty

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
    
    # Date (When)
    date = details.get("date", "")
    if not date and "when" in details:
        date = details.get("when", "")
    if date:
        message.append(f"When: {date}")
    else:
        message.append("When: (empty - current date will be used)")
    
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
    
    # Extract the sender's name from the details
    sender_name = details.get("sender_name", "")
    
    # Process the date (from "date" or "when" field)
    date_value = None
    if "date" in details and details["date"]:
        date_value = details["date"]
    elif "when" in details and details["when"]:
        date_value = details["when"]
        
    # Format the date for Google Sheets
    formatted_date = ""
    if date_value:
        try:
            # Skip instruction text
            if date_value.startswith("(can be empty"):
                logging.info(f"Instruction text detected in date: '{date_value}'. Will use current date.")
                formatted_date = datetime.now().strftime('%Y-%m-%d %H:%M')
            # If it's in DD/MM/YYYY format, parse and convert to YYYY-MM-DD HH:MM
            elif re.match(r'\d{2}/\d{2}/\d{4}', date_value):
                try:
                    # Verify it's a valid date
                    parsed_date = datetime.strptime(date_value, "%d/%m/%Y")
                    # Check if the day matches (to catch invalid dates like 31/04/2024)
                    original_day = int(date_value.split('/')[0])
                    if original_day == parsed_date.day:
                        # Format as YYYY-MM-DD 12:00 (noon)
                        formatted_date = parsed_date.strftime('%Y-%m-%d 12:00')
                        logging.info(f"Formatted date '{date_value}' to: {formatted_date}")
                    else:
                        logging.warning(f"Invalid date detected: {date_value} - day doesn't match after parsing")
                        formatted_date = datetime.now().strftime('%Y-%m-%d %H:%M')
                except ValueError:
                    logging.warning(f"Date appears to be in right format but is invalid: {date_value}")
                    formatted_date = datetime.now().strftime('%Y-%m-%d %H:%M')
            else:
                # Try other date formats
                date_formats = [
                    "%d/%m/%Y",  # 31/12/2023
                    "%d-%m-%Y",  # 31-12-2023
                    "%d.%m.%Y",  # 31.12.2023
                    "%Y-%m-%d",  # 2023-12-31 (ISO format)
                    "%Y/%m/%d",  # 2023/12/31
                ]
                
                parsed_date = None
                for fmt in date_formats:
                    try:
                        parsed_date = datetime.strptime(date_value, fmt)
                        # Check if the day matches (for formats with day first)
                        if fmt.startswith("%d"):
                            original_day = date_value.split(fmt[2])[0]
                            if original_day.isdigit() and int(original_day) != parsed_date.day:
                                logging.warning(f"Invalid date detected: {date_value} - day doesn't match after parsing")
                                parsed_date = None
                                continue
                        break
                    except ValueError:
                        continue
                
                if parsed_date:
                    # Format as YYYY-MM-DD 12:00 (noon)
                    formatted_date = parsed_date.strftime('%Y-%m-%d 12:00')
                    logging.info(f"Parsed and formatted date '{date_value}' to: {formatted_date}")
                else:
                    # Special keywords
                    if date_value.lower() == "today":
                        formatted_date = datetime.now().strftime('%Y-%m-%d 12:00')
                    elif date_value.lower() == "yesterday":
                        formatted_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d 12:00')
                    else:
                        # If we can't parse it, use current date/time
                        logging.warning(f"Could not parse date: {date_value}. Using current date.")
                        formatted_date = datetime.now().strftime('%Y-%m-%d %H:%M')
        except Exception as e:
            logging.warning(f"Error formatting date: {e}. Using current date.")
            formatted_date = datetime.now().strftime('%Y-%m-%d %H:%M')
    else:
        # No date provided, use current date/time
        formatted_date = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    # Create values array in EXACTLY the order expected by the spreadsheet
    # [when, who, what, amount, IVA, receipt, store name, payment method, charge to, comments]
    # Number is added by append_to_sheet
    final_values = [
        formatted_date,                                # when
        sender_name,                                   # who
        details.get("what", ""),                       # what
        details.get("total_amount", details.get("amount", "")),  # amount
        details.get("iva", ""),                        # IVA
        details.get("has_receipt", "yes"),             # receipt (use user value or default to yes)
        details.get("store_name", ""),                 # store name
        details.get("payment_method", ""),             # payment method
        details.get("charge_to", ""),                  # charge to
        details.get("comments", "")                    # comments
    ]
    
    # Add receipt_number as the last element if it exists
    # This will be used by append_to_sheet to ensure consistent numbering
    if "receipt_number" in details:
        final_values.append(details.get("receipt_number"))
        logging.info(f"Added receipt number {details.get('receipt_number')} to prepared values")
    
    # Log the values being returned for debugging
    logging.info(f"Prepared values for Google Sheets: {final_values}")
    
    return final_values

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
        
        # Create the request to the OpenAI API with the image and structured output
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            max_tokens=OPENAI_MAX_TOKENS,
            temperature=OPENAI_TEMPERATURE,
            messages=[
                {"role": "system", "content": "Extract receipt details and return as JSON."},
                {
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": EXTRACTION_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "ReceiptDetails",
                    "strict": True,
                    "schema": RECEIPT_SCHEMA
                }
            }
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
            
            # Return the validated JSON (schema is enforced by the API)
            return result_json, None
            
        except json.JSONDecodeError:
            logging.error(f"Failed to parse JSON response: {result_text}")
            return None, "Invalid JSON response from OpenAI"
            
    except Exception as e:
        logging.error(f"Error in extract_from_image: {str(e)}")
        return None, f"{str(e)}" 