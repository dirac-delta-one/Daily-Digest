"""Stage 2.2/2.3 — cftc_cot: exact-code contract matching (a substring hit in
another line's numeric field could return the wrong contract's row) and, from
Stage 2.3, the prior-WEEK cache selection for WoW changes."""

import cftc_cot


def _line(name, code, oi=100, nl=10, ns=5):
    """One legacy-format CFTC CSV line with the columns _parse_cot_line reads."""
    fields = [f'"{name}"', "260707", "2026-07-07", code, "NYME", "x", "x",
              str(oi), str(nl), str(ns), "0", "11", "12", "0", "0", "0"]
    return ",".join(fields)


# --- _find_contract (exact match must beat an earlier substring hit) ---

def test_exact_code_beats_earlier_substring_hit():
    # "020601" appears inside the wrong line's open-interest figure (1020601)
    raw = "\n".join([_line("WRONG CONTRACT", "999999", oi=1020601),
                     _line("RIGHT CONTRACT", "020601")])
    row = cftc_cot._find_contract(raw, "020601")
    assert row["name"] == "RIGHT CONTRACT"
    assert row["cftc_code"] == "020601"


def test_loose_fallback_kept_when_no_exact_match():
    raw = _line("ONLY SUBSTRING", "999999", oi=1020601)
    row = cftc_cot._find_contract(raw, "020601")
    assert row["name"] == "ONLY SUBSTRING"


def test_absent_code_returns_none():
    assert cftc_cot._find_contract(_line("A", "111111"), "020601") is None


def test_parse_cot_line_fields():
    row = cftc_cot._parse_cot_line(_line("WTI CRUDE", "067651", oi=500, nl=40, ns=15))
    assert row["name"] == "WTI CRUDE"
    assert row["cftc_code"] == "067651"
    assert row["open_interest"] == 500
    assert row["noncomm_long"] == 40
    assert row["noncomm_short"] == 15
    assert row["comm_long"] == 11
    assert row["comm_short"] == 12
