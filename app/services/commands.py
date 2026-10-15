"""
Typed commands for iDrea: help, links, sheet, folder, status.

A leading "/" is optional ("/help", "help" and "/ help" all work). Everything
here is read-only, so it also works while a receipt is waiting for confirmation.
"""
import logging
import os

RECENT_COUNT = 5
DRIVE_LOOKBACK = 40  # newest Drive files to scan; some may be unconfirmed or cancelled

COMMANDS = {
    "help": "help", "menu": "help", "?": "help", "ayuda": "help",
    "links": "links", "link": "links", "enlaces": "links",
    "sheet": "sheet", "sheets": "sheet", "spreadsheet": "sheet",
    "folder": "folder", "drive": "folder", "carpeta": "folder",
    "status": "status", "pending": "status",
}

HELP_TEXT = (
    "Hi {name}! Here's what I can do 🤖\n\n"
    "🧾 *Send a receipt* - a photo or PDF, and I'll read it for you.\n"
    "✍️ *Type it yourself* - send any text and I'll reply with a form to fill in.\n\n"
    "When a receipt is waiting, reply *confirm*, *edit* or *cancel* (or tap the buttons).\n\n"
    "*Commands* (the / is optional):\n"
    "• *help* - this message\n"
    "• *links* - the sheet, the folder and the {count} latest receipts\n"
    "• *sheet* - link to the spreadsheet\n"
    "• *folder* - link to the Drive folder\n"
    "• *status* - is a receipt of yours waiting for confirmation?"
)


def parse(text):
    """Return the command name for a message, or None. Whole-message match only."""
    cleaned = " ".join((text or "").strip().lstrip("/").split()).lower()
    return COMMANDS.get(cleaned)


def sheet_url():
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit" if sheet_id else None


def folder_url():
    folder_id = os.getenv("GOOGLE_FOLDER_ID")
    return f"https://drive.google.com/drive/folders/{folder_id}" if folder_id else None


def recent_receipts(creds, limit=RECENT_COUNT):
    """Newest saved receipts as [(number, drive_link)]. Raises on API errors."""
    build = _whatsapp().build
    drive = build("drive", "v3", credentials=creds)
    files = drive.files().list(
        q=f"'{os.getenv('GOOGLE_FOLDER_ID')}' in parents and trashed = false",
        orderBy="createdTime desc",
        pageSize=DRIVE_LOOKBACK,
        fields="files(id,name)",
    ).execute().get("files", [])

    # Files are uploaded before the user confirms, so keep only receipts that reached the sheet.
    sheets = build("sheets", "v4", credentials=creds)
    rows = sheets.spreadsheets().values().get(
        spreadsheetId=os.getenv("GOOGLE_SHEET_ID"), range="iDrea!A2:A").execute().get("values", [])
    saved = {row[0].strip() for row in rows if row}

    found = []
    for f in files:
        number = os.path.splitext(f.get("name", ""))[0]
        if number in saved:
            found.append((number, f"https://drive.google.com/file/d/{f['id']}/view"))
        if len(found) == limit:
            break
    return found


def handle(command, text, name, creds, sender_waid, stored_receipt):
    """Reply to a command. Returns True when handled."""
    wu = _whatsapp()
    first_name = wu.get_first_name(name) or "friend"

    def reply(message):
        wu.send_message(wu.get_text_message_input(sender_waid, message))

    if command == "help":
        reply(HELP_TEXT.format(name=first_name, count=RECENT_COUNT))
    elif command == "sheet":
        reply(f"📊 Spreadsheet:\n{sheet_url()}" if sheet_url() else "I don't have a spreadsheet configured.")
    elif command == "folder":
        reply(f"📁 Receipts folder:\n{folder_url()}" if folder_url() else "I don't have a folder configured.")
    elif command == "status":
        if stored_receipt:
            number = stored_receipt.get("receipt_number")
            label = f"Receipt #{number}" if number else "A receipt"
            reply(f"{label} is waiting for you, {first_name}. Reply *confirm*, *edit* or *cancel*.")
        else:
            reply(f"Nothing waiting, {first_name}. Send me a receipt whenever you're ready. 🧾")
    elif command == "links":
        parts = []
        if sheet_url():
            parts.append(f"📊 Spreadsheet:\n{sheet_url()}")
        if folder_url():
            parts.append(f"📁 Folder:\n{folder_url()}")
        try:
            recent = recent_receipts(creds)
            if recent:
                lines = "\n".join(f"#{number}: {link}" for number, link in recent)
                parts.append(f"🧾 Latest receipts:\n{lines}")
            else:
                parts.append("🧾 No saved receipts found yet.")
        except Exception as e:
            logging.error(f"Could not list recent receipts: {e}")
            parts.append("🧾 I couldn't fetch the latest receipts just now, try again in a minute.")
        reply("\n\n".join(parts))
    else:
        return False
    return True


def _whatsapp():
    from app.utils import whatsapp_utils
    return whatsapp_utils
