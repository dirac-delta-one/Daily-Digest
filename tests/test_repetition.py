"""Repetition metric (repetition.py, REDUCE_REPEATS Idea 12): scoring rules,
the strong/weak signal split, section include/exclude inventory, and the
persist-never-raise contract."""

import json

import pytest

import repetition


def _h2(title):
    return f'<h2 style="font-size: 18px;">{title}</h2>'


DIGEST = (
    # Headerless boxes (alerts/earnings) precede the first <h2> in the real
    # assembled layout — the splitter never assigns them to a section.
    '<div style="background: #fdf2f2;">headerless alerts box $ORCL</div>'
    + _h2("Corporate Credit Snapshot")            # excluded: pre-rendered
    + "<td>978 bps</td><td>$ORCL</td>"
    + _h2("Fund Position Changes (13F)")          # excluded: data table
    + "<td>$ORCL</td>"
    + _h2("1. Top Takeaways")
    + '<li><strong>$ORCL (Oracle):</strong> debt to $120bn, CDS wide (Stifel)</li>'
    + _h2("2. Market &amp; Macro")
    + '<li><strong>Credit:</strong> CCC at 978 bps, widening; CPI 2.5% (FRED)</li>'
    + _h2("3. Equity Ideas")
    + '<li><strong>$ORCL:</strong> another angle, CCC 978 bps; BTC up 2.5%</li>'
    + _h2("WSJ/FT Articles")                      # included: appended, reader-facing
    + "<li>Oracle debt hits $120bn milestone</li>"
)


def test_score_strong_and_weak_counted_separately():
    n_strong, n_weak, details = repetition.repetition_score(DIGEST)
    # STRONG dupes: $ORCL (§1+§3), 978 bps (§2+§3), $120bn (§1+WSJ)
    assert n_strong == 3
    assert details["$ORCL"] == ["1. Top Takeaways", "3. Equity Ideas"]
    assert details["$120bn"] == ["1. Top Takeaways", "WSJ/FT Articles"]
    # WEAK dupe: bare 2.5% in §2+§3 — counted, but marked weak
    assert n_weak == 1
    assert details["2.5% (weak)"] == ["2. Market &amp; Macro", "3. Equity Ideas"]


def test_percent_substring_not_matched():
    # "10.50%" must NOT also produce a bogus "50%" signal (2026-07-22 smoke
    # test artifact: Gray Media's 10.50% coupon collided with a 50% tariff).
    html = (_h2("1. A") + "<li>bought the 10.50% notes</li>"
            + _h2("2. B") + "<li>a 50% tariff threat</li>")
    n_strong, n_weak, details = repetition.repetition_score(html)
    assert n_strong == 0 and n_weak == 0 and details == {}


def test_excluded_sections_never_scored():
    secs = repetition.section_texts(DIGEST)
    assert "Corporate Credit Snapshot" not in secs
    assert "Fund Position Changes (13F)" not in secs
    assert "WSJ/FT Articles" in secs


def test_mandated_sections_excluded():
    # 2026-07-23 recalibration: SEC Filings / Rating Actions are content-
    # mandated listings — a ticker discussed analytically AND carrying a
    # filing is a structural collision, not editorial repetition. The
    # substring match must survive dynamic renumbering.
    html = (
        _h2("3. Equity Ideas") + "<li>$CRWV (CoreWeave): BofA Buy, $140 PT</li>"
        + _h2("8. Recent SEC Filings") + "<li>$CRWV: Form 4 insider sales</li>"
        + _h2("9. Rating Actions") + "<li>$CRWV downgraded; 978 bps wide</li>"
        + _h2("7. Rating Actions")  # renumbered variant also excluded
        + "<li>$CRWV again</li>"
    )
    n_strong, n_weak, details = repetition.repetition_score(html)
    assert n_strong == 0 and details == {}
    secs = repetition.section_texts(html)
    assert list(secs) == ["3. Equity Ideas"]


def test_no_dupes_scores_zero():
    html = _h2("1. Top Takeaways") + "<li>$AAA only here</li>" \
        + _h2("2. Market") + "<li>$BBB only here</li>"
    n_strong, n_weak, details = repetition.repetition_score(html)
    assert n_strong == 0 and n_weak == 0 and details == {}


def test_record_score_persists_and_never_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(repetition, "SCORES_PATH", tmp_path / "scores.json")
    n = repetition.record_score("full", DIGEST, today="2026-07-22")
    assert n == 3  # returns the strong count
    saved = json.loads((tmp_path / "scores.json").read_text(encoding="utf-8"))
    assert saved[0]["variant"] == "full"
    assert saved[0]["n_strong"] == 3
    assert saved[0]["n_weak"] == 1
    assert "$ORCL" in saved[0]["details"]
    # appends, not overwrites
    repetition.record_score("team", DIGEST, today="2026-07-22")
    saved = json.loads((tmp_path / "scores.json").read_text(encoding="utf-8"))
    assert len(saved) == 2


def test_log_score_never_persists(tmp_path, monkeypatch, capsys):
    # 2026-07-24: the weekly wrap is scored log-only — repetition_scores.json
    # is the DAILY digest's decision series and must stay weekly-free.
    monkeypatch.setattr(repetition, "SCORES_PATH", tmp_path / "scores.json")
    n = repetition.log_score("weekly (team)", DIGEST)
    assert n == 3
    assert not (tmp_path / "scores.json").exists()
    out = capsys.readouterr().out
    assert "weekly (team), log-only" in out
    # never-raise contract holds on garbage input
    assert repetition.log_score("weekly", None) == 0


@pytest.mark.parametrize("bad", [None, "", "<p>no h2 at all</p>"])
def test_score_handles_empty_input(bad):
    n_strong, n_weak, details = repetition.repetition_score(bad)
    assert n_strong == 0 and n_weak == 0
