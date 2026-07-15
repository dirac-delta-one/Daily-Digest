"""Cleanup Stage 1.1 — pin digest.main()'s wiring/order invariants.

These orderings were validated live (WORKLOG 2026-07-10/13) but had no
regression net, and a regression would only surface unattended on the server:
- pacer.commit_seen() fires only AFTER the last send (F1a-4: a crash before
  send must re-surface entries, never silently lose them);
- the O2 completion marker (archive/<date>/digest_sent_at.txt) is written
  AFTER the last send (a marker written early would blind the 9 AM watchdog);
- the shared memory is fed the TEAM html when the team variant exists (the
  substack-cleanse invariant) and the FULL html otherwise;
- O3 counts are recorded exactly once per run;
- the team variant generates FIRST (it writes the shared cache prefix) and
  only when TEAM_RECIPIENTS is non-empty.

Everything external is stubbed: no network, no Gmail, no Claude, tmp dirs only.
"""

import datetime

import pytest

import digest


@pytest.fixture
def harness(tmp_path, monkeypatch):
    """Drive the real main() with every external effect stubbed + recorded.

    Each recorded call carries `marker.exists()` at call time, so the tests can
    assert the completion marker appears only after the last send/commit.
    """
    calls = []
    marker = (tmp_path / "archive" / datetime.date.today().isoformat()
              / "digest_sent_at.txt")

    monkeypatch.setattr(digest, "DIGESTS_DIR", tmp_path / "digests")
    monkeypatch.setattr(digest, "get_gmail_service", lambda: "SERVICE")
    monkeypatch.setattr(digest, "fetch_recent_emails", lambda service: [])
    monkeypatch.setattr(
        digest, "fetch_substack_articles",
        lambda gmail_service=None: [
            {"title": "t", "author": "a", "url": "u", "text": "x"}
        ])
    monkeypatch.setattr(digest, "fetch_wiltw", lambda: None)

    fetched = {key: [] for key, *_ in digest.SOURCE_FETCHERS}
    fetched["news_articles"] = [
        {"title": "n", "url": "http://x", "summary": "", "source": "WSJ"}
    ]
    monkeypatch.setattr(digest, "_fetch_all_sources", lambda: dict(fetched))

    def fake_summarize(**kwargs):
        label = kwargs.get("cost_label", "")
        calls.append((f"summarize{label}", marker.exists()))
        # template-shaped: the double-border header is the anchor
        # _assemble_digest_html needs to inject the alert box
        html = ('<div style="font-family: Georgia;">'
                '<div style="border-bottom: 3px double #1a1a1a;">Header</div>'
                f'DIGEST{label}</div>')
        return (html, f"SRC{label}")
    monkeypatch.setattr(digest, "summarize_with_claude", fake_summarize)

    monkeypatch.setattr(digest, "get_substack_memory_context", lambda: "")
    monkeypatch.setattr(
        digest, "evaluate_alerts",
        lambda source: calls.append(("alerts", source)) or [])
    monkeypatch.setattr(
        digest, "record_and_check",
        lambda counts: calls.append(("o3", dict(counts))) or [])
    monkeypatch.setattr(
        digest, "send_digest_email",
        lambda service, html, recipients=None, subject=None:
        calls.append(("send", tuple(recipients) if recipients else ("FULL",),
                      marker.exists(), html)))
    monkeypatch.setattr(
        digest, "commit_seen",
        lambda: calls.append(("commit_seen", marker.exists())))
    monkeypatch.setattr(
        digest, "archive_daily_content", lambda **kw: calls.append(("archive",)))
    monkeypatch.setattr(
        digest, "index_daily_content", lambda d: calls.append(("index", d)))
    monkeypatch.setattr(
        digest, "update_memory", lambda html: calls.append(("update_memory", html)))
    monkeypatch.setattr(
        digest, "update_substack_memory",
        lambda arts: calls.append(("update_substack", len(arts))))
    monkeypatch.setattr(digest, "_is_friday", lambda: False)

    return calls, marker


def test_full_only_wiring(harness, monkeypatch):
    calls, marker = harness
    # the pre-team world: no team recipients AND no activation date (with the
    # date set, an empty team list is a misconfiguration — tested separately)
    monkeypatch.setattr(digest, "TEAM_RECIPIENTS", [])
    monkeypatch.setattr(digest, "TEAM_ACTIVATION_DATE", None)

    digest.main()
    names = [c[0] for c in calls]

    # single (full) generation and send; no team anything
    assert "summarize (team)" not in names
    assert names.count("send") == 1

    # commit_seen strictly after the send; marker absent at both moments,
    # present by the end of the run
    send_i, commit_i = names.index("send"), names.index("commit_seen")
    assert send_i < commit_i
    assert calls[send_i][2] is False
    assert calls[commit_i][1] is False
    assert marker.exists()

    # memory fed from the FULL html when no team variant exists (main passes
    # the ASSEMBLED html — pre-built sections injected — so assert on content)
    mem_html = next(c[1] for c in calls if c[0] == "update_memory")
    assert "DIGEST" in mem_html and "(team)" not in mem_html
    assert ("update_substack", 1) in calls

    # O3 counts recorded exactly once; alert eval ran on the full source only
    assert names.count("o3") == 1
    assert [c[1] for c in calls if c[0] == "alerts"] == ["SRC"]


def test_team_active_wiring(harness, monkeypatch):
    calls, marker = harness
    monkeypatch.setattr(digest, "TEAM_RECIPIENTS", ["team@acorninv.com"])

    digest.main()
    names = [c[0] for c in calls]

    # team generates FIRST — it writes the shared cache prefix the full run reads
    assert names.index("summarize (team)") < names.index("summarize")

    # two sends (full then team); commit_seen after the LAST send; the
    # completion marker appears only after all of them
    send_is = [i for i, n in enumerate(names) if n == "send"]
    assert len(send_is) == 2
    commit_i = names.index("commit_seen")
    assert send_is[-1] < commit_i
    assert all(calls[i][2] is False for i in send_is)
    assert calls[commit_i][1] is False
    assert marker.exists()

    # full send uses the default recipients; team send carries the team list
    assert calls[send_is[0]][1] == ("FULL",)
    assert calls[send_is[1]][1] == ("team@acorninv.com",)

    # the substack-cleanse invariant: shared memory learns from the TEAM html
    # (assembled — so assert on the variant marker in the content)
    mem_html = next(c[1] for c in calls if c[0] == "update_memory")
    assert "DIGEST (team)" in mem_html

    # per-variant alert evals, full first; O3 recorded once
    assert [c[1] for c in calls if c[0] == "alerts"] == ["SRC", "SRC (team)"]
    assert names.count("o3") == 1


def test_post_activation_misconfig_guard(harness, monkeypatch):
    # CLEANUP_SPEC 2.1: activation recorded in config but DIGEST_TO_TEAM empty
    # -> the run completes and sends, but memory is NOT fed the full digest,
    # and the sent email carries a loud config alert.
    calls, marker = harness
    monkeypatch.setattr(digest, "TEAM_RECIPIENTS", [])
    monkeypatch.setattr(digest, "TEAM_ACTIVATION_DATE", "2026-07-13")

    digest.main()
    names = [c[0] for c in calls]

    assert "update_memory" not in names          # shared store protected
    assert ("update_substack", 1) in calls       # jared-personal store unaffected
    assert names.count("send") == 1              # the run still delivers
    assert marker.exists()                       # and still completes (O2)
    sent_html = next(c[3] for c in calls if c[0] == "send")
    assert "Team config missing" in sent_html    # visible in the email itself


# --- Receiving-side policy + self-ingestion guard (CLEANUP_SPEC 2.5) ---

def test_recipient_defaults_are_acorninv_only():
    # Operator policy 2026-07-14: @acorninv.com only on the receiving side.
    import run_alert
    for default in (digest._DEFAULT_RECIPIENTS, run_alert._DEFAULT_RECIPIENTS):
        addrs = [a.strip() for a in default.split(",") if a.strip()]
        assert addrs, "default recipient list must not be empty"
        assert all(a.endswith("@acorninv.com") for a in addrs)
    assert digest.BOT_ADDRESS not in digest._DEFAULT_RECIPIENTS


def test_o3_counts_track_substack_fulltext(harness, monkeypatch):
    # CLEANUP_SPEC 4.2: preview-flagged and paid-only-failure articles don't
    # count as full text — a leak-closure at Substack then shows up as a
    # fulltext collapse even while the total stays healthy
    calls, _marker = harness
    monkeypatch.setattr(digest, "TEAM_RECIPIENTS", [])
    monkeypatch.setattr(digest, "TEAM_ACTIVATION_DATE", None)
    monkeypatch.setattr(digest, "fetch_substack_articles", lambda gmail_service=None: [
        {"title": "full", "author": "a", "url": "u", "text": "real body text"},
        {"title": "prev", "author": "b", "url": "u",
         "text": "intro\n[preview only — the remainder of this article is paywalled]"},
        {"title": "fail", "author": "c", "url": "u",
         "text": "[Paid-only post — could not access full content. Check cookie/login.]"},
    ])

    digest.main()
    counts = next(c[1] for c in calls if c[0] == "o3")
    assert counts["substack"] == 3
    assert counts["substack_fulltext"] == 1


def test_is_self_artifact():
    f = digest._is_self_artifact
    # the system's own output (any subject) — sender rule
    assert f("Acorn Research Bot <acorn.research.bot@gmail.com>", "anything")
    # replies to digests (observed ingested 2026-07-14) — subject rule,
    # including the FULL variant's marker
    assert f("acohen@acorninv.com",
             "RE: [FULL] \U0001f4ec Daily Inbox Digest — Monday, July 13")
    assert f("acohen@acorninv.com",
             "Re: \U0001f4ec Daily Inbox Digest — Monday, July 13")
    # real source mail passes: forwarded research, Substack OTP, plain mail
    assert not f("Jared T <jtramontano@acorninv.com>", "FW: Stifel New Issue Flash")
    assert not f("no-reply@substack.com", "850582 is your Substack verification code")
    assert not f("news@bloomberg.net", "Today's News")
    assert not f(None, None)
