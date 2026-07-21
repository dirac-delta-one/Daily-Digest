"""§7.2 observability — pin run_alert's log-tail + alert-HTML building.

Importing run_alert must not touch Gmail (auth is inside functions), so these
tests are pure/offline.
"""

import run_alert


# --- _tail ---

def test_tail_last_n_lines(tmp_path):
    log = tmp_path / "x.log"
    log.write_text("\n".join(f"line{i}" for i in range(100)), encoding="utf-8")
    out = run_alert._tail(log, n=5)
    assert out.splitlines() == ["line95", "line96", "line97", "line98", "line99"]


def test_tail_short_file(tmp_path):
    log = tmp_path / "x.log"
    log.write_text("only line", encoding="utf-8")
    assert run_alert._tail(log, n=40) == "only line"


def test_tail_missing_file(tmp_path):
    out = run_alert._tail(tmp_path / "nope.log")
    assert "could not read log" in out


# --- build_alert_html ---

def test_alert_html_contains_label_and_tail():
    html_out = run_alert.build_alert_html("digest", "Traceback: boom",
                                          when="2026-07-06 08:01:00", host="TESTBOX")
    assert "digest run FAILED" in html_out
    assert "Traceback: boom" in html_out
    assert "TESTBOX" in html_out
    assert "2026-07-06 08:01:00" in html_out


def test_alert_html_escapes_log_content():
    html_out = run_alert.build_alert_html("digest", 'x < y & "z" <script>')
    assert "<script>" not in html_out
    assert "&lt;script&gt;" in html_out
    assert "&amp;" in html_out


def test_alert_html_escapes_label():
    html_out = run_alert.build_alert_html("<b>weird</b>", "tail")
    assert "<b>weird</b>" not in html_out


# --- _find_log (O1 rotation-aware log lookup) ---

def _touch(path, mtime):
    import os
    path.write_text("x", encoding="utf-8")
    os.utime(path, (mtime, mtime))


def test_find_log_picks_newest_dated(tmp_path, monkeypatch):
    monkeypatch.setattr(run_alert, "SCRIPT_DIR", tmp_path)
    logs = tmp_path / "logs"
    logs.mkdir()
    _touch(logs / "digest_2026-07-09.log", 1_000)
    _touch(logs / "digest_2026-07-10.log", 2_000)
    _touch(logs / "digest.log", 500)  # legacy name, oldest
    assert run_alert._find_log("digest").name == "digest_2026-07-10.log"


def test_find_log_legacy_only(tmp_path, monkeypatch):
    monkeypatch.setattr(run_alert, "SCRIPT_DIR", tmp_path)
    logs = tmp_path / "logs"
    logs.mkdir()
    _touch(logs / "backup.log", 1_000)
    assert run_alert._find_log("backup").name == "backup.log"


def test_find_log_labels_do_not_cross_match(tmp_path, monkeypatch):
    monkeypatch.setattr(run_alert, "SCRIPT_DIR", tmp_path)
    logs = tmp_path / "logs"
    logs.mkdir()
    _touch(logs / "reply_monitor_2026-07-10.log", 2_000)
    _touch(logs / "digest_2026-07-10.log", 3_000)  # newer, different label
    assert run_alert._find_log("reply_monitor").name == "reply_monitor_2026-07-10.log"


def test_find_log_missing_dir_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(run_alert, "SCRIPT_DIR", tmp_path)
    # no logs/ at all -> fall back to the legacy path (tail prints placeholder)
    assert run_alert._find_log("digest") == tmp_path / "logs" / "digest.log"


# --- check_completed (O2 hung-run watchdog) ---

import datetime  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture
def watchdog_env(tmp_path, monkeypatch):
    """Isolated SCRIPT_DIR + captured _send_email (no Gmail)."""
    monkeypatch.setattr(run_alert, "SCRIPT_DIR", tmp_path)
    sent = []
    monkeypatch.setattr(run_alert, "_send_email",
                        lambda subject, body: sent.append((subject, body)))
    return tmp_path, sent


def _write_marker(tmp_path):
    day_dir = tmp_path / "archive" / datetime.date.today().isoformat()
    day_dir.mkdir(parents=True)
    (day_dir / "digest_sent_at.txt").write_text("2026-07-10T08:14:02", encoding="utf-8")


def test_watchdog_completed_no_alert(watchdog_env):
    tmp_path, sent = watchdog_env
    _write_marker(tmp_path)
    assert run_alert.check_completed("digest") == 0
    assert sent == []


def test_watchdog_missing_marker_alerts(watchdog_env):
    tmp_path, sent = watchdog_env
    assert run_alert.check_completed("digest") == 0  # alert sent successfully
    assert len(sent) == 1
    subject, body = sent[0]
    assert "MISSING" in subject
    assert "digest run MISSING" in body
    assert "hung" in body


def test_watchdog_test_flag_forces_drill_despite_marker(watchdog_env):
    tmp_path, sent = watchdog_env
    _write_marker(tmp_path)
    assert run_alert.check_completed("digest", test=True) == 0
    assert len(sent) == 1
    subject = sent[0][0]
    # The drill marker must PRECEDE the alarming words — clients truncate
    # subjects from the end, and a cut-off TEST tag reads as a real emergency.
    assert subject.index("(TEST drill)") < subject.index("MISSING")


def test_watchdog_real_alert_has_no_drill_marker(watchdog_env):
    tmp_path, sent = watchdog_env
    assert run_alert.check_completed("digest") == 0  # no marker -> real alert
    assert "(TEST drill)" not in sent[0][0]


def test_watchdog_send_failure_returns_1(tmp_path, monkeypatch):
    monkeypatch.setattr(run_alert, "SCRIPT_DIR", tmp_path)

    def _boom(subject, body):
        raise RuntimeError("token dead")
    monkeypatch.setattr(run_alert, "_send_email", _boom)
    assert run_alert.check_completed("digest") == 1


def test_watchdog_rejects_other_labels(watchdog_env):
    tmp_path, sent = watchdog_env
    assert run_alert.check_completed("reply_monitor") == 2
    assert sent == []


# --- build_alert_html custom headline/detail (watchdog variant) ---

def test_alert_html_custom_headline_detail():
    out = run_alert.build_alert_html("digest", "tail", headline="digest run MISSING",
                                     detail="No completed digest today.")
    assert "digest run MISSING" in out
    assert "No completed digest today." in out
    assert "exited nonzero" not in out


def test_alert_html_defaults_unchanged():
    out = run_alert.build_alert_html("digest", "tail")
    assert "digest run FAILED" in out
    assert "exited nonzero" in out
