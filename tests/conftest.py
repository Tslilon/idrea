"""
Test harness for the WhatsApp bot.

The real Flask app handles signed webhook requests exactly as in production;
only the network edges are faked: the WhatsApp Cloud API (requests.get/post),
Google Drive/Sheets (googleapiclient.build) and Gemini (get_gemini_client).
"""
import hashlib
import hmac
import io
import json
import os
import sys
import itertools
from types import SimpleNamespace

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TEST_ENV = {
    "APP_SECRET": "test-app-secret",
    "VERIFY_TOKEN": "test-verify-token",
    "ACCESS_TOKEN": "test-access-token",
    "VERSION": "v20.0",
    "PHONE_NUMBER_ID": "111111111",
    "RECIPIENT_WAID": "+34600000099",
    "GOOGLE_SHEET_ID": "sheet-id",
    "GOOGLE_FOLDER_ID": "folder-id",
    "GOOGLE_SERVICE_ACCOUNT_FILE": "unused-in-tests.json",
    "LOG_LEVEL": "WARNING",
}
os.environ.update(TEST_ENV)

import requests  # noqa: E402
from app import create_app  # noqa: E402
from app.utils import whatsapp_utils as wu  # noqa: E402
from app.services import receipt_extraction_service as res  # noqa: E402
from app.views import limiter  # noqa: E402

USER_WAID = "34600000001"
ADMIN_WAID = "+34600000099"


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, content=b"", content_type="application/json"):
        self.status_code = status_code
        self._json = json_data
        self.content = content
        self.headers = {"Content-Type": content_type}
        self.text = json.dumps(json_data) if json_data is not None else ""

    def json(self):
        return self._json

    def iter_content(self, chunk_size=8192):
        for i in range(0, len(self.content), chunk_size):
            yield self.content[i:i + chunk_size]

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


class FakeRequest:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()


class FakeGoogle:
    """Just enough of the Drive v3 and Sheets v4 APIs for the bot."""

    def __init__(self):
        self.sheet_rows = []           # rows below the header, column A = receipt number
        self.drive_files = {}          # id -> {"name", "mimetype", "size"}
        self.deleted_files = []
        self.fail_append = False
        self._ids = itertools.count(1)

    # Drive
    def files(self):
        google = self

        class Files:
            def create(self, body, media_body, fields):
                def run():
                    file_id = f"file{next(google._ids)}"
                    google.drive_files[file_id] = {"name": body["name"], **media_body}
                    return {"id": file_id}
                return FakeRequest(run)

            def delete(self, fileId):
                def run():
                    google.deleted_files.append(fileId)
                    google.drive_files.pop(fileId, None)
                    return {}
                return FakeRequest(run)
        return Files()

    # Sheets
    def spreadsheets(self):
        google = self

        class Values:
            def get(self, spreadsheetId, range):
                return FakeRequest(lambda: {"values": [[str(r[0])] for r in google.sheet_rows]})

            def append(self, spreadsheetId, range, valueInputOption, body):
                def run():
                    if google.fail_append:
                        raise RuntimeError("Sheets API unavailable")
                    google.sheet_rows.extend(body["values"])
                    return {"updates": {"updatedCells": len(body["values"][0])}}
                return FakeRequest(run)

        return SimpleNamespace(values=lambda: Values())


class FakeGemini:
    """Stands in for genai.Client; returns canned extraction results."""

    def __init__(self):
        self.result = dict(
            what="Office supplies", store_name="Papeleria Sol", total_amount="12,50", iva="2,17",
            date="01/10/2026", company="DILIGENTE RE MANAGEMENT SL", invoice_number="F-2026-17",
            supplier_id="B12345678",
        )
        self.calls = []  # list of lists of PIL image sizes, one per call
        self.models = SimpleNamespace(generate_content=self._generate_content)

    def _generate_content(self, model, contents, config):
        images = contents[1:]
        self.calls.append({"model": model, "sizes": [im.size for im in images]})
        return SimpleNamespace(parsed=res.ReceiptDetails(**self.result), text=None)


class World:
    """Everything the bot talks to, recorded for assertions."""

    def __init__(self, client, monkeypatch, tmp_path):
        self.client = client
        self.tmp_path = tmp_path
        self.google = FakeGoogle()
        self.gemini = FakeGemini()
        self.sent = []          # outgoing WhatsApp payloads (dicts)
        self.typing = []        # message ids we sent typing indicators for
        self.media = {}         # media id -> (bytes, content type)
        self.fail_interactive = False
        self.uploads = []       # media uploaded to WhatsApp (content types)
        self._msg_ids = itertools.count(1)

        monkeypatch.setattr(requests, "post", self._post)
        monkeypatch.setattr(requests, "get", self._get)
        monkeypatch.setattr(wu, "build", lambda *a, **k: self.google)
        monkeypatch.setattr(wu, "MediaFileUpload", lambda path, mimetype: {"mimetype": mimetype, "size": os.path.getsize(path)})
        monkeypatch.setattr(wu, "load_credentials", lambda: object())
        monkeypatch.setattr(res, "get_gemini_client", lambda: self.gemini)

    # --- fake network
    def _post(self, url, data=None, json=None, headers=None, timeout=None, files=None, **kwargs):
        assert "graph.facebook.com" in url, url
        if url.endswith("/media"):
            self.uploads.append(files["file"][2])
            return FakeResponse(200, {"id": f"upload{len(self.uploads)}"})
        payload = json if json is not None else __import__("json").loads(data)
        if payload.get("status") == "read":
            self.typing.append(payload["message_id"])
            return FakeResponse(200, {"success": True})
        if payload.get("type") == "interactive" and self.fail_interactive:
            return FakeResponse(400, {"error": {"message": "interactive not allowed"}})
        self.sent.append(payload)
        return FakeResponse(200, {"messages": [{"id": "wamid.out"}]})

    def _get(self, url, headers=None, timeout=None, stream=False, **kwargs):
        if url.startswith("https://graph.facebook.com/"):
            media_id = url.rstrip("/").split("/")[-1]
            return FakeResponse(200, {"url": f"https://lookaside.fbsbx.com/media/{media_id}"})
        if url.startswith("https://lookaside.fbsbx.com/media/"):
            content, content_type = self.media[url.split("/")[-1]]
            return FakeResponse(200, content=content, content_type=content_type)
        raise AssertionError(f"unexpected GET {url}")

    # --- helpers
    def webhook(self, message, sign=True, contacts_name="Dana Levi"):
        body = {
            "object": "whatsapp_business_account",
            "entry": [{"id": "1", "changes": [{"field": "messages", "value": {
                "messaging_product": "whatsapp",
                "metadata": {"phone_number_id": TEST_ENV["PHONE_NUMBER_ID"]},
                "contacts": [{"profile": {"name": contacts_name}, "wa_id": USER_WAID}],
                "messages": [message],
            }}]}],
        }
        return self.post_raw(json.dumps(body).encode(), sign=sign)

    def post_raw(self, raw, sign=True):
        headers = {"Content-Type": "application/json"}
        if sign:
            digest = hmac.new(TEST_ENV["APP_SECRET"].encode(), raw, hashlib.sha256).hexdigest()
            headers["X-Hub-Signature-256"] = f"sha256={digest}"
        return self.client.post("/webhook", data=raw, headers=headers)

    def new_id(self):
        return f"wamid.in.{next(self._msg_ids)}"

    def send_text(self, text, **kw):
        return self.webhook({"from": USER_WAID, "id": self.new_id(), "type": "text", "text": {"body": text}}, **kw)

    def press(self, button_id, title="x"):
        return self.webhook({"from": USER_WAID, "id": self.new_id(), "type": "interactive",
                             "interactive": {"type": "button_reply", "button_reply": {"id": button_id, "title": title}}})

    def send_image(self, content, content_type="image/jpeg", caption=None, message_id=None):
        media_id = f"media{len(self.media) + 1}"
        self.media[media_id] = (content, content_type)
        image = {"id": media_id, "mime_type": content_type}
        if caption:
            image["caption"] = caption
        return self.webhook({"from": USER_WAID, "id": message_id or self.new_id(), "type": "image", "image": image})

    def send_document(self, content, filename, mime_type, caption=None, message_id=None):
        media_id = f"media{len(self.media) + 1}"
        self.media[media_id] = (content, mime_type)
        document = {"id": media_id, "filename": filename, "mime_type": mime_type}
        if caption:
            document["caption"] = caption
        return self.webhook({"from": USER_WAID, "id": message_id or self.new_id(), "type": "document", "document": document})

    def to_user(self):
        return [m for m in self.sent if m["to"].lstrip("+") == USER_WAID]

    def to_admin(self):
        return [m for m in self.sent if m["to"] == ADMIN_WAID]

    @staticmethod
    def text_of(payload):
        if payload["type"] == "text":
            return payload["text"]["body"]
        return payload["interactive"]["body"]["text"]

    def last_to_user(self):
        return self.text_of(self.to_user()[-1])

    def pending(self):
        return wu.get_stored_receipt(f"+{USER_WAID}")


@pytest.fixture
def world(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(wu, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(wu, "RECEIPTS_DB", str(data_dir / "receipts_db"))
    monkeypatch.setattr(wu, "MESSAGE_LOG_DB", str(data_dir / "message_log_db"))
    monkeypatch.setattr(wu, "RECEIPT_NUMBER_FILE", str(data_dir / "latest_receipt_number.txt"))
    monkeypatch.setattr(wu, "STATE_LOCK_FILE", str(data_dir / ".state.lock"))
    monkeypatch.delenv("WEBHOOK_SIGNATURE_MODE", raising=False)
    monkeypatch.setenv("EASTER_EGGS", "off")
    app = create_app()
    app.config["TESTING"] = True
    limiter.reset()
    with app.test_client() as client:
        yield World(client, monkeypatch, tmp_path)


def jpeg_bytes(size=(800, 1200), color=(250, 250, 245)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG")
    return buf.getvalue()


def pdf_bytes(width_pts, height_pts, pages=1):
    """A minimal valid PDF with blank pages of the given size."""
    from PIL import Image
    buf = io.BytesIO()
    # 72 dpi so that pixels == points
    images = [Image.new("RGB", (int(width_pts), int(height_pts)), "white") for _ in range(pages)]
    images[0].save(buf, format="PDF", resolution=72.0, save_all=True, append_images=images[1:])
    return buf.getvalue()
