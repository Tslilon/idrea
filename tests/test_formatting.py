"""
Characterization tests: pin down how receipts are shown to users and written to the
sheet. These pass against the code that ran in production before the October 2026
changes, so a failure here means user-visible behaviour changed.
"""
import re
from datetime import datetime

from app.services.receipt_extraction_service import format_extracted_details_for_whatsapp, prepare_for_google_sheets
from app.utils.whatsapp_utils import parse_manual_receipt_entry, append_to_sheet, get_first_name

FULL = dict(
    what="Office supplies", store_name="Papeleria Sol", total_amount="12,50", iva="2,17",
    date="01/10/2026", company="DILIGENTE RE MANAGEMENT SL", invoice_number="F-2026-17",
    supplier_id="B12345678",
)


def test_whatsapp_format_full():
    assert format_extracted_details_for_whatsapp(dict(FULL)) == (
        "What: Office supplies\n"
        "Amount (euros): 12,50 €\n"
        "IVA (euros): 2,17 €\n"
        "When: 01/10/2026\n"
        "Store name: Papeleria Sol\n"
        "Company: DILIGENTE RE MANAGEMENT SL\n"
        "Invoice number: F-2026-17\n"
        "Supplier ID: B12345678"
    )


def test_whatsapp_format_missing_fields():
    assert format_extracted_details_for_whatsapp({}) == (
        "What: Purchase\n"
        "Amount (euros): 0 €\n"
        "IVA (euros): \n"
        "When: (empty - current date will be used)\n"
        "Store name: Unknown Store\n"
        "Company: (not identified)\n"
        "Invoice number: (not found)\n"
        "Supplier ID: (not found)"
    )


def test_whatsapp_format_optional_fields():
    text = format_extracted_details_for_whatsapp(dict(FULL, payment_method="card", charge_to="Project X", comments="team lunch"))
    assert text.endswith("Payment method: card\nCharge to: Project X\nComments: team lunch")


def test_sheet_values_order():
    values = prepare_for_google_sheets(dict(FULL, sender_name="Dana Levi", receipt_number=2555))
    assert values == [
        "2026-10-01 12:00", "Dana Levi", "Office supplies", "12,50", "2,17", "yes", "Papeleria Sol",
        "", "", "", "DILIGENTE RE MANAGEMENT SL", "F-2026-17", "B12345678", 2555,
    ]


def test_sheet_date_formats():
    assert prepare_for_google_sheets({"date": "2026-10-03"})[0] == "2026-10-03 12:00"
    assert prepare_for_google_sheets({"when": "03.10.2026"})[0] == "2026-10-03 12:00"
    assert prepare_for_google_sheets({"date": "05/10/2026", "when": "06/10/2026"})[0] == "2026-10-05 12:00"
    # Unparseable or missing -> now
    now_prefix = datetime.now().strftime("%Y-%m-%d")
    assert prepare_for_google_sheets({"date": "sometime"})[0].startswith(now_prefix)
    assert prepare_for_google_sheets({})[0].startswith(now_prefix)
    assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", prepare_for_google_sheets({})[0])


def test_manual_entry_parsing():
    parsed = parse_manual_receipt_entry(
        "*What*: Taxi to airport\n*Amount* (euros): 1.234,56\nIVA (euros): 21,5\n"
        "When: 02/10/2026\nReceipt: Y\nStore name: Taxi BCN\nCompany: NADLAN ROSENFELD\n"
        "Invoice number: 77\nSupplier ID: \nPayment method: card\nCharge to:\nComments: late flight"
    )
    assert parsed == {
        "what": "Taxi to airport", "total_amount": "1234.56", "iva": "21.5", "when": "02/10/2026",
        "has_receipt": "yes", "store_name": "Taxi BCN", "company": "NADLAN ROSENFELD",
        "invoice_number": "77", "payment_method": "card", "comments": "late flight",
    }


class _Sheets:
    def __init__(self, existing):
        self.rows = [[str(n)] for n in existing]
        self.appended = None

    def spreadsheets(self):
        sheets = self

        class Values:
            def get(self, spreadsheetId, range):
                return type("R", (), {"execute": lambda _: {"values": sheets.rows}})()

            def append(self, spreadsheetId, range, valueInputOption, body):
                sheets.appended = body["values"][0]
                return type("R", (), {"execute": lambda _: {"updates": {"updatedCells": 14}}})()

        return type("S", (), {"values": lambda _: Values()})()


def test_append_to_sheet_amount_formatting(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    sheets = _Sheets([7, 9, 8])
    import app.utils.whatsapp_utils as wu
    monkeypatch.setattr(wu, "build", lambda *a, **k: sheets)
    row = ["2026-10-01 12:00", "Dana", "Taxi", "12.5", "€2,10", "yes", "Taxi BCN", "", "", "", "", "", ""]
    assert append_to_sheet(object(), "sheet", row) == 10
    assert sheets.appended == [10, "2026-10-01 12:00", "Dana", "Taxi", "12,5", "2,10", "yes", "Taxi BCN", "", "", "", "", "", ""]
    # A receipt number assigned at upload time is reused
    assert append_to_sheet(object(), "sheet", row + [2555]) == 2555
    assert sheets.appended[0] == 2555


def test_first_name():
    assert get_first_name("Dana Levi") == "Dana"
    assert get_first_name("") == ""
