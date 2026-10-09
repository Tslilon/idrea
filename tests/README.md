# Tests

```bash
pip install -r requirements.txt pytest
python -m pytest tests -q                  # offline: fast, no network, no credentials
IDREA_LIVE=1 python -m pytest tests/live   # real Gemini calls (needs GEMINI_API_KEY in .env)
```

- `test_formatting.py`: characterization tests. They pin down the WhatsApp text and the
  sheet columns as they were before the October 2026 changes. If one fails, user-visible
  behaviour changed.
- `test_webhook_e2e.py`: signed webhook requests go through the real Flask app. WhatsApp,
  Drive, Sheets and Gemini are faked at the network edge (see `conftest.py`).
- `test_easter_eggs.py`: the surprises, plus checks that they never get in the way.
- `live/`: real Gemini calls on the example receipts.

To test inside the production image (same Python and system packages as production):

```bash
docker build --platform linux/amd64 -t idrea:test .
docker run --rm --platform linux/amd64 -v "$PWD/tests:/app/tests" -v "$PWD/example.pdf:/app/example.pdf" \
  -v "$PWD/example_receipt.jpg:/app/example_receipt.jpg" idrea:test sh -c "pip install -q pytest && python -m pytest tests -q"
```

To compare Gemini models on real receipts (read-only), see `scripts/eval_gemini_models.py`.
