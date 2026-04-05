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

```bash
# Required
set ANTHROPIC_API_KEY=sk-ant-...

# Required for Substack (skip if you don't want Substack scraping)
set SUBSTACK_EMAIL=your@email.com
set SUBSTACK_PASSWORD=your-password
```

On Mac/Linux, use `export` instead of `set`. To make permanent, add to your
`~/.zshrc`, `~/.bash_profile`, or Windows system environment variables.

### 4. Run it once manually

```bash
python digest.py
```

The first run:
- Opens a browser for Google OAuth — log in and authorize
- Logs into Substack and saves the session for future runs
- Sends you a test digest email

## Scheduling

### Windows (Task Scheduler)
1. Open Task Scheduler
2. Create Basic Task → name it "Daily Digest"
3. Trigger: Daily, set your preferred time (e.g. 7:30 AM)
4. Action: Start a Program
   - Program: `C:\Users\jared\AppData\Local\Programs\Python\Python312\python.exe`
   - Arguments: `digest.py`
   - Start in: `C:\Users\jared\Daily-Digest`
5. Make sure environment variables are set system-wide (not just in your terminal)

### Mac/Linux (cron)

```bash
crontab -e
```

```
ANTHROPIC_API_KEY=sk-ant-...
SUBSTACK_EMAIL=your@email.com
SUBSTACK_PASSWORD=your-password
30 7 * * * cd /path/to/Daily-Digest && /path/to/python digest.py >> digest.log 2>&1
```

## Configuration

Edit the top of `digest.py`:
- `HOURS_LOOKBACK` — how far back to fetch (default: 24 hours)
- `MAX_EMAILS` — cap on emails to summarize (default: 50)
- `DIGEST_RECIPIENTS` — list of email addresses to send the digest to
- `CLAUDE_MODEL` — which Claude model to use (default: opus)
- `MAX_PDF_SIZE_MB` — skip PDFs larger than this (default: 5MB)

Edit the top of `substack.py`:
- `MAX_ARTICLES` — max Substack articles per run (default: 15)
- `MAX_ARTICLE_CHARS` — truncate long articles (default: 8000 chars)

## Files

- `digest.py` — main script (Gmail + Claude + send)
- `substack.py` — Substack scraper (Playwright)
- `credentials.json` — Google OAuth credentials (you provide)
- `token.json` — auto-generated Gmail auth token
- `substack_session.json` — auto-generated Substack browser session

## Cost

With Claude Opus and PDF/Substack content, expect roughly $0.50–$2.00 per daily
digest depending on volume. Heavier days with many PDFs and long articles will
cost more. Monitor usage at console.anthropic.com for the first week.
