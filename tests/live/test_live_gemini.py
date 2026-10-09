"""
Live checks against the real Gemini API (costs a fraction of a cent per run).

    IDREA_LIVE=1 python -m pytest tests/live -q
"""
import os

import pytest

from app.services import receipt_extraction_service as res
from app.services import easter_eggs

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
pytestmark = pytest.mark.skipif(not os.getenv("IDREA_LIVE") or not os.getenv("GEMINI_API_KEY"),
                                reason="set IDREA_LIVE=1 and GEMINI_API_KEY to run")


def read(name):
    with open(os.path.join(ROOT, name), "rb") as f:
        return f.read()


def test_photo_receipt():
    details, error = res.extract_receipt_details(read("example_receipt.jpg"), "image")
    assert error is None, error
    assert details["total_amount"] and details["store_name"]


def test_pdf_invoice():
    details, error = res.extract_receipt_details(read("example.pdf"), "pdf")
    assert error is None, error
    assert details["total_amount"]


def test_oversized_pdf_page():
    """A 30x43in page (Chrome 'Save as PDF') used to OOM-kill the worker."""
    from io import BytesIO
    from PIL import Image, ImageDraw
    page = Image.new("RGB", (2200, 3111), "white")
    d = ImageDraw.Draw(page)
    for i, line in enumerate(["FACTURA F-77", "Papeleria Sol  NIF B12345678", "TOTAL 12,50 EUR", "IVA 21% 2,17"]):
        d.text((200, 300 + i * 120), line, fill="black", font_size=80)
    buf = BytesIO()
    page.save(buf, format="PDF", resolution=72.0)
    details, error = res.extract_receipt_details(buf.getvalue(), "pdf")
    assert error is None, error
    assert "12" in details["total_amount"]


def test_easter_egg_quip_model_answers():
    line = easter_eggs.generate_quip("Dana", {"what": "Coffee beans", "store_name": "Cafes El Magnifico"})
    assert line and len(line) <= 160
