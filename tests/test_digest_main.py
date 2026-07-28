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
    monkeypatch.setattr(digest, "fetch_recent_emails",
                        lambda service, hours=None: [])
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
    # Part II: recipients pinned (real defaults are env-driven), per-owner eval
    # stubbed, and the state-touching alert_commands hooks neutralized so the
    # wiring tests don't depend on seeded tmp state.
    monkeypatch.setattr(digest, "DIGEST_RECIPIENTS", ["jared@acorninv.com"])
    monkeypatch.setattr(
        digest, "evaluate_owner_alerts",
        lambda source, owner_alerts, watchlist=None:
        calls.append(("alerts", source, tuple(owner_alerts))) or {})
    monkeypatch.setattr(digest.alert_commands, "orphan_notices",
                        lambda recipients, today=None: [])
    monkeypatch.setattr(
        digest, "record_and_check",
        lambda counts: calls.append(("o3", dict(counts))) or [])
    monkeypatch.setattr(
        digest, "send_digest_email",
        lambda service, html, recipients=None, subject=None:
        calls.append(("send", tuple(recipients) if recipients else ("FULL",),
                      marker.exists(), html, subject)))
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

    # per-recipient sends (Part II): full first, then the team recipient
    assert calls[send_is[0]][1] == ("jared@acorninv.com",)
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
    # -> the run completes and sends, but memory is NOT fed the full digest.
    # Since the footer reroute (2026-07-28) the config alert rides the FULL
    # send's grey ops footer — no separate ⚙️ email, no red-box clutter.
    calls, marker = harness
    monkeypatch.setattr(digest, "TEAM_RECIPIENTS", [])
    monkeypatch.setattr(digest, "TEAM_ACTIVATION_DATE", "2026-07-13")

    digest.main()
    names = [c[0] for c in calls]

    assert "update_memory" not in names          # shared store protected
    assert ("update_substack", 1) in calls       # jared-personal store unaffected
    assert marker.exists()                       # and still completes (O2)

    sends = [c for c in calls if c[0] == "send"]
    assert len(sends) == 1                       # ONE email — no separate ⚙️
    assert "Team config missing" in sends[0][3]  # …because it rides the footer
    assert "System notices" in sends[0][3]


def test_ops_alerts_ride_full_footer_only(harness, monkeypatch):
    # 2026-07-28 reroute (new-operator request; supersedes the 2026-07-22
    # separate-⚙️-email split): operational signals render as a grey footer
    # on the FULL sends only; content signals (watch-item expiry) stay in the
    # red box; TEAM sends and the durable artifacts never carry the footer.
    calls, _marker = harness
    monkeypatch.setattr(digest, "TEAM_RECIPIENTS", ["team@acorninv.com"])
    monkeypatch.setattr(
        digest, "record_and_check",
        lambda counts: ["news: 0 items for 3 straight runs"])
    monkeypatch.setattr(
        digest.alert_commands, "consume_expired",
        lambda: [{"owner": None,
                  "notice": "Watchlist ticker BBB expired 2026-07-21 and was removed."}])

    digest.main()
    sends = [c for c in calls if c[0] == "send"]
    assert len(sends) == 2                       # FULL + TEAM, nothing else
    full_html, team_html = sends[0][3], sends[1][3]

    assert "Source degradation" in full_html     # ops -> FULL footer
    assert "System notices" in full_html
    assert "Source degradation" not in team_html  # never to the team
    assert "System notices" not in team_html
    assert "Watch item expired" in full_html     # content stays in the red box
    assert "Watch item expired" in team_html

    # the durable artifacts (memory here; same html feeds save/archive/index)
    # stay footer-free — the footer is a send-time append only
    mem_html = next(c[1] for c in calls if c[0] == "update_memory")
    assert "System notices" not in mem_html


def test_per_recipient_alert_boxes(harness, monkeypatch):
    # Part II: each recipient's email carries THEIR alerts; the neutral base
    # (saved / fed to memory) carries nobody's.
    calls, _marker = harness
    monkeypatch.setattr(digest, "TEAM_RECIPIENTS",
                        ["apain@acorninv.com", "acohen@acorninv.com"])
    monkeypatch.setattr(
        digest, "evaluate_owner_alerts",
        lambda source, owner_alerts, watchlist=None: {
            "apain@acorninv.com": [{"name": "APAIN ONLY", "detail": "x", "source": "s"}],
            "acohen@acorninv.com": [{"name": "ACOHEN ONLY", "detail": "y", "source": "s"}],
        })
    # owned expiry notice routes to its owner's box only
    monkeypatch.setattr(
        digest.alert_commands, "expiring_today",
        lambda: [{"owner": "apain@acorninv.com",
                  "notice": 'Alert "APAIN TIMED" ends after today\'s run.'}])

    digest.main()
    sends = {c[1][0]: c[3] for c in calls if c[0] == "send"
             and not (c[4] or "").startswith("⚙️")}

    apain_html = sends["apain@acorninv.com"]
    acohen_html = sends["acohen@acorninv.com"]
    assert "APAIN ONLY" in apain_html and "ACOHEN ONLY" not in apain_html
    assert "ACOHEN ONLY" in acohen_html and "APAIN ONLY" not in acohen_html
    assert "APAIN TIMED" in apain_html and "APAIN TIMED" not in acohen_html

    # neutral base: saved for the weekly wrap + fed to memory — no personal alerts
    mem_html = next(c[1] for c in calls if c[0] == "update_memory")
    for personal in ("APAIN ONLY", "ACOHEN ONLY", "APAIN TIMED"):
        assert personal not in mem_html


def test_partial_send_failure_raises_after_all_attempts(harness, monkeypatch):
    # Part II send loop: one recipient failing doesn't block the others, the
    # run still fails loudly at the end, and commit_seen never runs (PACER
    # entries must re-surface tomorrow).
    calls, marker = harness
    monkeypatch.setattr(digest, "TEAM_RECIPIENTS",
                        ["apain@acorninv.com", "acohen@acorninv.com"])

    def flaky_send(service, html, recipients=None, subject=None):
        calls.append(("send", tuple(recipients), marker.exists(), html, subject))
        if recipients == ["apain@acorninv.com"]:
            raise OSError("smtp exploded")

    monkeypatch.setattr(digest, "send_digest_email", flaky_send)

    with pytest.raises(RuntimeError, match="apain@acorninv.com"):
        digest.main()

    sent_to = [c[1][0] for c in calls if c[0] == "send"]
    # all three recipients were attempted (jared FULL + both team)
    assert sent_to == ["jared@acorninv.com", "apain@acorninv.com",
                       "acohen@acorninv.com"]
    assert "commit_seen" not in [c[0] for c in calls]
    assert not marker.exists()


class _Resp:
    def __init__(self, stop_reason):
        self.stop_reason = stop_reason


def test_guard_truncation_detects_cap(monkeypatch):
    monkeypatch.setattr(digest, "_TRUNCATIONS", [])
    assert digest._guard_truncation("digest pass 1", _Resp("max_tokens")) is True
    assert digest._TRUNCATIONS == ["digest pass 1"]
    assert digest._guard_truncation("digest pass 2", _Resp("end_turn")) is False
    assert digest._guard_truncation("x", object()) is False  # missing attr
    assert digest._TRUNCATIONS == ["digest pass 1"]


def test_truncation_reaches_ops_footer(harness, monkeypatch):
    # A pass that hit its max_tokens cap must surface in the FULL send's ops
    # footer — and stale entries from a prior run are cleared at main() start.
    calls, _marker = harness
    monkeypatch.setattr(digest, "TEAM_RECIPIENTS", [])
    monkeypatch.setattr(digest, "TEAM_ACTIVATION_DATE", None)
    digest._TRUNCATIONS.append("stale pass from prior run")

    stub = digest.summarize_with_claude  # the harness stub

    def truncating(**kw):
        digest._TRUNCATIONS.append("digest pass 2")
        return stub(**kw)
    monkeypatch.setattr(digest, "summarize_with_claude", truncating)

    digest.main()
    sends = [c for c in calls if c[0] == "send"]
    assert len(sends) == 1                       # no separate ⚙️ email
    assert "Output truncated" in sends[0][3]
    assert "digest pass 2" in sends[0][3]
    assert "stale pass" not in sends[0][3]


def test_orphan_notices_no_longer_surfaced(harness, monkeypatch):
    # 2026-07-28 (new-operator call): departures are handled in person — the
    # orphan mechanism still pauses the alerts by construction, but digest.main
    # neither calls orphan_notices nor emails about it.
    calls, _marker = harness
    monkeypatch.setattr(digest, "TEAM_RECIPIENTS", [])
    monkeypatch.setattr(digest, "TEAM_ACTIVATION_DATE", None)
    called = []
    monkeypatch.setattr(
        digest.alert_commands, "orphan_notices",
        lambda recipients, today=None: called.append(recipients) or
        ["7 alert(s) owned by ghost@acorninv.com are paused."])

    digest.main()
    assert called == []                          # never invoked
    sends = [c for c in calls if c[0] == "send"]
    assert len(sends) == 1
    assert "Paused alerts" not in sends[0][3]


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


def test_o3_counts_use_raw_pacer_signal(harness, monkeypatch):
    # O3 re-point (2026-07-28): the monitor watches the pre-filter Ch.11
    # feed-hit count — the filtered pacer_entries is legitimately 0 most days
    # since the freshness filter and false-alarmed the zero-streak rule.
    calls, _marker = harness
    monkeypatch.setattr(digest, "TEAM_RECIPIENTS", [])
    monkeypatch.setattr(digest, "TEAM_ACTIVATION_DATE", None)
    monkeypatch.setattr(digest._pacer_mod, "_raw_ch11_count", 17)
    monkeypatch.setattr(digest._pacer_mod, "_court_item_counts",
                        {"deb": 554, "txsb": 0})

    digest.main()
    counts = next(c[1] for c in calls if c[0] == "o3")
    assert "pacer_entries" not in counts
    assert counts["pacer_raw_ch11"] == 17
    # per-court feed-health keys (the txsb lesson) ride along
    assert counts["pacer_rss_deb"] == 554
    assert counts["pacer_rss_txsb"] == 0


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
