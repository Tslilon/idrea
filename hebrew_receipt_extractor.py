#!/usr/bin/env python3
import base64
import csv
import os
import json
import logging
import sys
import io
from typing import Dict, List, Tuple, Optional, Any
from io import BytesIO
import re
from datetime import datetime, timedelta
from PIL import Image
import argparse
import glob

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

# ===== Set your OpenAI API key here =====
# SECURITY NOTE: Use environment variable instead of hardcoding API key
# Set your API key with: export OPENAI_API_KEY="your-key-here"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    logging.error("OPENAI_API_KEY environment variable is not set!")
    sys.exit(1)
# =======================================

# Import OpenAI after setting environment variables
from openai import OpenAI

# OpenAI API configuration
OPENAI_MODEL = "gpt-4o"  # Using gpt-4o for better image analysis and Hebrew support
OPENAI_MAX_TOKENS = 4096  # Set token limit based on complexity of receipts
OPENAI_TEMPERATURE = 0.0  # Use 0 temperature for deterministic outputs

# Define schema for receipt data in Hebrew
RECEIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "profession": {
            "type": "string",
            "description": "The profession or category of the service provider"
        },
        "vendor_name": {
            "type": "string",
            "description": "Name of the vendor or service provider as shown on the receipt"
        },
        "receipt_number": {
            "type": "string",
            "description": "The receipt or invoice number if available"
        },
        "amount": {
            "type": "string",
            "description": "The total amount paid (including any taxes)"
        },
        "date": {
            "type": "string",
            "description": "The date of the transaction in DD/MM/YYYY format if available"
        },
        "notes": {
            "type": "string",
            "description": "Any additional notes or comments about the receipt"
        }
    },
    "required": ["vendor_name", "amount", "date"],
    "additionalProperties": False
}

# Extraction prompt for Hebrew receipts
EXTRACTION_PROMPT = """
Analyze this receipt image and extract the following key information in Hebrew:

1. בעלי מקצוע (Profession/Category): The profession or category of the service provider
2. שם בעל המקצוע (Vendor Name): The full name of the business or service provider that issued the receipt
3. מספר קבלה/חשבונית (Receipt/Invoice Number): The receipt or invoice number if visible
4. סכום (Amount): The total amount paid (including any taxes)
5. תאריך (Date): The date of the transaction
6. היערות (Notes): Any additional relevant information or notes

Important guidelines:
- Extract the text exactly as shown on the receipt, including Hebrew text
- If a field isn't visible or doesn't exist, use an empty string
- If barely visible, mention it in the notes
- For amounts, include the currency symbol if shown
- For dates, maintain the format as shown on the receipt
- These receipts are primarily in Hebrew - please extract text in its original Hebrew form

Be precise and accurate in your extraction. Do not translate Hebrew text to English.
"""

def get_openai_client():
    """Initialize and return an OpenAI client."""
    try:
        # Try to initialize with the provided API key
        client = OpenAI(api_key=OPENAI_API_KEY)
        logging.info("Successfully created OpenAI client")
        return client
    except Exception as e:
        logging.error(f"Error initializing OpenAI client: {str(e)}")
        raise RuntimeError(f"Could not initialize OpenAI client: {str(e)}")

def preprocess_image(image_path: str) -> bytes:
    """
    Preprocess an image for optimal analysis.
    
    Args:
        image_path: Path to the image file
        
    Returns:
        Optimized image bytes
    """
    try:
        # Open the image file
        with Image.open(image_path) as img:
            # Resize large images to save bandwidth
            max_size = 1600  # Max dimension
            if max(img.size) > max_size:
                ratio = max_size / max(img.size)
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img = img.resize(new_size, Image.LANCZOS)
            
            # Convert to RGB if needed (e.g., for PNG with transparency)
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Save optimized image to bytes
            with BytesIO() as buffer:
                img.save(buffer, format="JPEG", quality=80, optimize=True)
                buffer.seek(0)
                return buffer.read()
    except Exception as e:
        logging.error(f"Error preprocessing image {image_path}: {str(e)}")
        raise

def extract_from_image(image_path: str) -> Tuple[Optional[Dict], Optional[str]]:
    """
    Extract receipt details from an image using OpenAI's Vision API.
    
    Args:
        image_path: Path to the image file
        
    Returns:
        Tuple of (extracted_details, error_message) where error_message is None on success
    """
    try:
        # Preprocess the image
        image_bytes = preprocess_image(image_path)
        base64_image = base64.b64encode(image_bytes).decode()
        
        # Get OpenAI client
        client = get_openai_client()
        
        # Create the request to the OpenAI API with the image and structured output
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            max_tokens=OPENAI_MAX_TOKENS,
            temperature=OPENAI_TEMPERATURE,
            messages=[
                {"role": "system", "content": "Extract Hebrew receipt details and return as JSON."},
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
                    "name": "HebrewReceiptDetails",
                    "schema": RECEIPT_SCHEMA
                }
            }
        )
        
        # Extract and parse the JSON from the API response
        result_text = response.choices[0].message.content
        
        # Log the response content for debugging (limited to avoid huge logs)
        logging.info(f"Image: {os.path.basename(image_path)} - Response (first 100 chars): {result_text[:100]}...")
        
        try:
            # Parse the JSON response
            result_json = json.loads(result_text)
            
            # Map JSON keys to the required Hebrew column names for the CSV
            mapped_result = {
                "בעלי מקצוע": result_json.get("profession", ""),
                "שם בעל המקצוע": result_json.get("vendor_name", ""),
                "מספר קבלה/חשבונית": result_json.get("receipt_number", ""),
                "סכום": result_json.get("amount", ""),
                "תאריך": result_json.get("date", ""),
                "היערות": result_json.get("notes", "")
            }
            
            return mapped_result, None
            
        except json.JSONDecodeError:
            logging.error(f"Failed to parse JSON response for {image_path}: {result_text}")
            return None, "Invalid JSON response from OpenAI"
            
    except Exception as e:
        logging.error(f"Error in extract_from_image for {image_path}: {str(e)}")
        return None, f"{str(e)}"

def process_directory(directory_path: str, output_csv: str) -> None:
    """
    Process all image files in a directory and save results to CSV.
    
    Args:
        directory_path: Path to directory containing receipt images
        output_csv: Path to output CSV file
    """
    # Validate directory
    if not os.path.isdir(directory_path):
        logging.error(f"Directory not found: {directory_path}")
        sys.exit(1)
    
    # Find all image files
    image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.gif', '*.webp', '*.bmp', '*.tiff', '*.tif']
    image_files = []
    
    for ext in image_extensions:
        image_files.extend(glob.glob(os.path.join(directory_path, ext)))
        # Also look in subdirectories
        image_files.extend(glob.glob(os.path.join(directory_path, '**', ext), recursive=True))
    
    # Remove duplicates and sort
    image_files = sorted(set(image_files))
    
    if not image_files:
        logging.error(f"No image files found in {directory_path}")
        sys.exit(1)
    
    logging.info(f"Found {len(image_files)} image files to process")
    
    # Process images and collect results
    results = []
    
    for i, image_path in enumerate(image_files):
        try:
            logging.info(f"Processing image {i+1}/{len(image_files)}: {os.path.basename(image_path)}")
            extracted_data, error = extract_from_image(image_path)
            
            if error:
                logging.error(f"Failed to extract from {image_path}: {error}")
                continue
                
            if extracted_data:
                # Add the image file name for reference
                extracted_data["Image File"] = os.path.basename(image_path)
                results.append(extracted_data)
                logging.info(f"Successfully extracted data from {image_path}")
            else:
                logging.warning(f"No data extracted from {image_path}")
                
        except Exception as e:
            logging.error(f"Error processing {image_path}: {str(e)}")
    
    # Write results to CSV
    if results:
        try:
            # Determine CSV fields - use the first result as a template
            # Make sure Image File is the last column
            fields = list(results[0].keys())
            if "Image File" in fields:
                fields.remove("Image File")
            fields.append("Image File")
            
            with open(output_csv, 'w', newline='', encoding='utf-8-sig') as f:  # utf-8-sig adds BOM for Excel compatibility
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(results)
                
            logging.info(f"Successfully wrote {len(results)} records to {output_csv}")
        except Exception as e:
            logging.error(f"Error writing to CSV: {str(e)}")
    else:
        logging.error("No results to write to CSV")

def main():
    """Main function to parse arguments and execute the script."""
    parser = argparse.ArgumentParser(description="Extract data from Hebrew receipts and save to CSV")
    parser.add_argument("directory", help="Directory containing receipt images")
    parser.add_argument("--output", "-o", default="extracted_receipts.csv", 
                        help="Output CSV file path (default: extracted_receipts.csv)")
    
    args = parser.parse_args()
    
    logging.info(f"Starting Hebrew receipt extraction process")
    logging.info(f"Input directory: {args.directory}")
    logging.info(f"Output CSV: {args.output}")
    
    process_directory(args.directory, args.output)
    
    logging.info("Process complete")

if __name__ == "__main__":
    main() 