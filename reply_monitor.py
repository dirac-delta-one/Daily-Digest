#!/usr/bin/env python3
"""
Email Reply Interface
Polls Gmail for replies to digest emails, answers questions using
RAG over the archive, and replies in the same email thread.

Run as a background process or via cron every 5 minutes.

Usage:
    python reply_monitor.py          # run continuously (poll every 5 min)
    python reply_monitor.py --once   # process one batch and exit (for testing)
"""

import base64
import re
import sys
import time
import datetime
from email.mime.text import MIMEText
from pathlib import Path

import anthropic

# Reuse Gmail auth from digest.py
from digest import get_gmail_service, DIGEST_RECIPIENTS

from search import search
from config import OPUS_MODEL, SONNET_MODEL
from claude_utils import parse_json_response, json_schema_output, wrapped_array_schema
import cost
from html_utils import extract_gmail_body, strip_html

ARCHIVE_DIR = Path(__file__).parent / "archive"

# --- Configuration ---
POLL_INTERVAL_SECONDS = 300    # check every 5 minutes
SEARCH_TOP_K = 20              # retrieve top 20 chunks for context
REPLY_MODEL = OPUS_MODEL
MAX_CONTEXT_CHARS = 80000      # cap context to control Opus costs
MAX_REPLIES_PER_HOUR = 10      # rate limit

DIGEST_SUBJECT_PREFIX = "\U0001f4ec Daily Inbox Digest"

# Queries processed this hour (for rate limiting)
_replies_this_hour = []


# ======================================================================
# GMAIL HELPERS
# ======================================================================

def _extract_question(body):
    """
    Extract the actual question from a reply email body.
    Strips quoted text, signatures, and email headers.
    """
    lines = body.split("\n")
    question_lines = []

    for line in lines:
        stripped = line.strip()

        # Stop at quoted text indicators
        if stripped.startswith(">"):
            break
        if stripped.startswith("On ") and "wrote:" in stripped:
            break
        if stripped.startswith("------"):
            break
        if stripped.startswith("From:") and "Digest" in stripped:
            break

        # Skip empty leading lines
        if not question_lines and not stripped:
            continue

        # Skip common signatures
        if stripped in ("--", "Sent from my iPhone", "Sent from my iPad"):
            break
        if stripped.startswith("Sent from "):
            break

        question_lines.append(stripped)

    question = "\n".join(question_lines).strip()

    # Remove trailing empty lines
    while question.endswith("\n"):
        question = question[:-1].strip()

    return question


def _extract_digest_date(subject, thread_id, service):
    """
    Extract the date of the original digest from the email thread.
    Parses the subject line date, or falls back to the original message's date.

    Returns ISO date string "YYYY-MM-DD" or None.
    """
    # Try parsing date from subject: "Re: ... Daily Inbox Digest — Friday, April 4"
    # Match patterns like "April 4", "March 28", etc.
    m = re.search(r'(\w+)\s+(\d{1,2})$', subject.strip())
    if m:
        month_str, day_str = m.group(1), m.group(2)
        try:
            # Parse month name + day, assume current year
            parsed = datetime.datetime.strptime(f"{month_str} {day_str}", "%B %d")
            year = datetime.date.today().year
            # Handle year boundary (e.g. asking about December digest in January)
            candidate = datetime.date(year, parsed.month, parsed.day)
            if candidate > datetime.date.today():
                candidate = datetime.date(year - 1, parsed.month, parsed.day)
            return candidate.isoformat()
        except ValueError:
            pass

    # Fallback: look at the first message in the thread (the original digest)
    try:
        thread = service.users().threads().get(
            userId="me", id=thread_id, format="metadata",
            metadataHeaders=["Date"],
        ).execute()
        first_msg = thread["messages"][0]
        headers = {h["name"]: h["value"] for h in first_msg["payload"]["headers"]}
        date_str = headers.get("Date", "")
        if date_str:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(date_str)
            return dt.date().isoformat()
    except Exception:
        pass

    return None


def _load_digest_for_date(date_str):
    """Load the archived digest HTML for a given date, if available."""
    if not date_str:
        return None
    digest_file = ARCHIVE_DIR / date_str / "digest.html"
    if digest_file.exists():
        try:
            return digest_file.read_text(encoding="utf-8")
        except Exception:
            pass
    return None


def check_for_replies(service):
    """
    Find unprocessed replies to digest emails.

    Returns list of (message_id, thread_id, subject, question_text, digest_date).
    """
    # Search for replies to digest threads from the user
    query = (
        f'subject:"Re: {DIGEST_SUBJECT_PREFIX}" '
        f'is:unread '
        f'newer_than:1d '
        f'(from:jtramontano@acorninv.com OR from:acorn.research.bot@gmail.com '
        f'OR from:acohen@acorninv.com)'
    )

    try:
        results = service.users().messages().list(
            userId="me", q=query, maxResults=10,
        ).execute()
    except Exception as e:
        print(f"  Gmail search error: {e}")
        return []

    messages = results.get("messages", [])
    if not messages:
        return []

    replies = []
    for msg_meta in messages:
        try:
            msg = service.users().messages().get(
                userId="me", id=msg_meta["id"], format="full",
            ).execute()

            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            subject = headers.get("Subject", "")
            thread_id = msg.get("threadId", "")

            # Extract the question from the reply body
            body = extract_gmail_body(msg["payload"])
            question = _extract_question(body)

            if not question or len(question) < 3:
                # Not a real question — skip
                # Mark as read so we don't re-process
                _mark_as_read(service, msg_meta["id"])
                continue

            # Skip non-questions (simple acknowledgments)
            lower = question.lower().strip()
            if lower in ("thanks", "thank you", "ok", "got it", "ty", "thx", "👍"):
                _mark_as_read(service, msg_meta["id"])
                continue

            # Figure out which digest this reply is for
            digest_date = _extract_digest_date(subject, thread_id, service)

            # Get the RFC Message-ID for proper threading in Outlook/other clients
            rfc_message_id = headers.get("Message-ID", headers.get("Message-Id", ""))

            replies.append((msg_meta["id"], thread_id, subject, question, digest_date, rfc_message_id))

        except Exception as e:
            print(f"  Error processing message {msg_meta['id']}: {e}")

    return replies


def _mark_as_read(service, message_id):
    """Mark a message as read by removing the UNREAD label."""
    try:
        service.users().messages().modify(
            userId="me",
            id=message_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()
    except Exception:
        pass


# ======================================================================
# RAG ANSWER GENERATION
# ======================================================================

def _extract_search_queries(reply_text):
    """Use Sonnet to extract the actual questions/requests from a reply email."""
    client = anthropic.Anthropic()

    try:
        response = client.messages.create(
            model=SONNET_MODEL,
            max_tokens=500,
            system=(
                "Extract the questions or information requests from this email reply. "
                "Return a JSON object {\"queries\": [ ... ]} — one search-query string per question. "
                "Rephrase each as a clear search query suitable for searching a research archive. "
                "If there's only one question, return a single-element array. "
                "If the message isn't a question (just a comment/thanks), return {\"queries\": []}. "
                "Output ONLY the JSON object, nothing else."
            ),
            output_config=json_schema_output(wrapped_array_schema("queries", "string")),
            messages=[{"role": "user", "content": reply_text}],
        )

        cost.record("reply query-extract", SONNET_MODEL, response.usage)
        queries = parse_json_response(response.content[0].text)["queries"]
        if isinstance(queries, list) and queries:
            print(f"  Extracted {len(queries)} search queries from reply")
            for q in queries:
                print(f"    -> {q[:80]}")
            return queries

    except Exception as e:
        print(f"  Query extraction failed ({e}) — using raw text")

    # Fallback: use the full reply text as a single query
    return [reply_text[:500]]


def _search_multiple(queries, digest_date=None):
    """Search for multiple queries and merge results, deduped by chunk_id."""
    all_results = []
    seen_ids = set()

    for query in queries:
        # Two-phase search: digest day first, then broaden
        if digest_date:
            day_results = search(query, top_k=SEARCH_TOP_K // 2, date_filter=digest_date)
            for meta, score in day_results:
                cid = meta.get("chunk_id")
                if cid not in seen_ids:
                    seen_ids.add(cid)
                    all_results.append((meta, score))

        broader = search(query, top_k=SEARCH_TOP_K)
        for meta, score in broader:
            cid = meta.get("chunk_id")
            if cid not in seen_ids:
                seen_ids.add(cid)
                all_results.append((meta, score))

    # Sort by score and cap
    all_results.sort(key=lambda x: x[1], reverse=True)
    return all_results[:SEARCH_TOP_K]


def answer_question(question, digest_date=None):
    """
    Parse the full reply for questions, search the archive for each,
    and generate a unified answer using Claude Opus.

    Args:
        question: The user's full reply text (stripped of quoted content).
        digest_date: ISO date string of the digest being replied to.

    Returns:
        HTML string with the answer.
    """
    date_label = f" (replying to {digest_date} digest)" if digest_date else ""
    print(f"  Processing reply{date_label}: {question[:80]}...")

    # Extract individual search queries from the reply
    queries = _extract_search_queries(question)

    if not queries:
        return (
            '<div style="font-family: Georgia, serif; max-width: 680px; margin: 0 auto; '
            'color: #1a1a1a; line-height: 1.6; font-size: 14px;">'
            "<p>I couldn't identify a question in your reply. "
            "Try rephrasing as a specific question about your research archive.</p></div>"
        )

    # Search for all queries, merge and dedupe results
    results = _search_multiple(queries, digest_date=digest_date)

    if not results:
        return (
            '<div style="font-family: Georgia, serif; max-width: 680px; margin: 0 auto; '
            'color: #1a1a1a; line-height: 1.6; font-size: 14px;">'
            "<p>I searched the archive but found no relevant content for your question. "
            "The archive may not have enough history yet, or the topic might not have "
            "appeared in your research sources.</p></div>"
        )

    # Load the original digest as primary context
    digest_context = ""
    if digest_date:
        digest_html = _load_digest_for_date(digest_date)
        if digest_html:
            # Strip HTML for the prompt
            digest_text = strip_html(digest_html)
            # Cap at 20K chars to leave room for RAG chunks
            if len(digest_text) > 20000:
                digest_text = digest_text[:20000] + "\n[...digest truncated]"
            digest_context = (
                f"ORIGINAL DIGEST ({digest_date}):\n"
                f"{'='*40}\n{digest_text}\n{'='*40}\n\n"
            )

    # Build context from retrieved chunks
    context_parts = []
    total_chars = len(digest_context)
    for chunk_meta, score in results:
        entry = (
            f"[Source: {chunk_meta['source_name']} | "
            f"Date: {chunk_meta['date']} | "
            f"Type: {chunk_meta['source_type']}"
        )
        if chunk_meta.get("page_number"):
            entry += f" | Page {chunk_meta['page_number']}"
        if chunk_meta.get("url"):
            entry += f" | URL: {chunk_meta['url']}"
        entry += f"]\n{chunk_meta['text']}\n"

        if total_chars + len(entry) > MAX_CONTEXT_CHARS:
            context_parts.append("\n[...additional results truncated for length]")
            break

        context_parts.append(entry)
        total_chars += len(entry)

    context = digest_context + "\n---\n".join(context_parts)

    print(f"  Retrieved {len(context_parts)} chunks ({total_chars:,} chars). Asking Opus...")

    client = anthropic.Anthropic()

    response = client.messages.create(
        model=REPLY_MODEL,
        max_tokens=4000,
        system=(
            "You are a research assistant for a credit/distressed investment analyst. "
            "You have access to an archive of investment research — PDFs, newsletters, "
            "SEC filings, Substack articles, and daily digests.\n\n"
            "RULES:\n"
            "- Answer using the provided source material. Extract every relevant detail — "
            "numbers, prices, yields, spreads, leverage ratios, dates, names.\n"
            "- The archive chunks ARE the source material. PDFs have been extracted and indexed. "
            "Do NOT say 'the full PDF wasn't indexed' or 'I don't have the full article' — "
            "if the data appears in the chunks, it IS from the source.\n"
            "- Cite specific sources and dates in parentheses: (Grant's, Mar 27, 2026).\n"
            "- Be direct and specific. Lead with the answer, not caveats.\n"
            "- Only flag a gap if the question asks for something genuinely not in any chunk "
            "(e.g., a specific page number that doesn't appear). Do NOT add generic disclaimers "
            "about archive limitations.\n\n"
            "Format your response as clean HTML suitable for email. Use the same styling as "
            "the daily digest: Georgia font, 14px, 680px max-width. Use <strong> for emphasis, "
            "<ul>/<li> for lists."
        ),
        messages=[{
            "role": "user",
            "content": f"Question: {question}\n\nArchive search results:\n{context}",
        }],
    )

    answer = response.content[0].text

    tokens_in = response.usage.input_tokens
    tokens_out = response.usage.output_tokens
    print(f"  Answer tokens: {tokens_in:,} in + {tokens_out:,} out")
    cost.record("reply answer", REPLY_MODEL, response.usage)

    # Wrap in container div if not already
    if not answer.strip().startswith("<div"):
        answer = (
            '<div style="font-family: Georgia, serif; max-width: 680px; margin: 0 auto; '
            'color: #1a1a1a; line-height: 1.6; font-size: 14px;">\n'
            f'{answer}\n'
            '<hr style="margin: 20px 0; border: none; border-top: 1px solid #ccc;">\n'
            '<p style="font-size: 11px; color: #888;">Answered by Claude from your research archive. '
            f'Searched {len(context_parts)} source chunks.</p>\n'
            '</div>'
        )

    return answer


# ======================================================================
# REPLY SENDING
# ======================================================================

def send_reply(service, thread_id, original_msg_id, subject, answer_html, rfc_message_id=""):
    """Reply in the same email thread with Claude's answer."""
    # Ensure subject has Re: prefix
    if not subject.startswith("Re:"):
        subject = f"Re: {subject}"

    message = MIMEText(answer_html, "html")
    message["to"] = ", ".join(DIGEST_RECIPIENTS)
    message["subject"] = subject

    # Use RFC Message-ID for proper threading in Outlook and other clients
    # Gmail uses threadId, but Outlook/Exchange thread by In-Reply-To + References
    if rfc_message_id:
        message["In-Reply-To"] = rfc_message_id
        message["References"] = rfc_message_id
    else:
        message["In-Reply-To"] = f"<{original_msg_id}@mail.gmail.com>"
        message["References"] = f"<{original_msg_id}@mail.gmail.com>"

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    for attempt in range(3):
        try:
            service.users().messages().send(
                userId="me",
                body={"raw": raw, "threadId": thread_id},
            ).execute()
            return True
        except Exception as e:
            if attempt < 2 and ("EOF" in str(e) or "SSL" in str(e)):
                print(f"  Send retry {attempt + 1}: {e}")
                time.sleep(2 ** attempt)
                service = get_gmail_service()
            else:
                print(f"  Failed to send reply: {e}")
                return False

    return False


def send_error_reply(service, thread_id, original_msg_id, subject, error_msg, rfc_message_id=""):
    """Reply with a brief error message rather than silently failing."""
    html = (
        '<div style="font-family: Georgia, serif; max-width: 680px; margin: 0 auto; '
        'color: #1a1a1a; line-height: 1.6; font-size: 14px;">'
        f'<p style="color: #c0392b;">Sorry, I couldn\'t process your question: {error_msg}</p>'
        '<p style="font-size: 12px; color: #888;">Try rephrasing, or reply again and I\'ll retry.</p>'
        '</div>'
    )
    send_reply(service, thread_id, original_msg_id, subject, html, rfc_message_id)


# ======================================================================
# MAIN LOOP
# ======================================================================

def process_replies(service):
    """Check for and process any pending replies."""
    global _replies_this_hour

    # Rate limiting — purge old entries
    now = time.time()
    _replies_this_hour = [t for t in _replies_this_hour if now - t < 3600]

    if len(_replies_this_hour) >= MAX_REPLIES_PER_HOUR:
        print(f"  Rate limit hit ({MAX_REPLIES_PER_HOUR}/hour). Skipping this cycle.")
        return 0

    replies = check_for_replies(service)
    if not replies:
        return 0

    print(f"  Found {len(replies)} pending question(s).")

    processed = 0
    for msg_id, thread_id, subject, question, digest_date, rfc_message_id in replies:
        if len(_replies_this_hour) >= MAX_REPLIES_PER_HOUR:
            print("  Rate limit reached. Deferring remaining replies.")
            break

        print(f"\n  Q: {question[:100]}...")
        if digest_date:
            print(f"  Digest date: {digest_date}")

        try:
            cost.reset()
            answer = answer_question(question, digest_date=digest_date)
            cost_text, _ = cost.summary()
            print(cost_text)
            success = send_reply(service, thread_id, msg_id, subject, answer, rfc_message_id)

            if success:
                print("  Replied successfully.")
                processed += 1
                _replies_this_hour.append(time.time())
            else:
                print("  Reply send failed.")

        except Exception as e:
            print(f"  Error answering question: {e}")
            try:
                send_error_reply(service, thread_id, msg_id, subject, str(e), rfc_message_id)
            except Exception:
                pass

        # Mark original as read regardless
        _mark_as_read(service, msg_id)

    return processed


def main():
    """Poll for replies and respond."""
    once = "--once" in sys.argv

    print(f"[{datetime.datetime.now()}] Reply monitor starting...")
    print(f"  Mode: {'single pass' if once else f'polling every {POLL_INTERVAL_SECONDS}s'}")
    print(f"  Rate limit: {MAX_REPLIES_PER_HOUR}/hour")

    service = get_gmail_service()
    print("  Gmail authenticated.")

    if once:
        n = process_replies(service)
        print(f"  Processed {n} replies. Done.")
        return

    while True:
        try:
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"\n[{ts}] Checking for replies...")
            n = process_replies(service)
            if n:
                print(f"  Processed {n} replies.")
            else:
                print("  No pending replies.")

        except Exception as e:
            print(f"  Error in poll cycle: {e}")
            # Rebuild service in case of auth issues
            try:
                service = get_gmail_service()
            except Exception:
                pass

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
