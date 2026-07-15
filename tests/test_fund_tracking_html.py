"""Stage 2.2 — build_funds_html escaping (the builder the Phase-1.2 pass missed).

13F issuer names come from external EDGAR XML and routinely contain '&'
("AT&T INC"); interpolating them raw produced invalid entities in the email."""

import fund_tracking


def _result(name="AT&T INC", fund="Elliott & Co <LP>", url="https://sec.example/x"):
    return [{
        "fund": fund, "cik": "0000000001", "filing_date": "2026-07-01",
        "filing_url": url, "total_value": 1_000_000, "position_count": 2,
        "changes": {
            "new": [{"name": name, "cusip": "c1", "value": 500, "shares": 10}],
            "exited": [], "increased": [], "decreased": [],
        },
    }]


def test_issuer_and_fund_names_escaped():
    html = fund_tracking.build_funds_html(_result())
    assert "AT&amp;T INC" in html
    assert "Elliott &amp; Co &lt;LP&gt;" in html
    assert "<LP>" not in html


def test_hostile_href_neutralized():
    html = fund_tracking.build_funds_html(_result(url="javascript:alert(1)"))
    assert 'href="#"' in html
    assert "javascript:" not in html


def test_normal_names_render_unchanged():
    html = fund_tracking.build_funds_html(_result(name="Acme Corp", fund="Baupost Group",
                                                  url="https://www.sec.gov/x"))
    assert "Acme Corp: 10 shares" in html
    assert "Baupost Group" in html
    assert 'href="https://www.sec.gov/x"' in html
