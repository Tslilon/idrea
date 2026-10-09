#!/usr/bin/env python3
"""
Compare Gemini models on real receipts (read-only).

Ground truth is what the team confirmed into the iDrea sheet; the receipt file is
the Drive upload named after the receipt number. Note the bias: people often accept
what the current model extracted, so agreement favours the current model.

    python scripts/eval_gemini_models.py --models gemini-3-flash-preview gemini-3.5-flash --limit 40
"""
import argparse
import io
import json
import os
import random
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))
from google.oauth2 import service_account  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402
from googleapiclient.http import MediaIoBaseDownload  # noqa: E402
from app.services import receipt_extraction_service as res  # noqa: E402

FIELDS = ["total_amount", "iva", "date", "supplier_id", "invoice_number", "company"]
SHEET_COLUMNS = {"date": 1, "total_amount": 4, "iva": 5, "company": 11, "invoice_number": 12, "supplier_id": 13}


def amount(v):
    v = str(v or "").replace("€", "").strip()
    if not v:
        return None
    if "," in v and "." in v:
        v = v.replace(".", "").replace(",", ".") if v.rfind(",") > v.rfind(".") else v.replace(",", "")
    else:
        v = v.replace(",", ".")
    try:
        return round(float(re.sub(r"[^\d.\-]", "", v)), 2)
    except ValueError:
        return None


def day(v):
    v = str(v or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%Y %H:%M:%S", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            pass
    return None


def text(v):
    return re.sub(r"[^0-9a-z]", "", str(v or "").lower()) or None


NORMALIZE = {"total_amount": amount, "iva": amount, "date": day, "supplier_id": text, "invoice_number": text, "company": text}


def load_cases(limit, cache_dir):
    sa = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    sa = sa if os.path.isabs(sa) else os.path.join(ROOT, sa)
    creds = service_account.Credentials.from_service_account_file(
        sa, scopes=["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/spreadsheets.readonly"])
    sheets = build("sheets", "v4", credentials=creds)
    drive = build("drive", "v3", credentials=creds)
    rows = sheets.spreadsheets().values().get(spreadsheetId=os.getenv("GOOGLE_SHEET_ID"), range="iDrea!A2:N").execute().get("values", [])
    rows = [r + [""] * (14 - len(r)) for r in rows if r and str(r[0]).isdigit()][-400:]

    files, token = defaultdict(list), None
    while True:
        page = drive.files().list(q=f"'{os.getenv('GOOGLE_FOLDER_ID')}' in parents and trashed = false",
                                  fields="nextPageToken, files(id,name,mimeType)", pageSize=1000, pageToken=token,
                                  orderBy="createdTime desc").execute()
        for f in page["files"]:
            files[os.path.splitext(f["name"])[0]].append(f)
        token = page.get("nextPageToken")
        if not token or len(files) > 3000:
            break

    cases = []
    for r in rows:
        match = files.get(str(r[0]), [])
        if len(match) != 1 or not r[4]:
            continue
        f = match[0]
        kind = "pdf" if f["mimeType"] == "application/pdf" else "image" if f["mimeType"].startswith("image/") else None
        if kind:
            cases.append({"number": r[0], "file": f, "kind": kind, "truth": {k: r[c] for k, c in SHEET_COLUMNS.items()}})
    random.Random(7).shuffle(cases)
    cases = cases[:limit]

    os.makedirs(cache_dir, exist_ok=True)
    for c in cases:
        path = os.path.join(cache_dir, c["file"]["id"])
        if not os.path.exists(path):
            buf = io.BytesIO()
            dl = MediaIoBaseDownload(buf, drive.files().get_media(fileId=c["file"]["id"]))
            done = False
            while not done:
                _, done = dl.next_chunk()
            with open(path, "wb") as fh:
                fh.write(buf.getvalue())
        with open(path, "rb") as fh:
            c["content"] = fh.read()
    return cases


def run(model, pages, case):
    res.GEMINI_MODEL, res.PDF_MAX_PAGES = model, pages
    start = time.time()
    details, error = res.extract_receipt_details(case["content"], case["kind"])
    return details or {}, error, time.time() - start


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["gemini-3-flash-preview"])
    ap.add_argument("--pages", type=int, nargs="+", default=[1])
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--cache", default=os.path.join(ROOT, ".eval_cache"))
    ap.add_argument("--json", help="write per-case results here")
    args = ap.parse_args()

    cases = load_cases(args.limit, args.cache)
    print(f"{len(cases)} receipts ({sum(c['kind'] == 'pdf' for c in cases)} PDF, {sum(c['kind'] == 'image' for c in cases)} images)\n")
    results = {}
    for model in args.models:
        for pages in args.pages:
            # One model at a time (GEMINI_MODEL is a module global), cases in parallel
            res.GEMINI_MODEL, res.PDF_MAX_PAGES = model, pages
            with ThreadPoolExecutor(6) as pool:
                outs = list(pool.map(lambda c: run(model, pages, c), cases))
            label = f"{model} (pdf pages={pages})"
            results[label] = outs
            score, errors = defaultdict(int), 0
            for c, (details, error, _) in zip(cases, outs):
                errors += bool(error)
                for k in FIELDS:
                    got = details.get("date" if k == "date" else k)
                    if NORMALIZE[k](got) == NORMALIZE[k](c["truth"][k]):
                        score[k] += 1
            secs = sorted(o[2] for o in outs)
            n = len(cases)
            print(f"{label}\n  " + "  ".join(f"{k}={score[k] / n:.0%}" for k in FIELDS)
                  + f"\n  overall={sum(score.values()) / (n * len(FIELDS)):.1%}  errors={errors}  median={secs[n // 2]:.1f}s  p90={secs[int(n * .9)]:.1f}s\n")
    if args.json:
        with open(args.json, "w") as fh:
            json.dump({label: [{"number": c["number"], "truth": c["truth"], "got": o[0], "error": o[1], "secs": o[2]}
                               for c, o in zip(cases, outs)] for label, outs in results.items()}, fh, indent=1, ensure_ascii=False, default=str)


if __name__ == "__main__":
    main()
