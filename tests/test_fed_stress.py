"""Fed discount-window stress signal — numeric check + rendering.

`check_fed_stress` is now the source of truth for the discount-window level
alert (the stale LLM `alerts_config.json` rule was removed); digest.main merges
its output into the same red alert box. These pin the threshold logic and that
the merged signals render.
"""

import fed_balance_sheet as fbs
from alerts import build_alerts_html


def _dw(value_mm, wow=None):
    """One Discount Window row in the shape fetch_fed_balance_sheet() returns."""
    return [{"label": "Discount Window", "value_mm": value_mm, "wow_change": wow}]


# --- check_fed_stress threshold logic ---

def test_no_signal_at_baseline():
    # ~$8B primary-credit baseline with a small WoW move — not stress
    assert fbs.check_fed_stress(_dw(8000, wow=200)) == []


def test_absolute_level_signal():
    sig = fbs.check_fed_stress(_dw(30000, wow=0))  # $30B > $25B threshold
    assert len(sig) == 1
    assert "Discount window at" in sig[0]


def test_surge_signal():
    # $20B is under the $25B absolute bar, but +$15B WoW clears the $10B surge bar
    sig = fbs.check_fed_stress(_dw(20000, wow=15000))
    assert len(sig) == 1
    assert "surged" in sig[0]


def test_both_signals_fire():
    sig = fbs.check_fed_stress(_dw(30000, wow=15000))  # over both thresholds
    assert len(sig) == 2


def test_wow_none_no_surge():
    assert fbs.check_fed_stress(_dw(8000, wow=None)) == []


def test_ignores_non_discount_window_rows():
    # Total Assets is huge and swings WoW, but must never trip this check
    rows = [{"label": "Total Assets", "value_mm": 6_740_000, "wow_change": 999_999}]
    assert fbs.check_fed_stress(rows) == []


# --- merge into the alert box (the digest.main wiring, in miniature) ---

def test_signals_render_in_alert_box():
    signals = fbs.check_fed_stress(_dw(30000, wow=15000))
    triggered = [
        {"name": "Fed stress signal", "detail": s, "source": "FRED H.4.1"}
        for s in signals
    ]
    html = build_alerts_html(triggered)
    assert "Fed stress signal" in html
    assert "FRED H.4.1" in html
    assert "ALERTS" in html  # the red alert-box header


def test_no_box_when_silent():
    signals = fbs.check_fed_stress(_dw(8000, wow=200))
    html = build_alerts_html(
        [{"name": "Fed stress signal", "detail": s, "source": "FRED H.4.1"} for s in signals]
    )
    # no red box — only the standalone reply-channel hint line renders
    assert "ALERTS" not in html and "<div" not in html
    assert "manage your alerts" in html
