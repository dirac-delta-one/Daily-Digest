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
        return (f"<div>DIGEST{label}</div>", f"SRC{label}")
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
                      marker.exists())))
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
    monkeypatch.setattr(digest, "TEAM_RECIPIENTS", [])

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
