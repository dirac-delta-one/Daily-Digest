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
