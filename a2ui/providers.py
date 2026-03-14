"""A2UI LLM providers -- generate A2UI v0.9 messages from natural language.

Three providers:
  EchoA2UIProvider   -- canned response for testing (no API key)
  ClaudeA2UIProvider -- Anthropic SDK
  GeminiA2UIProvider -- Google GenAI SDK

All return list[dict] of v0.9 messages ready for bridge validation + adapter conversion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

import orjson


# ──────────────────────────────────────────────────────────────────
# Protocol + result
# ──────────────────────────────────────────────────────────────────


@runtime_checkable
class A2UIProvider(Protocol):
    def generate(self, system: str, user: str) -> A2UIResult: ...


@dataclass
class A2UIResult:
    """Result from an A2UI provider call."""
    messages: list[dict[str, Any]]
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""


# ──────────────────────────────────────────────────────────────────
# Echo provider (testing)
# ──────────────────────────────────────────────────────────────────


_CATALOG_ID = "https://a2ui.org/specification/v0_9/basic_catalog.json"

# Shared pattern: content inside markdown code fences (with or without lang tag)
_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)

# Pattern: "Generate an A2UI v0.9 surface for: <surface_name>"
_SURFACE_RE = re.compile(r"surface for:\s*(\S+)", re.IGNORECASE)


def _echo_build_messages(surface_id: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    """Build A2UI messages that display the actual data for a surface."""
    # Build component tree from the data keys
    children = ["title", "divider"]
    components: list[dict[str, Any]] = [
        {"id": "title", "component": "Text", "text": {"path": "/title"}, "variant": "h2"},
        {"id": "divider", "component": "Divider"},
    ]

    # Render each top-level key as a label + value row
    for i, key in enumerate(data):
        if key in ("title",):
            continue
        row_id = f"row-{i}"
        label_id = f"label-{i}"
        val_id = f"val-{i}"
        children.extend([row_id])
        components.extend([
            {
                "id": row_id,
                "component": "Row",
                "children": [label_id, val_id],
                "align": "center",
                "justify": "spaceBetween",
            },
            {"id": label_id, "component": "Text", "text": key, "variant": "caption"},
            {"id": val_id, "component": "Text", "text": {"path": f"/{key}"}, "variant": "body"},
        ])

    components.insert(0, {
        "id": "main-col",
        "component": "Column",
        "children": children,
        "align": "stretch",
        "gap": 8,
    })
    components.insert(0, {"id": "root", "component": "Card", "child": "main-col"})

    # Flatten nested dicts/lists to strings for display
    display_data: dict[str, Any] = {}
    for k, v in data.items():
        if isinstance(v, (dict, list)):
            display_data[k] = orjson.dumps(v).decode()
        elif v is None:
            display_data[k] = ""
        else:
            display_data[k] = v

    if "title" not in display_data:
        display_data["title"] = surface_id.replace("_", " ").replace("-", " ").title()

    return [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": surface_id,
                "catalogId": _CATALOG_ID,
                "sendDataModel": True,
            },
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": surface_id,
                "components": components,
            },
        },
        {
            "version": "v0.9",
            "updateDataModel": {
                "surfaceId": surface_id,
                "value": display_data,
            },
        },
    ]


class EchoA2UIProvider:
    """Builds A2UI surfaces from the actual data without an LLM call.

    Parses the user prompt to extract the surface name and data block,
    then generates a component tree that displays each data field.
    """

    def generate(self, system: str, user: str) -> A2UIResult:
        # Extract surface name from user prompt
        surface_match = _SURFACE_RE.search(user)
        surface_id = surface_match.group(1) if surface_match else "echo-surface"

        # Extract data from the ```json``` block in the user prompt
        data: dict[str, Any] = {}
        data_match = _FENCE_RE.search(user)
        if data_match:
            try:
                parsed = orjson.loads(data_match.group(1))
                if isinstance(parsed, dict):
                    data = parsed
            except Exception:
                pass

        if not data:
            data = {"info": "(no data provided)", "provider": "echo"}

        messages = _echo_build_messages(surface_id, data)
        return A2UIResult(messages=messages, model="echo")


# ──────────────────────────────────────────────────────────────────
# Claude provider
# ──────────────────────────────────────────────────────────────────


class ClaudeA2UIProvider:
    """Generates A2UI messages using Claude via the Anthropic SDK."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        try:
            import anthropic  # type: ignore[import-untyped]
        except ImportError:
            raise ImportError(
                "Anthropic SDK not installed. Run: uv add anthropic"
            ) from None
        self._client = anthropic.Anthropic()
        self._model = model

    def generate(self, system: str, user: str) -> A2UIResult:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=8192,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        raw = response.content[0].text
        messages = _extract_json_messages(raw)
        return A2UIResult(
            messages=messages,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
        )


# ──────────────────────────────────────────────────────────────────
# Gemini provider
# ──────────────────────────────────────────────────────────────────


class GeminiA2UIProvider:
    """Generates A2UI messages using Gemini via the Google GenAI SDK."""

    def __init__(self, model: str = "gemini-2.5-flash"):
        try:
            from google import genai  # type: ignore[import-untyped]
        except ImportError:
            raise ImportError(
                "Google GenAI SDK not installed. Run: uv add google-genai"
            ) from None
        self._client = genai.Client()
        self._model = model

    def generate(self, system: str, user: str) -> A2UIResult:
        from google.genai import types  # type: ignore[import-untyped]

        response = self._client.models.generate_content(
            model=self._model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=8192,
                response_mime_type="application/json",
            ),
        )
        raw = response.text
        messages = _extract_json_messages(raw)
        input_tokens = 0
        output_tokens = 0
        if response.usage_metadata:
            input_tokens = response.usage_metadata.prompt_token_count or 0
            output_tokens = response.usage_metadata.candidates_token_count or 0
        return A2UIResult(
            messages=messages,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self._model,
        )


# ──────────────────────────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────────────────────────


def get_a2ui_provider(name: str, model: str | None = None) -> A2UIProvider:
    """Create an A2UI provider by name."""
    if name == "echo":
        return EchoA2UIProvider()
    elif name == "claude":
        return ClaudeA2UIProvider(model=model or "claude-sonnet-4-6")
    elif name == "gemini":
        return GeminiA2UIProvider(model=model or "gemini-2.5-flash")
    else:
        raise ValueError(f"Unknown A2UI provider: {name!r}. Use 'echo', 'claude', or 'gemini'.")


# ──────────────────────────────────────────────────────────────────
# JSON extraction from LLM output
# ──────────────────────────────────────────────────────────────────


def _extract_json_messages(raw: str) -> list[dict[str, Any]]:
    """Parse A2UI messages from LLM output, stripping markdown fences if present."""
    text = raw.strip()

    # Try stripping markdown code fences
    match = _FENCE_RE.search(text)
    if match:
        text = match.group(1).strip()

    parsed = orjson.loads(text)

    # LLM might return a single message or a list
    if isinstance(parsed, dict):
        # Could be a wrapper: {"messages": [...]}
        if "messages" in parsed and isinstance(parsed["messages"], list):
            return parsed["messages"]
        return [parsed]
    if isinstance(parsed, list):
        return parsed

    raise ValueError(f"Expected list or dict from LLM, got {type(parsed).__name__}")
