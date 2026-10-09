"""
End-to-end: signed WhatsApp webhook -> Flask app -> outgoing WhatsApp messages,
Drive uploads, Sheet rows and Gemini calls (all faked at the network edge).
"""
import os

import pytest

from app.utils import whatsapp_utils as wu
from conftest import USER_WAID, ADMIN_WAID, jpeg_bytes, pdf_bytes, TEST_ENV

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def button_ids(payload):
    return [b["reply"]["id"] for b in payload["interactive"]["action"]["buttons"]]


# ---------------------------------------------------------------- webhook plumbing

def test_verification_handshake(world):
    ok = world.client.get("/webhook", query_string={"hub.mode": "subscribe", "hub.verify_token": "test-verify-token", "hub.challenge": "42"})
    assert ok.status_code == 200 and ok.data == b"42"
    assert world.client.get("/webhook", query_string={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "1"}).status_code == 403
    assert world.client.get("/webhook").status_code == 400


def test_health(world):
    assert world.client.get("/health").json["status"] == "healthy"


def test_status_updates_are_never_rate_limited(world):
    raw = (b'{"object":"whatsapp_business_account","entry":[{"changes":[{"value":{"statuses":'
           b'[{"id":"wamid.x","status":"delivered"}]}}]}]}')
    codes = {world.post_raw(raw).status_code for _ in range(150)}
    assert codes == {200}


def test_unknown_paths_are_rate_limited(world):
    codes = [world.client.get("/wp-login.php").status_code for _ in range(7)]
    assert codes[:5] == [404] * 5 and codes[-1] == 429


def test_signature_log_mode_processes_unsigned(world):
    assert world.send_text("hello", sign=False).status_code == 200
    assert world.to_user(), "message should still be answered in log-only mode"


def test_signature_enforce_mode(world, monkeypatch):
    monkeypatch.setenv("WEBHOOK_SIGNATURE_MODE", "enforce")
    assert world.send_text("hello", sign=False).status_code == 403
    assert world.to_user() == []
    assert world.send_text("hello").status_code == 200
    assert world.to_user()


def test_signature_enforce_rejects_tampered_body(world, monkeypatch):
    monkeypatch.setenv("WEBHOOK_SIGNATURE_MODE", "enforce")
    import hashlib, hmac
    raw = b'{"object":"whatsapp_business_account","entry":[]}'
    sig = hmac.new(TEST_ENV["APP_SECRET"].encode(), raw, hashlib.sha256).hexdigest()
    tampered = raw.replace(b"[]", b"[ ]")
    r = world.client.post("/webhook", data=tampered, headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"})
    assert r.status_code == 403


# ---------------------------------------------------------------- receipt via photo

def test_photo_receipt_review_and_confirm_with_button(world):
    world.google.sheet_rows = [[2553], [2554]]
    assert world.send_image(jpeg_bytes()).status_code == 200

    # Drive upload named after the new receipt number
    assert [f["name"] for f in world.google.drive_files.values()] == ["2555.jpg"]
    # User sees the details with three buttons
    review = world.to_user()[-1]
    assert review["type"] == "interactive"
    assert button_ids(review) == ["receipt_confirm", "receipt_edit", "receipt_cancel"]
    body = world.text_of(review)
    assert "Hi Dana!" in body and "Amount (euros): 12,50 €" in body and "Receipt #2555 has been created." in body
    # Admin notified, user marked as read/typing
    assert any("Receipt 2555 created" in world.text_of(m) for m in world.to_admin())
    assert world.typing
    assert world.pending()["receipt_number"] == 2555

    world.press("receipt_confirm")
    row = world.google.sheet_rows[-1]
    assert row[0] == 2555 and row[1] == "2026-10-01 12:00" and row[2] == "Dana Levi" and row[4] == "12,50"
    assert row[11:] == ["DILIGENTE RE MANAGEMENT SL", "F-2026-17", "B12345678"]
    assert "Your receipt number is 2555" in world.last_to_user()
    assert world.pending() is None


def test_typed_yes_still_confirms(world):
    world.send_image(jpeg_bytes())
    world.send_text("yes")
    assert len(world.google.sheet_rows) == 1
    assert world.pending() is None


def test_cancel_button_deletes_drive_file(world):
    world.send_image(jpeg_bytes())
    (file_id,) = world.google.drive_files
    world.press("receipt_cancel")
    assert world.google.deleted_files == [file_id]
    assert world.pending() is None and world.google.sheet_rows == []
    assert "cancelled" in world.last_to_user()


def test_edit_button_explains_how(world):
    world.send_image(jpeg_bytes())
    world.press("receipt_edit")
    assert "Amount: 42,50" in world.last_to_user()
    assert world.pending() is not None


def test_field_corrections_reach_the_sheet(world):
    world.send_image(jpeg_bytes())
    world.send_text("Company: nadlan rosenfeld\nInvoice number: INV-9\nSupplier ID: B7654321\nWhen: 05/10/2026\nAmount: 99,90")
    review = world.to_user()[-1]
    assert review["type"] == "interactive"
    body = world.text_of(review)
    assert "Company: NADLAN ROSENFELD" in body and "When: 05/10/2026" in body and "Invoice number: INV-9" in body
    world.send_text("confirm")
    row = world.google.sheet_rows[-1]
    assert row[1] == "2026-10-05 12:00"
    assert row[4] == "99,90"
    assert row[11:] == ["NADLAN ROSENFELD", "INV-9", "B7654321"]


def test_ambiguous_company_kept_as_typed(world):
    world.send_image(jpeg_bytes())
    world.send_text("Company: nadlan")
    assert world.pending()["company"] == "nadlan"


def test_sheet_failure_keeps_pending_receipt(world):
    world.send_image(jpeg_bytes())
    world.google.fail_append = True
    world.send_text("confirm")
    assert "couldn't save" in world.last_to_user()
    assert world.pending() is not None
    world.google.fail_append = False
    world.send_text("confirm")
    assert len(world.google.sheet_rows) == 1 and world.pending() is None


def test_button_failure_falls_back_to_text(world):
    world.fail_interactive = True
    world.send_image(jpeg_bytes())
    last = world.to_user()[-1]
    assert last["type"] == "text"
    assert 'reply "confirm"' in last["text"]["body"] and "Amount (euros): 12,50 €" in last["text"]["body"]


def test_long_review_split_into_text_and_buttons(world):
    world.gemini.result["what"] = "x" * 1100
    world.send_image(jpeg_bytes())
    *_, details, buttons = world.to_user()
    assert details["type"] == "text" and "x" * 1100 in details["text"]["body"]
    assert buttons["type"] == "interactive" and len(world.text_of(buttons)) <= 1024


def test_image_with_caption_is_filed_under_existing_receipt(world):
    world.send_image(jpeg_bytes(), caption="2550")
    assert [f["name"] for f in world.google.drive_files.values()] == ["2550.jpg"]
    assert world.gemini.calls == []
    assert "#2550" in world.last_to_user()


# ---------------------------------------------------------------- PDFs and documents

def test_oversized_pdf_is_rendered_within_budget(world):
    # 2200x3111pt pages crashed production in Oct 2026 (854MB peak at 200dpi)
    world.send_document(pdf_bytes(2200, 3111), "invoice.pdf", "application/pdf")
    (call,) = world.gemini.calls
    assert max(call["sizes"][0]) <= 2400
    assert world.to_user()[-1]["type"] == "interactive"


def test_a4_pdf_rendering_unchanged(world):
    world.send_document(pdf_bytes(595, 842), "invoice.pdf", "application/pdf")
    (call,) = world.gemini.calls
    # 200 dpi, as before
    assert call["sizes"][0] == (1653, 2339)
    assert [f["name"] for f in world.google.drive_files.values()] == ["1.pdf"]


def test_only_first_pdf_page_sent_by_default(world):
    world.send_document(pdf_bytes(595, 842, pages=3), "invoice.pdf", "application/pdf")
    assert len(world.gemini.calls[0]["sizes"]) == 1


def test_image_sent_as_document_uses_image_path(world):
    world.send_document(jpeg_bytes((3000, 4000)), "IMG_1234.jpg", "image/jpeg")
    assert [f["name"] for f in world.google.drive_files.values()] == ["1.jpg"]
    assert world.google.drive_files["file1"]["mimetype"] == "image/jpeg"
    assert max(world.gemini.calls[0]["sizes"][0]) <= 1600


def test_real_example_files(world):
    with open(os.path.join(FIXTURES, "example.pdf"), "rb") as f:
        world.send_document(f.read(), "example.pdf", "application/pdf")
    with open(os.path.join(FIXTURES, "example_receipt.jpg"), "rb") as f:
        world.send_image(f.read())
    assert len(world.gemini.calls) == 2


# ---------------------------------------------------------------- retries from Meta

def test_duplicate_delivery_processed_once(world):
    image = jpeg_bytes()
    world.send_image(image, message_id="wamid.same")
    world.send_image(image, message_id="wamid.same")
    assert len(world.google.drive_files) == 1
    assert len(world.gemini.calls) == 1


def test_crashing_message_gives_up_after_two_attempts(world, monkeypatch):
    clock = [1_000_000.0]
    monkeypatch.setattr(wu.time, "time", lambda: clock[0])

    def crash(*a, **k):
        raise MemoryError("simulated OOM kill")  # the worker dies before finishing
    monkeypatch.setattr(wu, "_process_whatsapp_message", crash)
    monkeypatch.setattr(wu, "finish_message_processing", lambda message_id: None)

    for _ in range(2):
        world.send_document(b"%PDF", "x.pdf", "application/pdf", message_id="wamid.poison")
        clock[0] += 200  # Meta retries a few minutes later
    world.send_document(b"%PDF", "x.pdf", "application/pdf", message_id="wamid.poison")
    assert "wasn't able to process" in world.last_to_user()
    assert any("could not be processed" in world.text_of(m) for m in world.to_admin())


def test_retry_while_first_attempt_still_running_is_skipped(world):
    assert wu.begin_message_processing("wamid.slow") == "process"
    assert wu.begin_message_processing("wamid.slow") == "duplicate"


# ---------------------------------------------------------------- text flows

def test_unknown_text_gets_form_template(world):
    world.send_text("hello")
    assert "Please provide the receipt details" in world.last_to_user()
    assert any("Dana Levi sent:\n\nhello" == world.text_of(m) for m in world.to_admin())


def test_manual_form_entry_saves_row(world):
    world.google.sheet_rows = [[10]]
    world.send_text("What: Taxi\nAmount: 23,40\nStore name: Taxi BCN\nWhen: 02/10/2026")
    row = world.google.sheet_rows[-1]
    assert row[0] == 11 and row[3] == "Taxi" and row[4] == "23,4" and row[7] == "Taxi BCN"
    assert "Receipt #11" in world.last_to_user()


def test_confirm_without_pending(world):
    world.send_text("confirm")
    assert "don't have any pending" in world.last_to_user()
