#!/usr/bin/env python3
"""
Cross-Digest Memory — story-timeline store (Stage 5)

System A restructured (MEMORY_REFACTOR_SPEC Stage 5): memory.json is a
queryable story-timeline store, updated INCREMENTALLY after each digest.
The model returns only a DELTA — which tracked stories today's digest
advances (plus any genuinely new ones) — and code applies it: appends dated
timeline entries, refreshes summaries, resolves concluded stories. The old
wholesale-rewrite resent the entire memory every day and let the model
silently drop or reshape stories; now a story can only change through an
explicit delta, and staleness aging is deterministic code, not model whim.

Compatibility contract (Stage-5 hard constraints):
- The old v1 format ({active_stories, resolved_stories}) stays readable —
  migrated in memory on load; the v1 file is backed up once before the first
  v2 save (memory_v1_backup.json, gitignored).
- get_memory_context() renders the digest-prompt block in the SAME format as
  before (topic / since / summary / data points / sources), so the digest's
  load-bearing prompt sees no change.
- update_memory(digest_html) keeps its signature; digest.main is untouched.

match_stories() is the Stage-5 reply-bot router hook: a reply question is
matched against tracked storylines, whose entities + lifespan window drive
targeted (Stage-3a-filtered) retrieval and whose timelines join the answer
context as the narrative spine.
"""

import datetime
import json
import re
from pathlib import Path

import anthropic

from config import SONNET_MODEL
from claude_utils import parse_json_response, json_schema_output
from html_utils import strip_html
import cost

SCRIPT_DIR = Path(__file__).parent
MEMORY_FILE = SCRIPT_DIR / "memory.json"
V1_BACKUP_FILE = SCRIPT_DIR / "memory_v1_backup.json"
MEMORY_VERSION = 2

# Memory runs on Sonnet 4.6 (not Opus): the 2026-07-01 cost A/B found Sonnet's
# memory output near-identical to Opus at ~40% of the cost; the accrual-week
# watch closed healthy 2026-07-09 (Sonnet stays). Swap back to OPUS_MODEL if
# quality ever drifts.
CLAUDE_MODEL = SONNET_MODEL

# Active stories not advanced in this many days are resolved by CODE (was a
# prompt instruction under the v1 wholesale rewrite — model-enforced and lossy).
STALE_DAYS = 30

# --- Structured-output schema (A2): the incremental delta ---
# story_updates reference existing stories by id; new_stories create them.
# Nullable fields mean "leave unchanged".
_STORY_UPDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "update": {"type": "string"},
        "sources": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": ["string", "null"]},
        "key_data_points": {"type": ["array", "null"], "items": {"type": "string"}},
        "status": {"type": ["string", "null"]},
        "entities": {"type": ["array", "null"], "items": {"type": "string"}},
    },
    "required": ["id", "update", "sources", "summary", "key_data_points",
                 "status", "entities"],
    "additionalProperties": False,
}
_NEW_STORY_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "topic": {"type": "string"},
        "summary": {"type": "string"},
        "update": {"type": "string"},
        "key_data_points": {"type": "array", "items": {"type": "string"}},
        "sources": {"type": "array", "items": {"type": "string"}},
        "entities": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["id", "topic", "summary", "update", "key_data_points",
                 "sources", "entities"],
    "additionalProperties": False,
}
DELTA_SCHEMA = {
    "type": "object",
    "properties": {
        "story_updates": {"type": "array", "items": _STORY_UPDATE_SCHEMA},
        "new_stories": {"type": "array", "items": _NEW_STORY_SCHEMA},
    },
    "required": ["story_updates", "new_stories"],
    "additionalProperties": False,
}


# ======================================================================
# LOAD / SAVE / MIGRATION
# ======================================================================

def _slugify(topic):
    """'Wynn Resorts / Moody's downgrade' -> 'wynn-resorts-moodys-downgrade'."""
    slug = re.sub(r'[^a-z0-9]+', '-', (topic or "").lower()).strip("-")
    return slug[:60] or "story"


def _tag_entities(*texts):
    """Entity tags for story text via the shared index lexicon (Stage 3a/4).

    Lazy import: memory.py stays importable without search's dependencies.
    """
    from search import extract_entities
    return extract_entities(" ".join(t for t in texts if t))


def _migrate_v1(memory):
    """Convert a v1 memory dict to the v2 story-timeline shape (in memory).

    Each v1 story becomes a v2 story whose timeline is seeded with one entry
    carrying the v1 summary (dated at the story's last_updated), so nothing
    is lost and get_memory_context renders identically to before.
    """
    stories = []
    seen_ids = set()
    for status, key in (("active", "active_stories"), ("resolved", "resolved_stories")):
        for s in memory.get(key) or []:
            topic = s.get("topic", "")
            story_id = _slugify(topic)
            while story_id in seen_ids:
                story_id += "-2"
            seen_ids.add(story_id)
            last = s.get("last_updated") or s.get("first_seen") or ""
            try:
                entities = _tag_entities(topic, s.get("summary", ""))
            except Exception:
                entities = []
            stories.append({
                "id": story_id,
                "topic": topic,
                "status": status,
                "first_seen": s.get("first_seen", ""),
                "last_updated": last,
                "entities": entities,
                "summary": s.get("summary", ""),
                "key_data_points": s.get("key_data_points") or [],
                "sources": s.get("sources") or [],
                "timeline": [{
                    "date": last,
                    "update": s.get("summary", ""),
                    "sources": s.get("sources") or [],
                }],
            })
    return {
        "version": MEMORY_VERSION,
        "last_updated": memory.get("last_updated"),
        "stories": stories,
    }


def _load_memory():
    """Load memory as v2, migrating a v1 file in memory (no write on load)."""
    raw = None
    if MEMORY_FILE.exists():
        try:
            raw = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            raw = None
    if raw is None:
        return {"version": MEMORY_VERSION, "last_updated": None, "stories": []}
    if raw.get("version") == MEMORY_VERSION:
        return raw
    return _migrate_v1(raw)


def _save_memory(memory):
    """Save v2 memory; back up the on-disk v1 file once before first overwrite."""
    if MEMORY_FILE.exists() and not V1_BACKUP_FILE.exists():
        try:
            existing = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
            if existing.get("version") != MEMORY_VERSION:
                V1_BACKUP_FILE.write_text(
                    json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                print(f"  Backed up v1 memory to {V1_BACKUP_FILE.name}")
        except Exception:
            pass
    MEMORY_FILE.write_text(json.dumps(memory, indent=2, ensure_ascii=False), encoding="utf-8")


# ======================================================================
# DIGEST-PROMPT CONTEXT (contract-preserving)
# ======================================================================

def get_memory_context():
    """Return the current memory as a string for the digest prompt.

    Renders the SAME per-story block as the v1 version (topic / tracking
    since / summary / data points / sources) — the digest prompt sees no
    format change from Stage 5. Timelines are for the reply router, not here.
    """
    memory = _load_memory()
    active = [s for s in memory.get("stories", []) if s.get("status") == "active"]
    if not active:
        return ""

    lines = [
        "CROSS-DIGEST MEMORY — Stories you've been tracking across previous digests:",
        f"Last updated: {memory.get('last_updated', 'never')}",
        "",
    ]

    for story in active:
        lines.append(f"• {story['topic']} (tracking since {story.get('first_seen', '?')})")
        lines.append(f"  Summary: {story.get('summary', '')}")
        for dp in story.get("key_data_points") or []:
            lines.append(f"    - {dp}")
        if story.get("sources"):
            lines.append(f"  Sources: {', '.join(story['sources'])}")
        lines.append("")

    lines.append(
        "Reference prior context where relevant. Note how today's information "
        "updates or changes previous analysis. When citing data from memory, "
        "attribute it to the ORIGINAL source (e.g. Grant's, Bloomberg), not to "
        "this memory system."
    )

    return "\n".join(lines)


# ======================================================================
# INCREMENTAL UPDATE (the Stage-5 rewrite of update_memory)
# ======================================================================

def _story_index_for_prompt(memory):
    """Compact index the model updates against — id/status/dates/topic/summary
    per active story, plus resolved topics so they aren't recreated as new."""
    lines = ["STORY INDEX (active — update these by id):"]
    resolved = []
    for s in memory.get("stories", []):
        if s.get("status") == "active":
            summary = (s.get("summary") or "").replace("\n", " ")[:200]
            lines.append(f"  {s['id']} | last updated {s.get('last_updated', '?')} | "
                         f"{s.get('topic', '')} :: {summary}")
        else:
            resolved.append(f"  {s['id']} — {s.get('topic', '')}")
    if resolved:
        lines.append("\nRESOLVED STORIES (do NOT recreate these as new):")
        lines.extend(resolved)
    return "\n".join(lines)


def _apply_delta(memory, delta, today):
    """Apply a model delta to the store. Returns (updated, created, resolved).

    Only explicit deltas change stories: updates append a dated timeline
    entry (and optionally refresh summary/data points/status/entities); new
    stories are created with a seeded timeline. Unknown update ids are
    skipped loudly rather than guessed.
    """
    by_id = {s["id"]: s for s in memory.get("stories", [])}
    n_updated = n_created = n_resolved = 0

    for upd in delta.get("story_updates") or []:
        story = by_id.get(upd.get("id", "")) or by_id.get(upd.get("id", "").lower())
        if story is None:
            print(f"  Memory delta: unknown story id '{upd.get('id')}' — skipped.")
            continue
        sources = [s for s in (upd.get("sources") or []) if s]
        story["timeline"].append({
            "date": today,
            "update": upd.get("update", ""),
            "sources": sources,
        })
        story["last_updated"] = today
        if upd.get("summary"):
            story["summary"] = upd["summary"]
        if upd.get("key_data_points"):
            story["key_data_points"] = upd["key_data_points"][:5]
        if sources:
            story["sources"] = sorted(set(story.get("sources") or []) | set(sources))[:8]
        if upd.get("entities"):
            story["entities"] = sorted(set(story.get("entities") or [])
                                       | set(upd["entities"]))
        if upd.get("status") == "resolved" and story["status"] == "active":
            story["status"] = "resolved"
            n_resolved += 1
        n_updated += 1

    for new in delta.get("new_stories") or []:
        story_id = _slugify(new.get("id") or new.get("topic", ""))
        while story_id in by_id:
            story_id += "-2"
        try:
            auto_entities = _tag_entities(new.get("topic", ""), new.get("summary", ""))
        except Exception:
            auto_entities = []
        story = {
            "id": story_id,
            "topic": new.get("topic", ""),
            "status": "active",
            "first_seen": today,
            "last_updated": today,
            "entities": sorted(set(new.get("entities") or []) | set(auto_entities)),
            "summary": new.get("summary", ""),
            "key_data_points": (new.get("key_data_points") or [])[:5],
            "sources": (new.get("sources") or [])[:8],
            "timeline": [{
                "date": today,
                "update": new.get("update") or new.get("summary", ""),
                "sources": new.get("sources") or [],
            }],
        }
        memory["stories"].append(story)
        by_id[story_id] = story
        n_created += 1

    return n_updated, n_created, n_resolved


def _age_stale_stories(memory, today, stale_days=STALE_DAYS):
    """Resolve active stories not advanced in `stale_days` (code-enforced;
    was a v1 prompt instruction the model applied lossily). Returns count."""
    try:
        today_d = datetime.date.fromisoformat(today)
    except ValueError:
        return 0
    aged = 0
    for story in memory.get("stories", []):
        if story.get("status") != "active":
            continue
        try:
            last = datetime.date.fromisoformat(story.get("last_updated", ""))
        except ValueError:
            continue
        if (today_d - last).days > stale_days:
            story["status"] = "resolved"
            aged += 1
    if aged:
        print(f"  Memory: aged {aged} stale story(ies) to resolved (> {stale_days}d).")
    return aged


def update_memory(digest_html):
    """Incrementally update the story store from today's digest (Sonnet delta).

    Sends the model today's digest (HTML stripped — same content, ~fewer
    tokens) plus the compact story index; receives only the delta. Failure
    at any point keeps the existing memory untouched, exactly as before.
    """
    print("  Updating cross-digest memory (incremental)...")

    memory = _load_memory()
    client = anthropic.Anthropic()

    digest_text = strip_html(digest_html)
    today = str(datetime.date.today())

    prompt = (
        "Below is today's daily research digest (plain text), followed by a compact "
        "index of the investment storylines already being tracked.\n\n"
        "YOUR TASK: return ONLY the incremental changes to the story memory as JSON.\n"
        "- story_updates: one entry per EXISTING story that today's digest materially "
        "advances. \"id\" must be an exact id from the index. \"update\" = 1-3 specific "
        "sentences on today's development (numbers, names, dates). \"sources\" = the real "
        "publications/agencies behind it. Set \"summary\" / \"key_data_points\" (max 5) "
        "only if the story's rolling summary is now wrong or stale, else null. Set "
        "\"status\" to \"resolved\" only if the story concluded today, else null. "
        "\"entities\" = ticker symbols if obvious, else null.\n"
        "- new_stories: storylines genuinely new today (not in the index and not in the "
        "resolved list). Give a short-kebab-slug id, topic, 2-3 sentence summary, "
        "today's update, up to 5 key_data_points, sources, and entities (may be []).\n"
        "- Do NOT include stories the digest doesn't advance. Do NOT re-emit unchanged "
        "stories. Both arrays may be empty.\n\n"
        f"{_story_index_for_prompt(memory)}\n\n"
        f"TODAY'S DIGEST:\n{'=' * 40}\n{digest_text}\n{'=' * 40}\n"
    )

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=8000,
            system=(
                "You are a research memory manager maintaining evolving investment "
                "storylines. Output only valid JSON matching the requested delta shape. "
                "Be concise and specific — updates are 1-3 sentences with real numbers."
            ),
            output_config=json_schema_output(DELTA_SCHEMA),
            messages=[{"role": "user", "content": prompt}],
        )

        if response.stop_reason != "end_turn":
            print(f"  Memory update truncated (stop_reason={response.stop_reason}). "
                  "Keeping existing memory.")
            return memory

        delta = parse_json_response(response.content[0].text)
        n_updated, n_created, n_resolved = _apply_delta(memory, delta, today)
        _age_stale_stories(memory, today)
        memory["last_updated"] = today
        _save_memory(memory)

        n_active = sum(1 for s in memory["stories"] if s["status"] == "active")
        print(f"  Memory delta applied: {n_updated} updated, {n_created} new, "
              f"{n_resolved} resolved -> {n_active} active stories.")

        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        print(f"  Memory pass tokens: {tokens_in:,} in + {tokens_out:,} out")
        cost.record("memory update", CLAUDE_MODEL, response.usage)

        return memory

    except json.JSONDecodeError as e:
        print(f"  Memory update failed (invalid JSON): {e}")
        return memory
    except Exception as e:
        print(f"  Memory update failed: {e}")
        return memory


# ======================================================================
# REPLY-BOT ROUTER (Stage 5: System A -> System B)
# ======================================================================

_STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "what", "when", "how",
    "did", "does", "was", "were", "are", "has", "have", "had", "its", "their",
    "into", "over", "about", "after", "before", "between", "story", "stories",
    "week", "evolve", "evolved", "develop", "developed", "latest", "update",
    "updates", "news", "happening", "happened",
}


def _topic_words(story):
    """Distinctive-ish words (>=4 chars, stopworded) from a story's topic."""
    words = set(re.findall(r'[a-z0-9]+', story.get("topic", "").lower()))
    return {w for w in words if len(w) >= 4} - _STOPWORDS


def match_stories(question, top_n=2):
    """Match a reply question to tracked storylines (Stage-5 router).

    Scoring, strongest first:
    - entity hits (story entity found in the question, via the shared lexicon
      or as a literal word) count 2x;
    - UNIQUE topic words — words appearing in exactly one story's topic across
      the whole store (e.g. "wynn": rating headlines spell "Wynn Resorts", so
      the story carries no WYNN entity tag, yet the word identifies the story
      unambiguously) — count 1.5x and pass the threshold alone;
    - shared topic words ("credit", "downgrade") count 1x and need >=2.
    No match returns [] and the reply path behaves exactly as Stage 4.
    """
    memory = _load_memory()
    stories = memory.get("stories", [])
    if not stories or not question:
        return []

    q_lower = question.lower()
    q_words = set(re.findall(r'[a-z0-9]+', q_lower)) - _STOPWORDS
    try:
        q_entities = {e.lower() for e in _tag_entities(question)}
    except Exception:
        q_entities = set()

    # Document frequency of topic words across the store: df == 1 means the
    # word pins exactly one story, so it can match on its own.
    df = {}
    for story in stories:
        for w in _topic_words(story):
            df[w] = df.get(w, 0) + 1

    scored = []
    for story in stories:
        s_entities = {e.lower() for e in story.get("entities") or []}

        ent_hits = len(q_entities & s_entities)
        for ent in s_entities - q_entities:
            # Literal mention of the story's entity (or a multi-word entity's
            # distinctive first word, e.g. "oaktree") in the question text.
            probe = ent.split()[0] if " " in ent else ent
            if len(probe) >= 3 and re.search(rf'\b{re.escape(probe)}\b', q_lower):
                ent_hits += 1

        hits = q_words & _topic_words(story)
        unique_hits = sum(1 for w in hits if df.get(w) == 1)
        common_hits = len(hits) - unique_hits

        if ent_hits >= 1 or unique_hits >= 1 or common_hits >= 2:
            scored.append((2.0 * ent_hits + 1.5 * unique_hits + common_hits, story))

    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored[:top_n]]


if __name__ == "__main__":
    memory = _load_memory()
    n_active = sum(1 for s in memory.get("stories", []) if s.get("status") == "active")
    n_resolved = len(memory.get("stories", [])) - n_active
    print(f"Memory v{memory.get('version', 1)}: {n_active} active, {n_resolved} resolved "
          f"(last updated {memory.get('last_updated')})")
    print("\n--- Prompt context ---")
    print(get_memory_context() or "(empty)")
