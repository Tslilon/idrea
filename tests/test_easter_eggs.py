"""Easter eggs: fun, rare, and never in the way of the receipt flow."""
from datetime import datetime

import pytest

from app.services import easter_eggs as eggs
from conftest import USER_WAID, jpeg_bytes

WAID = f"+{USER_WAID}"
TUESDAY_NOON = datetime(2026, 10, 6, 12, 0)


@pytest.fixture
def eggs_on(world, monkeypatch):
    monkeypatch.setenv("EASTER_EGGS", "on")
    monkeypatch.setattr(eggs, "_gemini_line", lambda prompt: "A witty line from Gemini ✨")
    monkeypatch.setattr(eggs, "now_local", lambda: TUESDAY_NOON)
    monkeypatch.setattr(eggs.random, "random", lambda: 0.99)  # no random surprise unless a test wants one
    return world


def stickers(world):
    return [m for m in world.sent if m["type"] == "sticker"]


def test_milestone_receipt_gets_confetti_sticker(eggs_on):
    w = eggs_on
    w.google.sheet_rows = [[2599]]
    w.send_image(jpeg_bytes())
    w.press("receipt_confirm")
    assert any("Your receipt number is 2600" in w.text_of(m) for m in w.to_user() if m["type"] != "sticker")
    assert len(stickers(w)) == 1 and w.uploads == ["image/webp"]
    assert "Receipt #2600!" in w.last_to_user()


def test_ordinary_receipt_no_egg(eggs_on):
    w = eggs_on
    w.google.sheet_rows = [[2553]]
    w.send_image(jpeg_bytes())
    w.press("receipt_confirm")
    assert stickers(w) == []
    assert "Your receipt number is 2554" in w.last_to_user()


def test_egg_comes_after_the_real_confirmation(eggs_on):
    w = eggs_on
    w.google.sheet_rows = [[99]]
    w.send_image(jpeg_bytes())
    w.press("receipt_confirm")
    texts = [w.text_of(m) for m in w.to_user() if m["type"] != "sticker"]
    assert texts.index(next(t for t in texts if "Your receipt number is 100" in t)) < len(texts) - 1


def test_egg_failure_never_breaks_confirmation(eggs_on, monkeypatch):
    w = eggs_on
    monkeypatch.setattr(eggs, "pick_egg", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    w.send_image(jpeg_bytes())
    w.press("receipt_confirm")
    assert "Your receipt number is" in w.last_to_user()
    assert len(w.google.sheet_rows) == 1


def test_eggs_can_be_switched_off(world):
    world.google.sheet_rows = [[2599]]
    world.send_image(jpeg_bytes())
    world.press("receipt_confirm")
    assert stickers(world) == []
    world.send_text("gracias")
    assert "Please provide the receipt details" in world.last_to_user()


def test_streak_on_fifth_receipt(world, monkeypatch):
    monkeypatch.setattr(eggs.random, "random", lambda: 0.99)
    picks = [eggs.pick_egg(WAID, 10 + i, now=TUESDAY_NOON) for i in range(10)]
    assert picks[4] == "streak" and picks[9] == "streak"
    assert [p for i, p in enumerate(picks) if i not in (4, 9)] == [None] * 8


def test_friday_and_night_owl_once_a_day(world, monkeypatch):
    monkeypatch.setattr(eggs.random, "random", lambda: 0.99)
    friday = datetime(2026, 10, 9, 16, 0)
    assert eggs.pick_egg(WAID, 11, now=friday) == "friday"
    assert eggs.pick_egg(WAID, 12, now=friday) is None
    late = datetime(2026, 10, 9, 23, 30)
    assert eggs.pick_egg(WAID, 13, now=late) == "owl"
    assert eggs.pick_egg(WAID, 14, now=late) is None


def test_random_surprise_has_cooldown(world):
    assert eggs.pick_egg(WAID, 11, now=TUESDAY_NOON, roll=0.0) == "surprise"
    assert eggs.pick_egg(WAID, 12, now=TUESDAY_NOON, roll=0.0) is None


def test_surprise_uses_gemini_line_or_falls_back(eggs_on, monkeypatch):
    w = eggs_on
    monkeypatch.setattr(eggs, "pick_egg", lambda *a, **k: "surprise")
    w.send_image(jpeg_bytes())
    w.press("receipt_confirm")
    assert w.last_to_user() == "A witty line from Gemini ✨"

    monkeypatch.setattr(eggs, "_gemini_line", lambda prompt: (_ for _ in ()).throw(TimeoutError()))
    w.send_image(jpeg_bytes())
    w.press("receipt_confirm")
    assert w.last_to_user() in eggs.SURPRISE_LINES


@pytest.mark.parametrize("word", ["gracias", "Thank you", "  THANKS  "])
def test_thanks(eggs_on, word):
    eggs_on.send_text(word)
    assert "Dana" in eggs_on.last_to_user() or "De nada" in eggs_on.last_to_user()


def test_joke_and_coffee(eggs_on):
    eggs_on.send_text("chiste")
    assert eggs_on.last_to_user() == "A witty line from Gemini ✨"
    eggs_on.send_text("café")
    assert len(stickers(eggs_on)) == 1 and "☕" in eggs_on.last_to_user()


def test_keywords_ignored_while_receipt_pending(eggs_on):
    eggs_on.send_image(jpeg_bytes())
    eggs_on.send_text("thanks")
    assert "waiting for confirmation" in eggs_on.last_to_user()


def test_clean_line():
    assert eggs.clean_line('"Nice one!"\nsecond line') == "Nice one!"
    assert eggs.clean_line("x" * 300) is None
    assert eggs.clean_line("") is None


def test_all_stickers_fit_whatsapp_limits():
    from io import BytesIO
    from PIL import Image
    for args in [("#2600", "RECEIPTS!", "party", "confetti"), ("#3000", "WOW!", "party", "confetti", True),
                 ("WEEKEND", "LOADING", "party", "progress"), ("NIGHT", "OWL", "night", "stars"),
                 ("EARLY", "BIRD", "sunrise", "sunrise"), ("COFFEE", "BREAK", "coffee")]:
        data = eggs.render_sticker(*args)
        img = Image.open(BytesIO(data))
        assert img.size == (512, 512) and img.format == "WEBP" and img.n_frames > 1
        assert len(data) < 500 * 1024


def test_personal_lines_match_team_names():
    assert eggs.personal_lines("Andrea") == eggs.PERSONAL_LINES["andrea"]
    assert eggs.personal_lines("María") == eggs.PERSONAL_LINES["maria"]
    assert eggs.personal_lines("Benjamín") == eggs.PERSONAL_LINES["benjamin"]
    assert eggs.personal_lines("Kalo/Juan") == eggs.PERSONAL_LINES["kalo"]
    assert eggs.personal_lines("Someone") is None
    assert all(len(line) <= 160 for lines in eggs.PERSONAL_LINES.values() for line in lines)
