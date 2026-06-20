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
