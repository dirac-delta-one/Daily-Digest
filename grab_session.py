#!/usr/bin/env python3
"""
Grab Substack session from your Chrome browser.

How to use:
1. Log into Substack normally in Chrome (not Playwright)
2. Close Chrome completely
3. Run: python grab_session.py
4. Done — substack_session.json is created for the scraper to use
"""

import json
import sys
from pathlib import Path

try:
    import rookiepy
except ImportError:
    print("Install rookiepy first:  pip install rookiepy")
    sys.exit(1)

SESSION_FILE = Path(__file__).parent / "substack_session.json"


def main():
    print("Reading cookies from Chrome...")
    print("(Make sure Chrome is fully closed first!)\n")

    try:
        # Get all cookies for substack.com from Chrome
        cookies = rookiepy.chrome(domains=["substack.com", ".substack.com"])
    except Exception as e:
        print(f"Error reading Chrome cookies: {e}")
        print("\nTroubleshooting:")
        print("  - Make sure Chrome is completely closed (check Task Manager)")
        print("  - On Mac, you may need to grant Terminal full disk access")
        print("  - If you use a Chrome profile, try: rookiepy.chrome(domains=[...], profile='Profile 1')")
        sys.exit(1)

    if not cookies:
        print("No Substack cookies found in Chrome.")
        print("Make sure you're logged into substack.com in Chrome first.")
        sys.exit(1)

    # Convert to Playwright session format
    playwright_cookies = []
    for c in cookies:
        cookie = {
            "name": c.get("name", ""),
            "value": c.get("value", ""),
            "domain": c.get("domain", ""),
            "path": c.get("path", "/"),
            "secure": c.get("secure", False),
            "httpOnly": c.get("httpOnly", False),
            "sameSite": "Lax",
        }

        # Add expiry if present
        if c.get("expires"):
            cookie["expires"] = c["expires"]

        playwright_cookies.append(cookie)

    # Save in Playwright's storage_state format
    session = {
        "cookies": playwright_cookies,
        "origins": [],
    }

    SESSION_FILE.write_text(json.dumps(session, indent=2))

    # Check if we got the important cookies
    cookie_names = {c["name"] for c in playwright_cookies}
    has_sid = "substack.sid" in cookie_names

    print(f"Saved {len(playwright_cookies)} cookies to {SESSION_FILE.name}")

    if has_sid:
        print("✅ Found substack.sid — session looks good!")
    else:
        print("⚠️  No substack.sid cookie found — you may not be logged in.")
        print("   Log into substack.com in Chrome and try again.")

    print("\nYou can now run: python digest.py")


if __name__ == "__main__":
    main()
