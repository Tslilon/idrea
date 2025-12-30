#!/usr/bin/env python3
"""Test script for Gemini receipt extraction."""

import base64
import io
import json
import sys
import os

print("Testing Gemini receipt extraction...")
print("=" * 50)

# Test imports
print("1. Testing imports...")
try:
    from google import genai
    from google.genai import types
    from pydantic import BaseModel, Field
    from PIL import Image
    from pdf2image import convert_from_path, convert_from_bytes
    print("   All imports successful!")
except ImportError as e:
    print(f"   Import error: {e}")
    sys.exit(1)

# Define the schema (matching the one in receipt_extraction_service.py)
class ReceiptDetails(BaseModel):
    """Schema for receipt extraction."""
    what: str = Field(default="", description="Concise description of the purchase or product (what was bought) in English")
    store_name: str = Field(default="", description="The name of the store or vendor as shown on the receipt")
    total_amount: str = Field(default="", description="The total amount paid")
    iva: str = Field(default="", description="The VAT/IVA tax amount")
    date: str = Field(default="", description="The date of the transaction in DD/MM/YYYY format if available")
    company: str = Field(default="", description="The paying company from the closed list: NADLAN VRGN HOLDINGS SL, DILIGENTE RE MANAGEMENT SL, NADLAN ROSENFELD")
    invoice_number: str = Field(default="", description="The invoice or receipt number as shown on the document")
    supplier_id: str = Field(default="", description="The supplier/vendor tax ID (CIF/NIF)")

# Test client initialization
print("2. Testing Gemini client initialization...")
try:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("   ERROR: GEMINI_API_KEY environment variable not set")
        print("   Add it to .env file: GEMINI_API_KEY=your_key_here")
        sys.exit(1)
    client = genai.Client(api_key=api_key)
    print("   Client created successfully!")
except Exception as e:
    print(f"   Client error: {e}")
    sys.exit(1)

# Determine which file to test with
test_file = sys.argv[1] if len(sys.argv) > 1 else "example.pdf"
print(f"3. Loading test file: {test_file}")

try:
    if test_file.lower().endswith('.pdf'):
        # Convert PDF to image
        print("   Converting PDF to image...")
        images = convert_from_path(test_file, first_page=1, last_page=1)
        if not images:
            print("   Failed to convert PDF")
            sys.exit(1)
        image = images[0]
        print(f"   Converted PDF page to image: {image.size}")
    else:
        # Load image directly
        with open(test_file, "rb") as f:
            image_bytes = f.read()
        image = Image.open(io.BytesIO(image_bytes))
        print(f"   Loaded image: {image.size}")
except FileNotFoundError:
    print(f"   {test_file} not found")
    sys.exit(1)
except Exception as e:
    print(f"   Error loading file: {e}")
    sys.exit(1)

PROMPT = """Analyze this receipt image and extract the following key information:
1. What: Brief up to 5 words description of the purchase (what was bought - name of the items or services, etc., and translate to English if suitable. if it's a lot of itmes, give the category. E.g. "White sugar packets from Dirty Harry (500 units of 7 grams)" -> "White sugar packets")
2. Store name: The business name that issued the receipt (do not confuse this with the client company name)
3. Total amount: The total amount paid (including any taxes)
4. IVA/VAT amount: The Spanish VAT tax amount (if shown on receipt)
5. Date: The date of the transaction (if shown on receipt)
6. Company: The paying company, the client, do not confuse this with the store name (see details below)
7. Invoice number: The invoice or receipt number
8. Supplier ID: The vendor/supplier tax ID (CIF/NIF)

Important guidelines:
- If a field isn't visible or doesn't exist, leave it empty
- Maintain original formatting
- For amounts, extract exactly as shown on the receipt (no need for the currency symbol)

When extracting the store name:
- Use the **issuer/sender of the receipt** (often shown under "Nombre" or with NIF/CIF, e.g. vendor or business name)
- Do NOT take the "cliente" or "client" section (where NADLAN / DILIGENTE / ROSENFELD may appear). Those belong only in the "company" field.
- Don't include slogans or addresses

When extracting the company:
- Look specifically in the "cliente" / "client" / billing section for the paying company (the client)
- Only select from this exact list: "NADLAN VRGN HOLDINGS SL", "DILIGENTE RE MANAGEMENT SL", "NADLAN ROSENFELD"
- Be conservative: only assign a company if it's clearly identifiable
- If uncertain or no clear company identifier is found, leave this field empty
- Use the exact company name from the list above

When extracting the invoice number:
- Look for labels like "Factura No.", "Invoice #", "Num. Factura", "N. Factura", "Recibo No.", "N° de factura", etc.
- Extract the number/code exactly as shown
- If no invoice number is visible, leave this field empty

When extracting the supplier ID (CIF/NIF):
- Look for the vendor's tax identification number near the vendor/store name section
- Usually labeled as "CIF", "NIF", "N.I.F.", "C.I.F.", or appears near the vendor address
- Typically format is a letter + 8 digits (e.g., B12345678) but can vary
- Do NOT use the client's CIF - only the vendor/supplier CIF
- If no supplier ID is visible, leave this field empty

Be precise and accurate in your extraction."""

print("4. Calling Gemini API (model: gemini-3-flash-preview)...")
try:
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=[PROMPT, image],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ReceiptDetails,
        ),
    )
    
    print("5. Processing response...")
    if hasattr(response, "parsed") and response.parsed:
        print("   Parsed response (structured):")
        result = response.parsed.model_dump()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        # Validate expected fields for example.pdf
        if "example.pdf" in test_file:
            print("\n6. Validating against expected values...")
            expected = {
                "store_name": "Cristina Oria",
                "company": "DILIGENTE RE MANAGEMENT SL",
                "invoice_number": "CO286608",
                "supplier_id": "B86980844",
                "date": "04/12/2025",
                "total_amount": "296,88",
            }
            for key, expected_val in expected.items():
                actual = result.get(key, "")
                match = expected_val.lower() in actual.lower() if actual else False
                status = "OK" if match else "MISMATCH"
                print(f"   {key}: '{actual}' (expected contains '{expected_val}') [{status}]")
    elif hasattr(response, "text") and response.text:
        print("   Text response:")
        print(response.text)
    else:
        print("   No response content")
        
except Exception as e:
    print(f"   API error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("=" * 50)
print("Test complete!")
