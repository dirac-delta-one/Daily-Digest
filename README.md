# Daily Investment Digest

Reads your Gmail inbox + paid Substack subscriptions, summarizes everything with Claude Opus, and emails you a structured research briefing once a day.

## Setup (one-time)

### 1. Install dependencies

```bash
cd Daily-Digest
pip install -r requirements.txt
playwright install chromium
```

### 2. Get Google Cloud credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or use an existing one)
3. Enable the **Gmail API**: search "Gmail API" in the API library and click Enable
4. Go to **APIs & Services → Credentials**
5. Click **Create Credentials → OAuth client ID**
6. Choose **Desktop app**, give it a name, click Create
7. Download the JSON file and save it as `credentials.json` in this folder
8. Go to **APIs & Services → OAuth consent screen → Audience/Test users**
9. Add your Gmail address as a test user

### 3. Set environment variables

Create `env.bat` in the project root (gitignored). The `run_*.bat` wrappers `call` it:

```bat
set ANTHROPIC_API_KEY=sk-ant-...
set FRED_API_KEY=...                  REM optional: Macro Dashboard + Fed balance sheet
set SUBSTACK_EMAIL=your@email.com     REM Substack auto-logs in via magic link (no password)
REM On a test machine, route ALL digest/alert/reply email to yourself instead of the
REM production recipients (defaults to the production list if unset):
set DIGEST_TO=you@example.com
```

`PYTHONUTF8=1` is already set by the `run_*.bat` wrappers (the logs contain Unicode and crash
under the default Windows cp1252 console). When running a script manually, set it yourself:
`set PYTHONUTF8=1`.

On Mac/Linux, use `export` instead of `set`. To make permanent, add to your
`~/.zshrc`, `~/.bash_profile`, or Windows system environment variables.

### 4. Run it once manually

```bash
python digest.py
```

The first run:
- Opens a browser for Google OAuth — log in and authorize
- Authenticates Substack via magic link (delivered to your Gmail) and saves `substack_cookie.txt`
- Sends you a test digest email

## Scheduling

### Windows (Task Scheduler)

The repo ships `run_digest.bat`, `run_midday.bat`, `run_reply_monitor.bat` (each `cd`s to its
own folder via `%~dp0`, sets `PYTHONUTF8=1`, calls `env.bat`, and runs the project `.venv`
Python) plus `setup_tasks.bat` to register all three tasks — no hardcoded paths.

1. Create `env.bat` in the project root (see "Set environment variables" above).
2. Run `setup_tasks.bat` — registers MorningDigest (8 AM), MiddayAlert (1 PM), and ReplyMonitor
   (at startup). It uses `%~dp0`, so the tasks point at wherever the repo lives.
3. Verify: `schtasks /Query /TN "DailyDigest\*"`.

To register a task manually instead, set the action to the relevant `run_*.bat` with "Start in"
= the project folder.

### Mac/Linux (cron)

```bash
crontab -e
```

```
ANTHROPIC_API_KEY=sk-ant-...
SUBSTACK_EMAIL=your@email.com
PYTHONUTF8=1
30 7 * * * cd /path/to/Daily-Digest && /path/to/python digest.py >> digest.log 2>&1
```

## Configuration

Edit the top of `digest.py`:
- `HOURS_LOOKBACK` — how far back to fetch (default: 24 hours)
- `MAX_EMAILS` — cap on emails to summarize (default: 50)
- `DIGEST_RECIPIENTS` — recipients; defaults to the production list, override with the `DIGEST_TO` env var
- `CLAUDE_MODEL` — which Claude model to use (default: opus)
- `MAX_PDF_SIZE_MB` — skip PDFs larger than this (default: 5MB)

Edit the top of `substack.py`:
- `MAX_ARTICLES_PER_PUB` — max Substack articles per publication per run (default: 3)
- `MAX_ARTICLE_CHARS` — truncate long articles (default: 8000 chars)

## Files

- `digest.py` — main script (Gmail + Claude + send)
- `substack.py` — Substack scraper (internal API + session cookie)
- `env.bat` — your environment variables (gitignored; you create it)
- `credentials.json` — Google OAuth credentials (you provide)
- `token.json` — auto-generated Gmail auth token
- `substack_cookie.txt` — auto-generated Substack session cookie

## Cost

With Claude Opus and PDF/Substack content, expect roughly $0.50–$2.00 per daily
digest depending on volume. Heavier days with many PDFs and long articles will
cost more. Monitor usage at console.anthropic.com for the first week.
