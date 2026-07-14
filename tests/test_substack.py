"""_check_session — the probe must actually distinguish logged-in from
logged-out. The old /reader/feed probe returned 200 to anonymous requests, so
a dead cookie passed the check and magic-link renewal never fired (the
2026-07-13 dead-cookie incident). Pins the /user/profile/self probe semantics:
200 -> True, 401/403 -> False, network error -> False (which triggers the
renewal path in fetch_substack_articles)."""

import substack


class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class _FakeSession:
    def __init__(self, status_code=None, exc=None):
        self.status_code = status_code
        self.exc = exc
        self.requested_urls = []

    def get(self, url, timeout=None):
        self.requested_urls.append(url)
        if self.exc:
            raise self.exc
        return _FakeResponse(self.status_code)


def test_check_session_authenticated():
    assert substack._check_session(_FakeSession(200)) is True


def test_check_session_dead_cookie_401():
    assert substack._check_session(_FakeSession(401)) is False


def test_check_session_403():
    assert substack._check_session(_FakeSession(403)) is False


def test_check_session_network_error():
    assert substack._check_session(_FakeSession(exc=OSError("boom"))) is False


def test_check_session_probes_profile_not_reader_feed():
    # The whole fix: /reader/feed answers 200 even logged out, so probing it
    # made the check vacuous. The probe must be an auth-gated endpoint.
    session = _FakeSession(200)
    substack._check_session(session)
    assert session.requested_urls == ["https://substack.com/api/v1/user/profile/self"]


# --- _cap_and_flag_preview: paywall previews must be visibly labeled ---

PREVIEW_MARK = "[preview only — the remainder of this article is paywalled]"


def test_preview_flagged_when_text_far_short_of_wordcount():
    # ~140 accessible words of a 2,064-word post (the Fixed Income Beacon case)
    text = "word " * 140
    out = substack._cap_and_flag_preview(text, wordcount=2064)
    assert out.endswith(PREVIEW_MARK)


def test_full_text_not_flagged():
    text = "word " * 2000
    out = substack._cap_and_flag_preview(text, wordcount=2064)
    assert PREVIEW_MARK not in out


def test_no_wordcount_never_flags():
    out = substack._cap_and_flag_preview("short intro text", wordcount=None)
    assert PREVIEW_MARK not in out
    assert substack._cap_and_flag_preview("short", wordcount=0) == "short"


def test_our_truncation_is_not_mistaken_for_preview():
    # A full long article capped by MAX_ARTICLE_CHARS: the preview check runs
    # on the UNCAPPED text, so only the truncation marker appears.
    text = "word " * 4000  # 20,000 chars, wordcount matches -> full text
    out = substack._cap_and_flag_preview(text, wordcount=4000)
    assert "[...truncated]" in out
    assert PREVIEW_MARK not in out


def test_long_preview_gets_both_markers():
    # A preview that ALSO exceeds the cap (huge article): both markers, with
    # the preview marker appended after the cap so it can't be cut off.
    text = "word " * 2000  # 10,000 chars but only 20% of the true wordcount
    out = substack._cap_and_flag_preview(text, wordcount=10000)
    assert "[...truncated]" in out
    assert out.endswith(PREVIEW_MARK)


def test_get_article_text_flags_archive_branch_preview():
    # Archive body_html present (>200 chars) but far short of wordcount.
    post = {"body_html": "<p>" + "intro words here " * 20 + "</p>",
            "wordcount": 3000}
    out = substack._get_article_text(_FakeSession(200), post, "https://x.substack.com/")
    assert out.endswith(PREVIEW_MARK)


# --- _extract_otp_code: the passwordless-renewal code parser (2026-07-14) ---
# Substack's flow now emails a 6-digit CODE ("NNNNNN is your Substack
# verification code"), not a magic LINK — so renewal reads the code, not a URL.

def test_extract_otp_from_subject():
    assert substack._extract_otp_code("850582 is your Substack verification code") == "850582"


def test_extract_otp_body_fallback():
    # Subject confirms it's a code email but carries no digits; code is in body.
    code = substack._extract_otp_code(
        "Your Substack verification code", "Enter this code: 123456 to sign in.")
    assert code == "123456"


def test_extract_otp_rejects_non_code_email():
    # A 6-digit number in an unrelated Substack email must NOT be taken as a code.
    assert substack._extract_otp_code("Weekly recap: 500000 subscribers milestone") is None


def test_extract_otp_none_when_no_digits():
    assert substack._extract_otp_code("Your Substack verification code", "no digits here") is None


def test_extract_otp_empty():
    assert substack._extract_otp_code("", "") is None
