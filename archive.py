#!/usr/bin/env python3
"""
Archive System
Saves all raw content from each digest run to disk for the RAG pipeline.

Directory structure:
  archive/
    2026-04-04/
      digest.html
      emails.json
      substacks.json
      filings.json
      news.json
      market_data.json
      macro_data.json
      memory.json
      pdfs/
        filename.pdf
"""

import base64
import json
import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
ARCHIVE_DIR = SCRIPT_DIR / "archive"


def archive_daily_content(
    date=None,
    digest_html="",
    emails=None,
    substack_articles=None,
    sec_filings=None,
    news_articles=None,
    market_data=None,
    macro_data=None,
    rating_actions=None,
    pacer_entries=None,
    fund_results=None,
    wiltw=None,
):
    """
    Save all raw content from today's digest run to the archive.
    Everything saved here gets indexed into the RAG vector search.
    """
    date = date or datetime.date.today().isoformat()
    day_dir = ARCHIVE_DIR / date
    pdf_dir = day_dir / "pdfs"

    day_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(exist_ok=True)

    print(f"  Archiving content to {day_dir}...")

    # Save digest HTML
    if digest_html:
        (day_dir / "digest.html").write_text(digest_html, encoding="utf-8")

    # Save emails (strip base64 PDF data to save disk — PDFs saved separately)
    emails = emails or []
    emails_clean = []
    pdf_count = 0
    for e in emails:
        email_copy = {k: v for k, v in e.items() if k != "pdfs"}
        email_copy["pdf_filenames"] = []

        for pdf in e.get("pdfs", []):
            filename = pdf.get("filename", "attachment.pdf")
            # Sanitize filename
            safe_name = "".join(c if c.isalnum() or c in ".-_ " else "_" for c in filename)
            pdf_path = pdf_dir / safe_name

            # Decode and save the PDF
            try:
                pdf_bytes = base64.standard_b64decode(pdf["base64"])
                pdf_path.write_bytes(pdf_bytes)
                email_copy["pdf_filenames"].append(safe_name)
                pdf_count += 1
            except Exception as ex:
                print(f"    Failed to save PDF {filename}: {ex}")

        emails_clean.append(email_copy)

    _save_json(day_dir / "emails.json", emails_clean)

    # Save Substack articles
    _save_json(day_dir / "substacks.json", substack_articles or [])

    # Save SEC filings
    _save_json(day_dir / "filings.json", sec_filings or [])

    # Save news articles
    _save_json(day_dir / "news.json", news_articles or [])

    # Save market data
    _save_json(day_dir / "market_data.json", market_data or [])

    # Save macro data
    _save_json(day_dir / "macro_data.json", macro_data or [])

    # Save rating actions
    _save_json(day_dir / "rating_actions.json", rating_actions or [])

    # Save PACER entries
    _save_json(day_dir / "pacer_entries.json", pacer_entries or [])

    # Save 13F fund results
    _save_json(day_dir / "fund_results.json", fund_results or [])

    # Save 13D WILTW summary + PDF
    if wiltw:
        _save_json(day_dir / "wiltw.json", wiltw)

    # Snapshot current memory.json
    memory_file = SCRIPT_DIR / "memory.json"
    if memory_file.exists():
        try:
            memory = json.loads(memory_file.read_text(encoding="utf-8"))
            _save_json(day_dir / "memory.json", memory)
        except Exception:
            pass

    print(f"  Archived: {len(emails_clean)} emails, {pdf_count} PDFs, "
          f"{len(substack_articles or [])} substacks, {len(sec_filings or [])} filings, "
          f"{len(news_articles or [])} news, {len(rating_actions or [])} ratings.")

    return str(day_dir)


def _save_json(path, data):
    """Save data as pretty-printed JSON."""
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def list_archived_dates():
    """Return sorted list of archived date strings."""
    if not ARCHIVE_DIR.exists():
        return []
    dates = []
    for d in ARCHIVE_DIR.iterdir():
        if d.is_dir() and len(d.name) == 10 and d.name[4] == "-":
            dates.append(d.name)
    return sorted(dates)


if __name__ == "__main__":
    dates = list_archived_dates()
    if dates:
        print(f"Archive contains {len(dates)} days: {dates[0]} to {dates[-1]}")
    else:
        print("Archive is empty.")
