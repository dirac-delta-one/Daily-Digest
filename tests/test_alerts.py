"""Alert-evaluation prompt building — the watchlist binding (2026-07-21).

`_build_alert_prompt` is exercised directly (no Claude call) so the binding of the
trigger word "watchlist" to the real sec_filings.WATCHLIST is unit-tested for free.
"""

import alerts


_CFG = [
    {"name": "Rating downgrade",
     "trigger": "Any downgrade of a watchlist company or a fallen angel",
     "priority": "high"},
    {"name": "Bank failure", "trigger": "Any FDIC bank failure", "priority": "high"},
]


def test_alert_prompt_injects_watchlist_when_provided():
    p = alerts._build_alert_prompt(_CFG, "some source text", watchlist=["ARCC", "MSTR", "CRWV"])
    assert "WATCHLIST DEFINITION" in p
    assert "ARCC, MSTR, CRWV" in p          # exact ticker list, comma-joined
    # triggers + source still present
    assert "Rating downgrade" in p and "Bank failure" in p
    assert "some source text" in p


def test_alert_prompt_omits_watchlist_clause_when_none():
    p = alerts._build_alert_prompt(_CFG, "src")            # legacy path, no list
    assert "WATCHLIST DEFINITION" not in p
    assert "Rating downgrade" in p                          # rest of the prompt intact


def test_alert_prompt_omits_watchlist_clause_when_empty():
    p = alerts._build_alert_prompt(_CFG, "src", watchlist=[])
    assert "WATCHLIST DEFINITION" not in p


# --- evaluate_owner_alerts (Part II: batched union + per-owner fan-out) ---

def test_owner_eval_dedupes_identical_alerts(monkeypatch):
    seen = {}

    def fake_eval(source, watchlist=None, alerts=None):
        seen["units"] = alerts
        return [{"name": alerts[0]["name"], "triggered": True,
                 "detail": "d", "source": "s"}]

    monkeypatch.setattr(alerts, "evaluate_alerts", fake_eval)
    shared = {"name": "Bank failure", "trigger": "Any FDIC bank failure",
              "priority": "high"}
    out = alerts.evaluate_owner_alerts(
        "SRC", {"jared@x.com": [dict(shared)], "ava@x.com": [dict(shared)]})
    assert len(seen["units"]) == 1  # identical (name, trigger) -> ONE eval unit
    assert [r["name"] for r in out["jared@x.com"]] == ["Bank failure"]
    assert [r["name"] for r in out["ava@x.com"]] == ["Bank failure"]


def test_owner_eval_disambiguates_name_collisions(monkeypatch):
    captured = {}

    def fake_eval(source, watchlist=None, alerts=None):
        captured["names"] = [a["name"] for a in alerts]
        # trigger only the SECOND unit — fan-out must hit only owner b
        return [{"name": alerts[1]["name"], "triggered": True,
                 "detail": "d", "source": "s"}]

    monkeypatch.setattr(alerts, "evaluate_alerts", fake_eval)
    out = alerts.evaluate_owner_alerts("SRC", {
        "a@x.com": [{"name": "Bank failure", "trigger": "trigger A"}],
        "b@x.com": [{"name": "Bank failure", "trigger": "trigger B"}],
    })
    assert captured["names"] == ["Bank failure", "Bank failure ~2"]
    assert out["a@x.com"] == []
    assert [r["name"] for r in out["b@x.com"]] == ["Bank failure"]  # real name back


def test_owner_eval_empty_union_makes_no_call(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("evaluate_alerts must not be called")

    monkeypatch.setattr(alerts, "evaluate_alerts", boom)
    assert alerts.evaluate_owner_alerts("SRC", {"a@x.com": [], "b@x.com": None}) == {
        "a@x.com": [], "b@x.com": []}
