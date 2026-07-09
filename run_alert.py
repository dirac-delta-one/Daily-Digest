#!/usr/bin/env python3
"""
Run-failure alert (the first slice of §7.2 observability).

The run_*.bat wrappers invoke this when their python entry point exits nonzero:

    run_alert.py <label> [--test]     # label: digest | midday | reply_monitor

It emails the digest recipients a short failure notice with the tail of the
relevant log (logs/<label>.log), so unattended failures aren't silent.
`--test` marks the subject as a drill without needing a real failure.

Deliberately self-contained — no `import digest`: the failure path must not
depend on the code that just failed (e.g. an import error in digest.py would
otherwise take the alerter down with it). Gmail auth here is token-refresh
ONLY — it never opens an interactive browser consent (this runs unattended at
8 AM); if the token is dead it prints and exits nonzero, and the missing
digest email remains the fallback signal.
"""

import base64
import datetime
import html
import os
import socket
import sys
from email.mime.text import MIMEText
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
TAIL_LINES = 40

# Same env-driven recipient logic as digest.py, duplicated on purpose (see
# module docstring): DIGEST_TO overrides the production default.
RECIPIENTS = [
    r.strip()
    for r in os.environ.get(
        "DIGEST_TO", "jtramontano@acorninv.com,acorn.research.bot@gmail.com"
    ).split(",")
    if r.strip()
]


def _tail(path, n=TAIL_LINES):
    """Last n lines of a log file, or a placeholder if unreadable."""
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except OSError:
        return f"(could not read log: {path})"


def _find_log(label):
    """Newest log file for a label (O1 rotation-aware).

    The wrappers write date-stamped logs (digest_YYYY-MM-DD.log) since the O1
    rotation; picking the newest by mtime also covers the legacy un-dated name
    and a run that crosses midnight (the file keeps its start-date name but
    stays the most recently written).
    """
    logs_dir = SCRIPT_DIR / "logs"
    candidates = sorted(logs_dir.glob(f"{label}*.log"),
                        key=lambda p: p.stat().st_mtime)
    return candidates[-1] if candidates else logs_dir / f"{label}.log"


def build_alert_html(label, log_tail, when=None, host=None,
                     headline=None, detail=None):
    """Failure-notice HTML in the digest's Georgia/680px style. Log tail is escaped.

    headline/detail default to the run-FAILED wording; the O2 watchdog passes
    its own ("run MISSING" / hung-or-never-started).
    """
    when = when or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    host = host or socket.gethostname()
    headline = headline or f"{label} run FAILED"
    detail = detail or ("The scheduled run exited nonzero &mdash; "
                        "no digest was produced. Last log lines below.")
    return (
        '<div style="font-family: Georgia, \'Times New Roman\', serif; max-width: 680px; '
        'margin: 0 auto; color: #1a1a1a; line-height: 1.6;">\n'
        '<div style="background: #fdf2f2; border: 2px solid #c0392b; border-radius: 6px; '
        'padding: 16px 20px; margin-bottom: 16px;">\n'
        f'<h2 style="font-size: 18px; color: #c0392b; margin: 0 0 6px;">'
        f'\U0001f6a8 {html.escape(headline)}</h2>\n'
        f'<p style="font-size: 13px; margin: 0;">Host: {html.escape(host)} &middot; '
        f'{html.escape(when)}. {detail}</p>\n'
        '</div>\n'
        f'<pre style="font-size: 11px; background: #f7f5f0; padding: 12px; '
        f'overflow-x: auto; white-space: pre-wrap;">{html.escape(log_tail)}</pre>\n'
        '</div>'
    )


def _gmail_service_noninteractive():
    """Gmail service from token.json, refresh-only (never a browser consent)."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    token_file = SCRIPT_DIR / "token.json"
    if not token_file.exists():
        raise RuntimeError("token.json missing — cannot send failure alert")

    creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())  # a dead token raises — caller logs and exits
        else:
            raise RuntimeError("Gmail token invalid and not refreshable")
    return build("gmail", "v1", credentials=creds)


def _send_email(subject, body):
    """Send one HTML email to the alert recipients (refresh-only Gmail auth)."""
    message = MIMEText(body, "html")
    message["to"] = ", ".join(RECIPIENTS)
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service = _gmail_service_noninteractive()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()


def send_alert(label, test=False):
    log_file = _find_log(label)
    body = build_alert_html(label, _tail(log_file))

    today = datetime.date.today().strftime("%A, %B %d")
    # Drill marker goes FIRST: clients truncate subjects from the END, and a
    # drill whose TEST tag is cut off reads as a real emergency (seen 7/09).
    marker = "(TEST drill) " if test else ""
    subject = f"\U0001f6a8 {marker}Daily Digest run FAILED — {label} — {today}"

    _send_email(subject, body)
    print(f"Failure alert sent to {', '.join(RECIPIENTS)} ({label}{' TEST' if test else ''}).")


def check_completed(label, test=False):
    """O2 hung-run watchdog: alert if today's run never completed.

    A run that HANGS (e.g. blocked on an interactive OAuth consent) or never
    starts exits nothing, so the wrappers' nonzero-exit alert can't fire —
    the 7/7 network race proved both signals can die together. This mode is
    meant for a ~9 AM weekday scheduled task (registered at deploy via
    Register-ScheduledTask, F1a #2): it checks the completion marker the
    digest writes after a successful send and alerts if it's absent.

    Only `digest` has a completion artifact (archive/<today>/digest_sent_at.txt);
    midday is silent-by-design most days and can't be watchdogged this way.
    `--test` sends the alert regardless, marked as a drill.

    Returns 0 if completed (or the drill/alert was sent), 1 if an alert was
    needed but could not be sent, 2 on a label without a completion marker.
    """
    if label != "digest":
        print(f"--check-completed supports only 'digest' (no completion marker for {label}).")
        return 2

    today = datetime.date.today().isoformat()
    marker = SCRIPT_DIR / "archive" / today / "digest_sent_at.txt"
    if marker.exists() and not test:
        print(f"OK: digest completed today ({marker.read_text(encoding='utf-8').strip()}).")
        return 0

    now = datetime.datetime.now().strftime("%H:%M")
    detail = (f"No completed digest for {today} as of {now} &mdash; the morning run "
              "likely hung (e.g. an interactive consent) or never started, so the "
              "nonzero-exit alert could not fire. Last log lines below.")
    body = build_alert_html("digest", _tail(_find_log("digest")),
                            headline="digest run MISSING", detail=detail)
    # Drill marker goes FIRST — same truncation reasoning as send_alert.
    marker = "(TEST drill) " if test else ""
    subject = (f"\U0001f6a8 {marker}Daily Digest MISSING — no completed run — "
               f"{datetime.date.today().strftime('%A, %B %d')}")

    try:
        _send_email(subject, body)
        print(f"Watchdog alert sent to {', '.join(RECIPIENTS)}"
              f"{' (TEST)' if test else ''}.")
        return 0
    except Exception as e:
        print(f"Could not send watchdog alert: {e}")
        return 1


def main():
    label = next((a for a in sys.argv[1:] if not a.startswith("--")), "digest")
    if label not in ("digest", "midday", "reply_monitor"):
        print(f"Unknown label '{label}' — expected digest | midday | reply_monitor")
        return 2

    if "--check-completed" in sys.argv:
        return check_completed(label, test="--test" in sys.argv)

    try:
        send_alert(label, test="--test" in sys.argv)
        return 0
    except Exception as e:
        # Nothing else to fall back to — log it; the missing digest email is
        # the remaining signal.
        print(f"Could not send failure alert: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
