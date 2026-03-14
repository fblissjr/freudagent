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


_ECHO_MESSAGES: list[dict[str, Any]] = [
    {
        "version": "v0.9",
        "createSurface": {
            "surfaceId": "echo-surface",
            "catalogId": "https://a2ui.org/specification/v0_9/basic_catalog.json",
            "sendDataModel": True,
        },
    },
    {
        "version": "v0.9",
        "updateComponents": {
            "surfaceId": "echo-surface",
            "components": [
                {"id": "root", "component": "Card", "child": "main-col"},
                {
                    "id": "main-col",
                    "component": "Column",
                    "children": ["title", "divider", "prompt-text"],
                    "align": "stretch",
                    "gap": 12,
                },
                {"id": "title", "component": "Text", "text": "Echo Surface", "variant": "h2"},
                {"id": "divider", "component": "Divider"},
                {
                    "id": "prompt-text",
                    "component": "Text",
                    "text": {"path": "/prompt"},
                    "variant": "body",
                },
            ],
        },
    },
    {
        "version": "v0.9",
        "updateDataModel": {
            "surfaceId": "echo-surface",
            "value": {
                "prompt": "(echo provider -- no LLM call)",
                "provider": "echo",
            },
        },
    },
]


class EchoA2UIProvider:
    """Returns canned A2UI messages for testing. No API key needed."""

    def generate(self, system: str, user: str) -> A2UIResult:
        # Include the user prompt in the data model so it's visible
        messages = orjson.loads(orjson.dumps(_ECHO_MESSAGES))
        messages[2]["updateDataModel"]["value"]["prompt"] = user
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


_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)


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
