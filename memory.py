#!/usr/bin/env python3
"""
Cross-Digest Memory
Maintains a running context file that tracks evolving stories across days.
After each digest, Opus updates memory.json with new/evolving/resolved storylines.
"""

import json
import datetime
from pathlib import Path

import anthropic

from config import OPUS_MODEL
from claude_utils import parse_json_response, json_schema_output
import cost

SCRIPT_DIR = Path(__file__).parent
MEMORY_FILE = SCRIPT_DIR / "memory.json"
CLAUDE_MODEL = OPUS_MODEL

# Structured-output schema (A2) — guarantees a well-formed memory object so a parse
# failure can't silently wipe the running memory. Top-level object, no wrapping.
_STORY_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string"},
        "first_seen": {"type": "string"},
        "last_updated": {"type": "string"},
        "summary": {"type": "string"},
        "key_data_points": {"type": "array", "items": {"type": "string"}},
        "sources": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["topic", "first_seen", "last_updated", "summary", "key_data_points", "sources"],
    "additionalProperties": False,
}
MEMORY_SCHEMA = {
    "type": "object",
    "properties": {
        "last_updated": {"type": "string"},
        "active_stories": {"type": "array", "items": _STORY_SCHEMA},
        "resolved_stories": {"type": "array", "items": _STORY_SCHEMA},
    },
    "required": ["last_updated", "active_stories", "resolved_stories"],
    "additionalProperties": False,
}


def _load_memory():
    """Load the current memory file."""
    if MEMORY_FILE.exists():
        try:
            return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "last_updated": None,
        "active_stories": [],
        "resolved_stories": [],
    }


def _save_memory(memory):
    """Save the updated memory file."""
    MEMORY_FILE.write_text(json.dumps(memory, indent=2, ensure_ascii=False), encoding="utf-8")


def get_memory_context():
    """Return the current memory as a string for the Opus prompt."""
    memory = _load_memory()

    if not memory.get("active_stories"):
        return ""

    lines = [
        "CROSS-DIGEST MEMORY — Stories you've been tracking across previous digests:",
        f"Last updated: {memory.get('last_updated', 'never')}",
        "",
    ]

    for story in memory["active_stories"]:
        lines.append(f"• {story['topic']} (tracking since {story.get('first_seen', '?')})")
        lines.append(f"  Summary: {story.get('summary', '')}")
        if story.get("key_data_points"):
            for dp in story["key_data_points"]:
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


def update_memory(digest_html):
    """Make an Opus call to update memory.json based on today's digest."""
    print("  Updating cross-digest memory...")

    memory = _load_memory()
    client = anthropic.Anthropic()

    prompt = (
        "Below is today's daily research digest, followed by the current memory file "
        "that tracks evolving stories across days.\n\n"
        "YOUR TASK: Update the memory file.\n"
        "- Add new storylines that emerged today.\n"
        "- Update existing storylines with new developments.\n"
        "- Move storylines to 'resolved_stories' if they concluded.\n"
        "- Keep only the last 30 days of active storylines (remove stale ones).\n"
        "- Each story needs: topic, first_seen, last_updated, summary, key_data_points (list), sources (list).\n"
        "- Keep summaries concise (2-3 sentences max). Keep key_data_points to the 5 most important per story.\n"
        "- Output ONLY valid JSON matching the schema below. No markdown, no explanation.\n\n"
        "SCHEMA:\n"
        '{"last_updated": "YYYY-MM-DD", "active_stories": [...], "resolved_stories": [...]}\n\n'
        "Each story: {\"topic\": str, \"first_seen\": \"YYYY-MM-DD\", "
        "\"last_updated\": \"YYYY-MM-DD\", \"summary\": str, "
        "\"key_data_points\": [str], \"sources\": [str]}\n\n"
        f"TODAY'S DIGEST:\n{'='*40}\n{digest_html}\n{'='*40}\n\n"
        f"CURRENT MEMORY:\n{'='*40}\n{json.dumps(memory, indent=2)}\n{'='*40}\n"
    )

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=16000,
            system=(
                "You are a research memory manager. Your job is to maintain a running "
                "memory of evolving investment stories and themes. Output only valid JSON. "
                "Be concise — summaries should be 2-3 sentences, key_data_points capped at 5 per story."
            ),
            output_config=json_schema_output(MEMORY_SCHEMA),
            messages=[{"role": "user", "content": prompt}],
        )

        # Check if output was truncated
        if response.stop_reason != "end_turn":
            print(f"  Memory update truncated (stop_reason={response.stop_reason}). Keeping existing memory.")
            return memory

        updated = parse_json_response(response.content[0].text)

        # Validate basic structure
        if "active_stories" not in updated:
            updated["active_stories"] = []
        if "resolved_stories" not in updated:
            updated["resolved_stories"] = []
        updated["last_updated"] = str(datetime.date.today())

        _save_memory(updated)

        n_active = len(updated["active_stories"])
        n_resolved = len(updated["resolved_stories"])
        print(f"  Memory updated: {n_active} active stories, {n_resolved} resolved.")

        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        print(f"  Memory pass tokens: {tokens_in:,} in + {tokens_out:,} out")
        cost.record("memory update", CLAUDE_MODEL, response.usage)

        return updated

    except json.JSONDecodeError as e:
        print(f"  Memory update failed (invalid JSON): {e}")
        return memory
    except Exception as e:
        print(f"  Memory update failed: {e}")
        return memory


if __name__ == "__main__":
    memory = _load_memory()
    print(json.dumps(memory, indent=2))
    print("\n--- Prompt context ---")
    print(get_memory_context() or "(empty)")
