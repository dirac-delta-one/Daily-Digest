"""Stage 5 — pin the story-timeline memory store: v1 migration (incl. the
get_memory_context contract), delta application, code-enforced aging, and the
reply-bot router. All offline — no Claude calls, no real memory.json touched."""

import json

import pytest

import memory


V1_MEMORY = {
    "last_updated": "2026-07-09",
    "active_stories": [
        {
            "topic": "Wynn Resorts Moody's downgrade / Boston leverage",
            "first_seen": "2026-06-30",
            "last_updated": "2026-07-02",
            "summary": "Moody's cut Wynn's outlook on Boston leverage concerns.",
            "key_data_points": ["Outlook to negative", "Boston lease-adjusted leverage 7x"],
            "sources": ["Moody's", "FT"],
        },
        {
            "topic": "Strategy (MSTR) Bitcoin monetization",
            "first_seen": "2026-06-29",
            "last_updated": "2026-07-09",
            "summary": "Strategy began selling BTC under its new capital framework.",
            "key_data_points": ["3,588 BTC sold", "$8.32B digital-asset loss"],
            "sources": ["Bloomberg", "WSJ"],
        },
    ],
    "resolved_stories": [
        {
            "topic": "Hormuz escalation",
            "first_seen": "2026-06-30",
            "last_updated": "2026-07-07",
            "summary": "Strait tensions de-escalated after the ceasefire.",
            "key_data_points": [],
            "sources": ["FT"],
        },
    ],
}


@pytest.fixture
def mem_files(tmp_path, monkeypatch):
    """Point memory at throwaway files; write the v1 fixture by default."""
    mem_file = tmp_path / "memory.json"
    backup_file = tmp_path / "memory_v1_backup.json"
    monkeypatch.setattr(memory, "MEMORY_FILE", mem_file)
    monkeypatch.setattr(memory, "V1_BACKUP_FILE", backup_file)
    mem_file.write_text(json.dumps(V1_MEMORY), encoding="utf-8")
    return mem_file, backup_file


# --- migration ---

def test_migrate_v1_shape(mem_files):
    m = memory._load_memory()
    assert m["version"] == 2
    assert len(m["stories"]) == 3
    wynn = m["stories"][0]
    assert wynn["status"] == "active"
    assert wynn["id"] == "wynn-resorts-moody-s-downgrade-boston-leverage"
    # timeline seeded with the v1 summary at the story's last_updated
    assert wynn["timeline"] == [{
        "date": "2026-07-02",
        "update": "Moody's cut Wynn's outlook on Boston leverage concerns.",
        "sources": ["Moody's", "FT"],
    }]
    # entity auto-tagging picks up MSTR on the second story (watchlist ticker)
    assert "MSTR" in m["stories"][1]["entities"]
    assert m["stories"][2]["status"] == "resolved"


def test_migration_does_not_write_on_load(mem_files):
    mem_file, _ = mem_files
    before = mem_file.read_text(encoding="utf-8")
    memory._load_memory()
    assert mem_file.read_text(encoding="utf-8") == before  # read-only load


def test_v2_roundtrip_loads_as_is(mem_files):
    m = memory._load_memory()
    memory._save_memory(m)
    assert memory._load_memory() == m


def test_save_backs_up_v1_once(mem_files):
    mem_file, backup_file = mem_files
    memory._save_memory(memory._load_memory())
    assert backup_file.exists()
    assert json.loads(backup_file.read_text(encoding="utf-8")) == V1_MEMORY
    # second save must not overwrite the backup with v2 content
    memory._save_memory(memory._load_memory())
    assert json.loads(backup_file.read_text(encoding="utf-8")) == V1_MEMORY


def test_load_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "MEMORY_FILE", tmp_path / "nope.json")
    m = memory._load_memory()
    assert m == {"version": 2, "last_updated": None, "stories": []}


# --- get_memory_context: the digest-prompt contract must not change shape ---

def test_context_format_matches_v1_contract(mem_files):
    ctx = memory.get_memory_context()
    assert ctx.startswith(
        "CROSS-DIGEST MEMORY — Stories you've been tracking across previous digests:"
    )
    assert "Last updated: 2026-07-09" in ctx
    assert "• Wynn Resorts Moody's downgrade / Boston leverage (tracking since 2026-06-30)" in ctx
    assert "  Summary: Moody's cut Wynn's outlook on Boston leverage concerns." in ctx
    assert "    - Outlook to negative" in ctx
    assert "  Sources: Moody's, FT" in ctx
    # resolved stories are NOT rendered
    assert "Hormuz" not in ctx
    # the attribution footer survives
    assert "attribute it to the ORIGINAL source" in ctx


def test_context_empty_when_no_active(tmp_path, monkeypatch):
    mem_file = tmp_path / "memory.json"
    monkeypatch.setattr(memory, "MEMORY_FILE", mem_file)
    mem_file.write_text(json.dumps({"version": 2, "last_updated": "x", "stories": [
        {"id": "a", "topic": "t", "status": "resolved", "first_seen": "", "last_updated": "",
         "entities": [], "summary": "", "key_data_points": [], "sources": [], "timeline": []},
    ]}), encoding="utf-8")
    assert memory.get_memory_context() == ""


# --- _apply_delta ---

def test_delta_update_appends_timeline(mem_files):
    m = memory._load_memory()
    delta = {"story_updates": [{
        "id": m["stories"][0]["id"],
        "update": "Fitch followed Moody's with its own negative outlook.",
        "sources": ["Fitch"],
        "summary": None, "key_data_points": None, "status": None, "entities": None,
    }], "new_stories": []}
    n_upd, n_new, n_res = memory._apply_delta(m, delta, "2026-07-10")
    assert (n_upd, n_new, n_res) == (1, 0, 0)
    wynn = m["stories"][0]
    assert len(wynn["timeline"]) == 2
    assert wynn["timeline"][-1]["date"] == "2026-07-10"
    assert wynn["last_updated"] == "2026-07-10"
    # null summary/dps mean "unchanged"
    assert wynn["summary"] == "Moody's cut Wynn's outlook on Boston leverage concerns."
    assert "Fitch" in wynn["sources"]  # sources union


def test_delta_resolve_and_refresh(mem_files):
    m = memory._load_memory()
    delta = {"story_updates": [{
        "id": m["stories"][1]["id"],
        "update": "Buyback program completed; monetization wound down.",
        "sources": ["Bloomberg"],
        "summary": "New summary.", "key_data_points": ["dp1"],
        "status": "resolved", "entities": ["STRC"],
    }], "new_stories": []}
    n_upd, n_new, n_res = memory._apply_delta(m, delta, "2026-07-10")
    assert (n_upd, n_res) == (1, 1)
    mstr = m["stories"][1]
    assert mstr["status"] == "resolved"
    assert mstr["summary"] == "New summary."
    assert mstr["key_data_points"] == ["dp1"]
    assert "STRC" in mstr["entities"] and "MSTR" in mstr["entities"]


def test_delta_unknown_id_skipped(mem_files):
    m = memory._load_memory()
    before = json.dumps(m)
    delta = {"story_updates": [{
        "id": "no-such-story", "update": "x", "sources": [],
        "summary": None, "key_data_points": None, "status": None, "entities": None,
    }], "new_stories": []}
    n_upd, n_new, n_res = memory._apply_delta(m, delta, "2026-07-10")
    assert (n_upd, n_new, n_res) == (0, 0, 0)
    assert json.dumps(m) == before  # untouched


def test_delta_new_story_created_with_slug_collision(mem_files):
    m = memory._load_memory()
    existing_id = m["stories"][0]["id"]
    delta = {"story_updates": [], "new_stories": [{
        "id": existing_id,  # collides -> must get a suffix
        "topic": "Another Wynn thread", "summary": "S.", "update": "U.",
        "key_data_points": ["d"], "sources": ["FT"], "entities": [],
    }]}
    n_upd, n_new, _ = memory._apply_delta(m, delta, "2026-07-10")
    assert n_new == 1
    new = m["stories"][-1]
    assert new["id"] == existing_id + "-2"
    assert new["status"] == "active"
    assert new["first_seen"] == "2026-07-10"
    assert new["timeline"] == [{"date": "2026-07-10", "update": "U.", "sources": ["FT"]}]


# --- aging (code-enforced staleness) ---

def test_age_stale_stories(mem_files):
    m = memory._load_memory()
    # Wynn last updated 2026-07-02 and MSTR 2026-07-09 -> both stale on 2026-08-15
    aged = memory._age_stale_stories(m, "2026-08-15")
    assert aged == 2
    assert all(s["status"] == "resolved" for s in m["stories"])
    # nothing stale 11 days out
    assert memory._age_stale_stories(memory._load_memory(), "2026-07-20") == 0


def test_age_stale_boundaries(mem_files):
    m = memory._load_memory()
    # exactly 30 days is not stale; 31 is
    assert memory._age_stale_stories(m, "2026-08-01") == 0  # Wynn 7/02 -> 30d
    assert memory._age_stale_stories(m, "2026-08-02") == 1  # Wynn 7/02 -> 31d


# --- _slugify ---

def test_slugify():
    assert memory._slugify("Wynn Resorts / Moody's downgrade!") == "wynn-resorts-moody-s-downgrade"
    assert memory._slugify("") == "story"
    assert len(memory._slugify("x" * 200)) <= 60


# --- match_stories (Stage-5 router) ---

def test_match_stories_by_literal_entity_word(mem_files):
    # "Wynn" is NOT in the question-side lexicon (not watchlist/$TICK/fund),
    # but the story's WYNN entity matches as a literal word — the router's
    # whole point. Requires the story to carry the tag (migration tags via
    # lexicon only, so set it explicitly as a delta would).
    m = memory._load_memory()
    m["stories"][0]["entities"] = ["WYNN"]
    memory._save_memory(m)
    matched = memory.match_stories("How did the Wynn story develop across the week?")
    assert [s["id"] for s in matched] == [m["stories"][0]["id"]]


def test_match_stories_by_lexicon_entity(mem_files):
    matched = memory.match_stories("What is the latest on $MSTR?")
    assert any("mstr" in s["id"] or "MSTR" in s.get("entities", []) for s in matched)


def test_match_stories_by_topic_words(mem_files):
    matched = memory.match_stories("What happened with the Bitcoin monetization plan?")
    assert any(s["topic"].startswith("Strategy") for s in matched)


def test_match_stories_no_match(mem_files):
    assert memory.match_stories("What are Treasury auction tails doing?") == []


def test_match_stories_empty_question(mem_files):
    assert memory.match_stories("") == []


def test_match_stories_unique_topic_word_matches_alone(mem_files):
    # "wynn" appears in exactly one story topic (df=1), so it matches on its
    # own even though the migrated story carries no WYNN entity tag — the
    # real-data gap the df weighting exists for.
    matched = memory.match_stories("How did the Wynn situation develop?")
    assert len(matched) == 1
    assert matched[0]["topic"].startswith("Wynn Resorts")


# --- Context budget (CLEANUP_SPEC 3.2) + resolved ids-only index (3.1) ---

def _budget_story(i, last_updated, topic=None):
    return {"id": f"s{i}", "topic": topic or f"Story {i}", "status": "active",
            "first_seen": "2026-07-01", "last_updated": last_updated,
            "entities": [], "summary": f"Summary {i}.", "key_data_points": [],
            "sources": ["FT"], "timeline": []}


def _write_store(tmp_path, monkeypatch, stories):
    mem_file = tmp_path / "memory.json"
    monkeypatch.setattr(memory, "MEMORY_FILE", mem_file)
    mem_file.write_text(json.dumps(
        {"version": 2, "last_updated": "2026-07-14", "stories": stories}),
        encoding="utf-8")
    return mem_file


def test_context_under_budget_renders_all_in_store_order(tmp_path, monkeypatch):
    # store order 0,1,2 but recency order 1,2,0 — under budget, EVERY story
    # renders and the output keeps STORE order (byte-identity with the
    # pre-budget renderer; also the cross-variant cache determinism condition)
    _write_store(tmp_path, monkeypatch, [
        _budget_story(0, "2026-07-01"),
        _budget_story(1, "2026-07-14"),
        _budget_story(2, "2026-07-08"),
    ])
    ctx = memory.get_memory_context()
    assert ctx.find("Story 0") < ctx.find("Story 1") < ctx.find("Story 2")
    assert memory.get_memory_context() == ctx  # deterministic across calls


def test_context_story_budget_drops_stalest_first(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "MEMORY_CONTEXT_MAX_STORIES", 2)
    _write_store(tmp_path, monkeypatch, [
        _budget_story(0, "2026-07-01"),   # stalest -> dropped
        _budget_story(1, "2026-07-14"),
        _budget_story(2, "2026-07-08"),
    ])
    ctx = memory.get_memory_context()
    assert "Story 0" not in ctx
    assert "Story 1" in ctx and "Story 2" in ctx
    assert ctx.find("Story 1") < ctx.find("Story 2")  # survivors in store order
    # header/footer intact around the trimmed body
    assert ctx.startswith("CROSS-DIGEST MEMORY")
    assert "attribute it to the ORIGINAL source" in ctx


def test_context_char_budget_keeps_at_least_one(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "MEMORY_CONTEXT_MAX_CHARS", 10)  # absurdly small
    _write_store(tmp_path, monkeypatch, [
        _budget_story(0, "2026-07-01"),
        _budget_story(1, "2026-07-14"),
    ])
    ctx = memory.get_memory_context()
    assert "Story 1" in ctx      # the most recent always survives
    assert "Story 0" not in ctx


def test_context_size_log_line(tmp_path, monkeypatch, capsys):
    _write_store(tmp_path, monkeypatch, [_budget_story(0, "2026-07-14")])
    memory.get_memory_context()
    out = capsys.readouterr().out
    assert "Memory context:" in out and "1 of 1 active stories" in out


def test_story_index_resolved_ids_only(mem_files):
    # CLEANUP_SPEC 3.1: the resolved tail sends ids (topic slugs), not topics
    m = memory._load_memory()
    text = memory._story_index_for_prompt(m)
    resolved_part = text.split("RESOLVED STORIES")[1]
    assert "hormuz-escalation" in resolved_part
    assert "Hormuz escalation" not in resolved_part
    # active stories keep their full index line
    assert "Wynn Resorts Moody's downgrade / Boston leverage ::" in text


# --- Substack store (TEAM_DIGEST_SPEC Stage 3) ---

def test_store_isolation(mem_files, tmp_path, monkeypatch):
    # Saving to the substack store must not touch the main one (or its backup)
    mem_file, backup_file = mem_files
    sub_file = tmp_path / "substack_memory.json"
    monkeypatch.setattr(memory, "SUBSTACK_MEMORY_FILE", sub_file)
    main_before = mem_file.read_text(encoding="utf-8")

    store = {"version": 2, "last_updated": "2026-07-13", "stories": [
        {"id": "petition-lme", "topic": "PETITION LME coverage", "status": "active",
         "first_seen": "2026-07-13", "last_updated": "2026-07-13", "entities": [],
         "summary": "S.", "key_data_points": [], "sources": ["PETITION"],
         "timeline": []},
    ]}
    memory._save_memory(store, sub_file)

    assert mem_file.read_text(encoding="utf-8") == main_before
    assert not backup_file.exists()  # v1 backup is a main-store-only behavior
    assert memory._load_memory(sub_file) == store


def test_substack_context_header_and_isolation(mem_files, tmp_path, monkeypatch):
    sub_file = tmp_path / "substack_memory.json"
    monkeypatch.setattr(memory, "SUBSTACK_MEMORY_FILE", sub_file)
    memory._save_memory({"version": 2, "last_updated": "2026-07-13", "stories": [
        {"id": "s1", "topic": "Data-center bond fragility", "status": "active",
         "first_seen": "2026-07-13", "last_updated": "2026-07-13", "entities": [],
         "summary": "Residual-value risk.", "key_data_points": ["dp"],
         "sources": ["Junk Bond Investor"], "timeline": []},
    ]}, sub_file)

    ctx = memory.get_substack_memory_context()
    assert ctx.startswith("TRACKED SUBSTACK STORYLINES")
    assert "Data-center bond fragility" in ctx
    assert "ORIGINAL publication" in ctx
    # the MAIN context is untouched by the substack store
    assert "Data-center bond fragility" not in memory.get_memory_context()


def test_substack_context_empty_store(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "SUBSTACK_MEMORY_FILE", tmp_path / "nope.json")
    assert memory.get_substack_memory_context() == ""


def test_match_stories_path_param(mem_files, tmp_path, monkeypatch):
    sub_file = tmp_path / "substack_memory.json"
    monkeypatch.setattr(memory, "SUBSTACK_MEMORY_FILE", sub_file)
    memory._save_memory({"version": 2, "last_updated": "2026-07-13", "stories": [
        {"id": "saaspocalypse", "topic": "SaaSpocalypse asset-light unwind",
         "status": "active", "first_seen": "2026-07-13",
         "last_updated": "2026-07-13", "entities": [], "summary": "",
         "key_data_points": [], "sources": ["High Yield Landlord"],
         "timeline": []},
    ]}, sub_file)
    q = "What is the latest on the SaaSpocalypse thesis?"
    assert memory.match_stories(q) == []  # not in the main store
    matched = memory.match_stories(q, path=sub_file)
    assert [s["id"] for s in matched] == ["saaspocalypse"]


def test_substack_articles_text_caps_body():
    articles = [{"title": "T", "author": "A", "text": "x" * 5000}]
    text = memory._substack_articles_text(articles)
    assert len(text) < 3200  # capped at SUBSTACK_ARTICLE_CAP + header
    assert text.startswith("--- T (A) ---")


def test_update_substack_memory_no_articles_makes_no_call(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "SUBSTACK_MEMORY_FILE", tmp_path / "sub.json")

    class _Boom:
        def __init__(self):
            raise AssertionError("no-articles path must not build a client")
    monkeypatch.setattr(memory.anthropic, "Anthropic", _Boom)

    result = memory.update_substack_memory([])
    assert result["stories"] == []
    assert not (tmp_path / "sub.json").exists()  # nothing written either


def test_match_stories_common_word_alone_no_match(tmp_path, monkeypatch):
    # A topic word shared by several stories (df>1) must NOT match alone.
    mem_file = tmp_path / "memory.json"
    monkeypatch.setattr(memory, "MEMORY_FILE", mem_file)
    stories = [
        {"id": f"s{i}", "topic": f"Private credit {name}", "status": "active",
         "first_seen": "2026-07-01", "last_updated": "2026-07-09", "entities": [],
         "summary": "", "key_data_points": [], "sources": [], "timeline": []}
        for i, name in enumerate(["fundraising", "redemptions"])
    ]
    mem_file.write_text(json.dumps(
        {"version": 2, "last_updated": "2026-07-09", "stories": stories}), encoding="utf-8")
    # "credit" alone (df=2) -> no match; adding a df=1 word -> match
    assert memory.match_stories("What about credit?") == []
    matched = memory.match_stories("What about credit redemptions?")
    assert [s["id"] for s in matched] == ["s1"]
