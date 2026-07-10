"""Phase 3.4 — pin behavior of pacer's pure parsers."""

import pacer


# --- _extract_case_info ---

def test_extract_case_info_basic():
    cn, debtor = pacer._extract_case_info("26-10710-mew JOANN Inc.", "", "")
    assert cn == "26-10710"
    # trailing punctuation is intentionally stripped (.strip(" -–—:.")), so "Inc." -> "Inc"
    assert debtor == "JOANN Inc"


def test_extract_case_info_no_judge_suffix():
    cn, debtor = pacer._extract_case_info("24-12345 Acme Corp", "", "")
    assert cn == "24-12345"
    assert debtor == "Acme Corp"


def test_extract_case_info_strips_joint_admin():
    cn, debtor = pacer._extract_case_info(
        "26-10710-abc Foo Holdings Jointly Administered under 26-10700", "", ""
    )
    assert cn == "26-10710"
    assert debtor == "Foo Holdings"


def test_extract_case_info_no_case_number():
    cn, debtor = pacer._extract_case_info("Some Title Without Number", "", "")
    assert cn == ""
    assert debtor == "Some Title Without Number"


def test_extract_case_info_falls_back_to_description():
    cn, debtor = pacer._extract_case_info("26-10710-mew", "Debtor: Widget Co", "")
    assert cn == "26-10710"
    assert "Widget Co" in debtor


# --- _is_corporate_entity ---

def test_is_corporate_entity_true_for_suffixes():
    assert pacer._is_corporate_entity("JOANN Inc.") is True
    assert pacer._is_corporate_entity("Acme Holdings LLC") is True
    assert pacer._is_corporate_entity("Big Capital Partners") is True


def test_is_corporate_entity_false_for_person():
    assert pacer._is_corporate_entity("John Smith") is False
    assert pacer._is_corporate_entity("John A. Smith") is False


def test_is_corporate_entity_false_for_unknown_or_empty():
    assert pacer._is_corporate_entity("(unknown debtor)") is False
    assert pacer._is_corporate_entity("") is False


def test_is_corporate_entity_dba_and_long_names():
    assert pacer._is_corporate_entity("Joe's Diner d/b/a JD Eats") is True
    assert pacer._is_corporate_entity("Alpha Beta Gamma Delta") is True  # 4+ words


# --- _is_chapter_11_filing ---

def test_is_chapter_11_filing_true():
    assert pacer._is_chapter_11_filing("Notice", "Chapter: 11 voluntary petition filed") is True


def test_is_chapter_11_filing_false_not_ch11():
    assert pacer._is_chapter_11_filing("Notice", "Chapter: 7 petition") is False


def test_is_chapter_11_filing_false_no_new_case_signal():
    assert pacer._is_chapter_11_filing("Notice", "Chapter: 11 motion to compel discovery") is False


# --- F1a-4: seen-state stash/commit (persist only after a successful send) ---

import json  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture
def seen_file(tmp_path, monkeypatch):
    monkeypatch.setattr(pacer, "SEEN_FILE", tmp_path / "pacer_seen.json")
    monkeypatch.setattr(pacer, "_pending_seen", None)
    return tmp_path / "pacer_seen.json"


def test_stash_not_persisted_until_commit(seen_file):
    pacer._stash_seen({"discovery": {"deb": ["entry1"]}, "tracking": {}})
    assert not seen_file.exists()  # a crash here loses nothing from the next digest
    # in-process readers (the tracking phase after discovery) see the pending state
    assert pacer._load_seen()["discovery"] == {"deb": ["entry1"]}

    pacer.commit_seen()
    on_disk = json.loads(seen_file.read_text(encoding="utf-8"))
    assert on_disk["discovery"] == {"deb": ["entry1"]}
    assert pacer._pending_seen is None  # cleared after commit


def test_commit_noop_when_nothing_pending(seen_file):
    pacer.commit_seen()
    assert not seen_file.exists()


def test_pending_overrides_disk(seen_file):
    seen_file.write_text(json.dumps({"discovery": {"deb": ["old"]}, "tracking": {}}),
                         encoding="utf-8")
    pacer._stash_seen({"discovery": {"deb": ["old", "new"]}, "tracking": {}})
    assert pacer._load_seen()["discovery"]["deb"] == ["old", "new"]
    pacer.commit_seen()
    assert json.loads(seen_file.read_text(encoding="utf-8"))["discovery"]["deb"] == ["old", "new"]


# --- Stage 2.3: ordered seen-state eviction (list(set)[-N:] was order-random) ---

def test_ordered_seen_dedupes_preserving_order():
    assert pacer._ordered_seen(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]
    assert pacer._ordered_seen([]) == []


@pytest.fixture
def mock_discovery(monkeypatch, seen_file):
    """One court, mocked RSS, size filter pass-through (NO Sonnet), no sleeps."""
    monkeypatch.setattr(pacer, "MONITORED_COURTS", ["deb"])
    monkeypatch.setattr(pacer, "_fetch_court_rss", lambda court: "TREE")
    monkeypatch.setattr(pacer, "_filter_by_size", lambda filings: filings)
    monkeypatch.setattr(pacer.time, "sleep", lambda s: None)

    def set_items(items):
        monkeypatch.setattr(pacer, "_parse_items", lambda tree: items)
    return set_items


def test_discovery_seen_ids_suppress(mock_discovery):
    ch11 = {"title": "26-10710 Acme Corp LLC", "link": "link-new",
            "description": "Chapter: 11 voluntary petition", "pub_date": ""}
    already = {"title": "26-10001 Old Corp LLC", "link": "link-old",
               "description": "Chapter: 11 voluntary petition", "pub_date": ""}
    pacer._stash_seen({"discovery": {"deb": ["link-old"]}, "tracking": {}})
    mock_discovery([already, ch11])

    found = pacer.discover_new_filings()
    assert [f["link"] for f in found] == ["link-new"]  # seen id suppressed


def test_discovery_eviction_drops_oldest_first(mock_discovery):
    # Pre-seed 990 ordered ids; 30 new feed entries push the court over the
    # 1000 cap -> exactly the 20 OLDEST pre-seeded ids must be evicted.
    pacer._stash_seen({"discovery": {"deb": [f"old{i:04d}" for i in range(990)]},
                       "tracking": {}})
    mock_discovery([{"title": f"t{i}", "link": f"new{i:02d}",
                     "description": "routine motion", "pub_date": ""}
                    for i in range(30)])

    pacer.discover_new_filings()
    seen = pacer._load_seen()["discovery"]["deb"]
    assert len(seen) == 1000
    assert seen[0] == "old0020"                       # oldest survivors first
    assert "old0019" not in seen and "old0000" not in seen
    assert seen[-30:] == [f"new{i:02d}" for i in range(30)]  # newest all retained
