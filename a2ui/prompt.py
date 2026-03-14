"""System prompt assembly for A2UI generation.

Loads and concatenates:
  1. SKILL.md      -- core A2UI authoring instructions
  2. component-catalog.md -- full component properties
  3. prompt_addendum.md   -- FreudAgent data shapes
  4. Few-shot examples    -- flight-status.json, booking-form.json
"""

from __future__ import annotations

import pathlib
from functools import lru_cache

import orjson

# Paths relative to the project root
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SKILL_DIR = _PROJECT_ROOT / "internal" / "a2ui-claude-bridge" / "skills" / "a2ui-authoring"
_ADDENDUM_PATH = pathlib.Path(__file__).resolve().parent / "prompt_addendum.md"


def _read_or_fallback(path: pathlib.Path, label: str) -> str:
    """Read a file, returning a placeholder if not found."""
    if path.exists():
        return path.read_text()
    return f"[{label} not found at {path}]"


@lru_cache(maxsize=1)
def build_system_prompt() -> str:
    """Assemble the full A2UI authoring system prompt."""
    parts: list[str] = []

    # 1. Core authoring skill
    skill_md = _read_or_fallback(_SKILL_DIR / "SKILL.md", "A2UI authoring skill")
    parts.append(skill_md)

    # 2. Component catalog
    catalog_md = _read_or_fallback(
        _SKILL_DIR / "references" / "component-catalog.md",
        "Component catalog",
    )
    parts.append(catalog_md)

    # 3. FreudAgent-specific addendum
    addendum = _read_or_fallback(_ADDENDUM_PATH, "FreudAgent data shapes")
    parts.append(addendum)

    # 4. Few-shot examples
    examples_dir = _SKILL_DIR / "examples"
    if examples_dir.exists():
        for example_path in sorted(examples_dir.glob("*.json")):
            try:
                data = orjson.loads(example_path.read_bytes())
                name = data.get("name", example_path.stem)
                messages_json = orjson.dumps(
                    data.get("messages", data),
                    option=orjson.OPT_INDENT_2,
                ).decode()
                parts.append(
                    f"## Example: {name}\n\n```json\n{messages_json}\n```"
                )
            except Exception:
                pass  # Skip malformed examples

    # 5. Output format instruction
    parts.append(
        "## Output Format\n\n"
        "Return ONLY a JSON array of A2UI v0.9 messages. "
        "No markdown fences, no explanation, just the JSON array. "
        "The array must contain exactly 3 messages in order: "
        "createSurface, updateComponents, updateDataModel."
    )

    return "\n\n---\n\n".join(parts)


def build_user_prompt(surface: str, data: dict, description: str | None = None) -> str:
    """Build the user prompt for A2UI generation.

    Args:
        surface: Surface type hint (e.g., "dashboard", "extraction_card").
        data: The data to visualize.
        description: Optional free-form description of the desired surface.
    """
    data_json = orjson.dumps(data, option=orjson.OPT_INDENT_2).decode()

    parts = [f"Generate an A2UI v0.9 surface for: {surface}"]
    if description:
        parts.append(f"Description: {description}")
    parts.append(f"Data:\n```json\n{data_json}\n```")

    return "\n\n".join(parts)
