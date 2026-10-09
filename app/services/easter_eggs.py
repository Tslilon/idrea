"""
Occasional surprises for the team when they talk to iDrea.

Everything here is best effort: it runs after the real reply has been sent,
every failure is swallowed, and EASTER_EGGS=off turns it all off.

What there is to discover:
  * Milestones   - receipt numbers ending in 00 get a confetti sticker (000: a bigger party)
  * Streaks      - the 5th and 10th receipt someone files in a day
  * Friday       - first receipt after 15:00 on a Friday: "weekend loading" sticker
  * Night owl    - receipts filed between 23:00 and 05:00
  * Early bird   - receipts filed between 05:00 and 07:30
  * Surprise     - now and then, a one-line reaction to the receipt (written by Gemini)
  * Words        - thanks / gracias, joke / chiste, coffee / café, who are you,
                   good morning / buenos días, good night / buenas noches,
                   i love you / te quiero, 42, idrea, high five
"""
import io
import logging
import math
import os
import random
import shelve
import time
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont

try:
    from zoneinfo import ZoneInfo
    TEAM_TZ = ZoneInfo("Europe/Madrid")
except Exception:  # tzdata missing: fall back to the server clock
    TEAM_TZ = None

SURPRISE_CHANCE = float(os.getenv("EASTER_EGG_CHANCE", "0.2"))
SURPRISE_COOLDOWN_SECONDS = 20 * 3600
QUIP_MODEL = os.getenv("EASTER_EGG_MODEL") or "gemini-3.5-flash-lite"
QUIP_TIMEOUT_MS = 10000

PALETTES = {
    "party": [(255, 89, 94), (255, 202, 58), (138, 201, 38), (25, 130, 196), (106, 76, 147)],
    "night": [(255, 236, 153), (186, 200, 255), (255, 255, 255)],
    "sunrise": [(255, 183, 77), (255, 112, 67), (255, 224, 130)],
    "coffee": [(255, 255, 255), (230, 230, 230)],
}

# Extra lines for the people who use iDrea (matched on first name, accents ignored);
# anyone else gets the general ones.
PERSONAL_LINES = {
    "andrea": [
        "We hope that some day bots and AI will be as efficient as Andrea. 💙",
        "Andrea, thank you for everything you do - this team is lucky to have you. ❤️",
        "Andrea, you are the heart of this operation. With love from all of us. 💙",
    ],
    "pablo": [
        "Pablo strikes again. The receipts never stood a chance. 🎯",
        "Filed by Pablo - neat, fast, and right on time.",
    ],
    "sebastian": [
        "Sebastian, smooth as ever. Receipt filed. 😎",
        "Another tidy one from Sebastian. 👌",
    ],
    "juan": [
        "Juan, you make this look easy. ✅",
        "Filed! Thanks, Juan - the spreadsheet salutes you. 🫡",
    ],
    "kalo": [
        "Kalo, you make this look easy. ✅",
    ],
    "maria": [
        "María, thank you - beautifully filed. 🌸",
        "Another one from María, right where it belongs. 📁",
    ],
    "barak": [
        "Barak, receipt received loud and clear. 📡",
        "Filed and accounted for - thanks, Barak! 🙌",
    ],
    "amir": [
        "Amir, rare and valuable - just like this receipt. 💎",
    ],
    "benjamin": [
        "Benjamín, receipt safely filed. Gracias! 🙏",
    ],
    "tslil": [
        "The creator files a receipt. iDrea is honoured. 🤖✨",
    ],
}


def personal_lines(first_name):
    """Lines for a known person; handles accents and profile names like "Kalo/Juan"."""
    import unicodedata
    plain = unicodedata.normalize("NFKD", first_name or "").encode("ascii", "ignore").decode().lower()
    for part in plain.replace("/", " ").split():
        if part in PERSONAL_LINES:
            return PERSONAL_LINES[part]
    return None


SURPRISE_LINES = [
    "Receipt filed. Somewhere, an accountant just smiled. 😊",
    "That's one less piece of paper living in a pocket. 🧾",
    "Filed faster than you can say 'factura'. ⚡",
    "Your spreadsheet thanks you. It doesn't say much, but it means it.",
    "Neat, tidy, filed. Chef's kiss. 👌",
    "Another receipt safely home. 🏡",
]

KEYWORD_REPLIES = {
    "thanks": [
        "Always a pleasure, {name}! 💙",
        "Anytime, {name}. Receipts are my love language. 🧾",
        "De nada, {name}! 🙌",
    ],
    "who": [
        "I'm iDrea 🤖 - I read receipts so you don't have to. Send me a photo or a PDF and I'll do the rest.",
    ],
    "morning": [
        "Good morning, {name}! ☀️ Ready when your receipts are.",
        "¡Buenos días, {name}! ☕ Let's file some receipts.",
    ],
    "night": [
        "Good night, {name}! 🌙 The receipts will keep till tomorrow.",
        "¡Buenas noches, {name}! 😴",
    ],
    "love": [
        "Aww, {name}. I love you too - in a strictly professional, receipt-processing way. 💙",
    ],
    "42": [
        "The answer to life, the universe and everything. Also a perfectly reasonable IVA amount. 🌌",
    ],
    "idrea": [
        "That's me! 👋 You rang, {name}?",
    ],
    "highfive": [
        "✋ Up high, {name}!",
    ],
}

JOKES = [
    "Why did the receipt go to therapy? It had too many issues. 🧾",
    "I tried to write a joke about IVA, but it was 21% too long.",
    "Why are accountants good at hide and seek? They always find the missing receipt. 🔎",
    "What's a receipt's favourite music? Anything with a good balance. 🎵",
    "I asked the spreadsheet for a date. It gave me DD/MM/YYYY.",
]

KEYWORDS = {
    "thanks": "thanks", "thank you": "thanks", "thank you!": "thanks", "thanks!": "thanks", "thx": "thanks",
    "gracias": "thanks", "gracias!": "thanks", "muchas gracias": "thanks", "merci": "thanks", "toda": "thanks",
    "joke": "joke", "tell me a joke": "joke", "chiste": "joke", "cuéntame un chiste": "joke",
    "coffee": "coffee", "café": "coffee", "cafe": "coffee", "☕": "coffee",
    "who are you": "who", "who are you?": "who", "quién eres": "who", "quien eres": "who", "¿quién eres?": "who",
    "good morning": "morning", "buenos días": "morning", "buenos dias": "morning", "buen día": "morning",
    "good night": "night", "buenas noches": "night",
    "i love you": "love", "te quiero": "love", "❤️": "love",
    "42": "42",
    "idrea": "idrea", "hi idrea": "idrea", "hola idrea": "idrea", "hey idrea": "idrea",
    "high five": "highfive", "✋": "highfive",
}


def enabled():
    return os.getenv("EASTER_EGGS", "on").lower() not in ("off", "0", "false", "no")


def now_local():
    return datetime.now(TEAM_TZ) if TEAM_TZ else datetime.now()


# ------------------------------------------------------------------ entry points

def handle_keyword(text, sender_waid, name):
    """Reply to a hidden keyword. Returns True if the message was handled."""
    if not enabled():
        return False
    try:
        key = KEYWORDS.get(" ".join(text.lower().strip().split()))
        if not key:
            return False
        wu = _whatsapp()
        first_name = wu.get_first_name(name) or "friend"
        if key == "joke":
            wu.send_message(wu.get_text_message_input(sender_waid, generate_joke() or random.choice(JOKES)))
        elif key == "coffee":
            send_sticker(sender_waid, render_sticker("COFFEE", "BREAK", "coffee"))
            wu.send_message(wu.get_text_message_input(sender_waid, f"☕ Here you go, {first_name}. Receipts can wait five minutes."))
        else:
            wu.send_message(wu.get_text_message_input(sender_waid, random.choice(KEYWORD_REPLIES[key]).format(name=first_name)))
        return True
    except Exception as e:
        logging.warning(f"Easter egg keyword failed: {e}")
        return False


def after_receipt_saved(sender_waid, name, receipt_details, receipt_number):
    """Maybe celebrate a confirmed receipt. Never raises."""
    if not enabled():
        return
    try:
        egg = pick_egg(sender_waid, receipt_number)
        if egg:
            deliver(egg, sender_waid, name, receipt_details or {}, receipt_number)
    except Exception as e:
        logging.warning(f"Easter egg failed: {e}")


# ------------------------------------------------------------------ choosing

def pick_egg(sender_waid, receipt_number, now=None, roll=None):
    """Decide which surprise (if any) fits this receipt. At most one per receipt."""
    now = now or now_local()
    today = now.strftime("%Y-%m-%d")
    roll = random.random() if roll is None else roll
    wu = _whatsapp()
    with wu.state_lock(), shelve.open(os.path.join(wu.DATA_DIR, "easter_eggs_db")) as db:
        state = db.get(sender_waid, {})
        if state.get("day") != today:
            state = {"day": today, "count": 0, "seen": [], "last_surprise": state.get("last_surprise", 0)}
        state["count"] += 1

        egg = None
        number = _as_int(receipt_number)
        if number and number % 1000 == 0:
            egg = "milestone_big"
        elif number and number % 100 == 0:
            egg = "milestone"
        elif state["count"] in (5, 10):
            egg = "streak"
        elif now.weekday() == 4 and now.hour >= 15 and "friday" not in state["seen"]:
            egg = "friday"
        elif (now.hour >= 23 or now.hour < 5) and "owl" not in state["seen"]:
            egg = "owl"
        elif 5 <= now.hour < 7 or (now.hour == 7 and now.minute < 30):
            egg = "early" if "early" not in state["seen"] else None
        if egg is None and roll < SURPRISE_CHANCE and time.time() - state.get("last_surprise", 0) > SURPRISE_COOLDOWN_SECONDS:
            egg = "surprise"
            state["last_surprise"] = time.time()

        if egg in ("friday", "owl", "early"):
            state["seen"].append(egg)
        state["streak"] = state["count"]
        db[sender_waid] = state
        return egg


def deliver(egg, sender_waid, name, details, receipt_number):
    wu = _whatsapp()
    first_name = wu.get_first_name(name) or "friend"
    text, sticker = None, None
    if egg == "milestone_big":
        sticker = render_sticker(f"#{receipt_number}", "WOW!", "party", effect="confetti", big=True)
        text = f"🎊 {first_name}, you just filed receipt #{receipt_number}! That's a milestone worth celebrating."
    elif egg == "milestone":
        sticker = render_sticker(f"#{receipt_number}", "RECEIPTS!", "party", effect="confetti")
        text = f"🎉 Receipt #{receipt_number}! Nice round number, {first_name}."
    elif egg == "streak":
        count = _streak_count(sender_waid)
        sticker = render_sticker(f"x{count}", "TODAY", "party", effect="confetti")
        text = f"🔥 {count} receipts today, {first_name}. You're on a roll!"
    elif egg == "friday":
        sticker = render_sticker("WEEKEND", "LOADING", "party", effect="progress")
        text = f"Happy Friday, {first_name}! 🎶"
    elif egg == "owl":
        sticker = render_sticker("NIGHT", "OWL", "night", effect="stars")
        text = f"🦉 Filing receipts at this hour, {first_name}? Get some sleep!"
    elif egg == "early":
        sticker = render_sticker("EARLY", "BIRD", "sunrise", effect="sunrise")
        text = f"🐦 Up early, {first_name}! Impressive."
    elif egg == "surprise":
        personal = personal_lines(first_name)
        if personal and random.random() < 0.5:
            text = random.choice(personal)
        else:
            text = generate_quip(first_name, details) or random.choice(SURPRISE_LINES)
    if sticker:
        send_sticker(sender_waid, sticker)
    if text:
        wu.send_message(wu.get_text_message_input(sender_waid, text))


def _streak_count(sender_waid):
    wu = _whatsapp()
    with wu.state_lock(), shelve.open(os.path.join(wu.DATA_DIR, "easter_eggs_db")) as db:
        return db.get(sender_waid, {}).get("count", 5)


# ------------------------------------------------------------------ Gemini one-liners

def _gemini_line(prompt):
    from google import genai
    from google.genai import types
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=QUIP_TIMEOUT_MS))
    response = client.models.generate_content(model=QUIP_MODEL, contents=prompt)
    return clean_line(getattr(response, "text", None))


def clean_line(text, max_len=160):
    if not text:
        return None
    line = text.strip().splitlines()[0].strip().strip('"“”\'').strip()
    if not line or len(line) > max_len:
        return None
    return line


def generate_quip(first_name, details):
    try:
        prompt = (
            "You are iDrea, a cheerful WhatsApp bot that files expense receipts for a small, friendly "
            "real-estate team in Spain. Write ONE short, warm, witty line (max 120 characters, at most one emoji) "
            f"reacting to {first_name} filing this expense: what='{details.get('what', '')}', "
            f"store='{details.get('store_name', '')}'.\n"
            "Rules: kind and inclusive; never comment on how much was spent or on the person's habits, "
            "appearance, health, politics, religion or alcohol; no hashtags; no quotes. Reply with the line only."
        )
        return _gemini_line(prompt)
    except Exception as e:
        logging.info(f"Quip generation failed, using a canned line: {e}")
        return None


def generate_joke():
    try:
        return _gemini_line(
            "Tell one short, clean, office-friendly joke about receipts, expenses, spreadsheets or accounting "
            "(max 140 characters, at most one emoji). Reply with the joke only, on one line."
        )
    except Exception as e:
        logging.info(f"Joke generation failed, using a canned one: {e}")
        return None


# ------------------------------------------------------------------ stickers

def _font(size):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _fit_font(draw, text, max_width, start):
    size = start
    while size > 20:
        font = _font(size)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size -= 6
    return _font(size)


def render_sticker(title, subtitle, palette="party", effect=None, big=False, frames=16):
    """Animated 512x512 WebP sticker: a round badge with two lines of text and a little animation."""
    colors = PALETTES[palette]
    rng = random.Random(f"{title}{subtitle}")
    particles = [(rng.uniform(0, 512), rng.uniform(-512, 0), rng.uniform(6, 14), rng.choice(PALETTES["party"]), rng.uniform(0, math.tau))
                 for _ in range(60 if big else 36)]
    badge = {"party": (33, 37, 41), "night": (25, 32, 72), "sunrise": (255, 245, 230), "coffee": (111, 78, 55)}[palette]
    ink = (33, 37, 41) if palette == "sunrise" else (255, 255, 255)
    out = []
    for i in range(frames):
        t = i / frames
        img = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        pulse = 1 + 0.04 * math.sin(t * math.tau)
        r = int(200 * pulse)
        d.ellipse((256 - r, 256 - r, 256 + r, 256 + r), fill=badge + (255,), outline=colors[0] + (255,), width=10)

        if effect == "confetti":
            for x, y, s, c, phase in particles:
                py = (y + t * 1024) % 600 - 40
                px = x + 18 * math.sin(phase + t * math.tau)
                d.rectangle((px, py, px + s, py + s * 0.6), fill=c + (255,))
        elif effect == "stars":
            for k, (x, y, s, _, phase) in enumerate(particles[:20]):
                a = int(255 * (0.5 + 0.5 * math.sin(phase + t * math.tau)))
                d.text((x, (y % 512)), "*", font=_font(int(s * 3)), fill=colors[k % len(colors)] + (a,))
        elif effect == "sunrise":
            rise = int(60 * math.sin(t * math.pi))
            d.pieslice((186, 380 - rise, 326, 520 - rise), 180, 360, fill=colors[0] + (255,))
        elif effect == "progress":
            filled = int(260 * ((i + 1) / frames))
            d.rounded_rectangle((126, 330, 386, 362), radius=14, outline=ink + (255,), width=4)
            d.rounded_rectangle((130, 334, 130 + filled, 358), radius=11, fill=colors[2] + (255,))
        if palette == "coffee":
            for k in range(3):
                x = 220 + k * 36
                for j in range(6):
                    y = 170 - j * 14 - (t * 28) % 14
                    d.ellipse((x + 6 * math.sin(j + t * math.tau + k), y, x + 10 + 6 * math.sin(j + t * math.tau + k), y + 10), fill=(255, 255, 255, 200))

        title_font = _fit_font(d, title, 330, 120 if big else 104)
        d.text((256, 220), title, font=title_font, fill=ink + (255,), anchor="mm")
        d.text((256, 300 if effect != "progress" else 290), subtitle, font=_fit_font(d, subtitle, 300, 54), fill=colors[1] + (255,), anchor="mm")
        out.append(img)

    buf = io.BytesIO()
    out[0].save(buf, format="WEBP", save_all=True, append_images=out[1:], duration=90, loop=0, quality=70, method=4)
    return buf.getvalue()


def send_sticker(recipient, webp_bytes):
    """Upload a sticker to WhatsApp and send it. Returns True on success."""
    import requests
    base = f"https://graph.facebook.com/{os.getenv('VERSION')}/{os.getenv('PHONE_NUMBER_ID')}"
    headers = {"Authorization": f"Bearer {os.getenv('ACCESS_TOKEN')}"}
    try:
        upload = requests.post(
            f"{base}/media",
            headers=headers,
            data={"messaging_product": "whatsapp", "type": "image/webp"},
            files={"file": ("sticker.webp", webp_bytes, "image/webp")},
            timeout=15,
        )
        media_id = upload.json().get("id") if upload.status_code == 200 else None
        if not media_id:
            logging.info(f"Sticker upload failed: {upload.status_code} {upload.text[:200]}")
            return False
        sent = requests.post(
            f"{base}/messages",
            headers=headers,
            json={"messaging_product": "whatsapp", "to": recipient, "type": "sticker", "sticker": {"id": media_id}},
            timeout=10,
        )
        return sent.status_code == 200
    except Exception as e:
        logging.info(f"Sticker not sent: {e}")
        return False


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _whatsapp():
    from app.utils import whatsapp_utils
    return whatsapp_utils
