"""Tests for providers.py -- A2UI LLM providers."""

import pytest
from bridge import A2UIBridge
from providers import (
    A2UIResult,
    EchoA2UIProvider,
    _extract_json_messages,
    get_a2ui_provider,
)


# ──────────────────────────────────────────────────────────────────
# Echo provider
# ──────────────────────────────────────────────────────────────────


def test_echo_provider_returns_valid_messages(bridge):
    provider = EchoA2UIProvider()
    result = provider.generate("system prompt", "show me a dashboard")
    assert isinstance(result, A2UIResult)
    assert result.model == "echo"
    assert len(result.messages) == 3

    errors = bridge.validate(result.messages)
    assert errors == [], f"Echo messages failed validation: {errors}"


def test_echo_provider_includes_user_prompt():
    provider = EchoA2UIProvider()
    result = provider.generate("sys", "my custom prompt")
    dm = result.messages[2]["updateDataModel"]["value"]
    assert dm["prompt"] == "my custom prompt"


def test_echo_provider_returns_independent_copies():
    """Each call should return independent copies, not shared references."""
    provider = EchoA2UIProvider()
    r1 = provider.generate("sys", "prompt 1")
    r2 = provider.generate("sys", "prompt 2")
    dm1 = r1.messages[2]["updateDataModel"]["value"]
    dm2 = r2.messages[2]["updateDataModel"]["value"]
    assert dm1["prompt"] == "prompt 1"
    assert dm2["prompt"] == "prompt 2"


# ──────────────────────────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────────────────────────


def test_get_provider_echo():
    provider = get_a2ui_provider("echo")
    assert isinstance(provider, EchoA2UIProvider)


def test_get_provider_unknown():
    with pytest.raises(ValueError, match="Unknown A2UI provider"):
        get_a2ui_provider("nonexistent")


# ──────────────────────────────────────────────────────────────────
# JSON extraction
# ──────────────────────────────────────────────────────────────────


def test_extract_json_plain_array():
    raw = '[{"version": "v0.9", "createSurface": {"surfaceId": "s"}}]'
    msgs = _extract_json_messages(raw)
    assert len(msgs) == 1
    assert msgs[0]["createSurface"]["surfaceId"] == "s"


def test_extract_json_with_fences():
    raw = """Here are the A2UI messages:

```json
[{"version": "v0.9", "createSurface": {"surfaceId": "s"}}]
```

That should work!"""
    msgs = _extract_json_messages(raw)
    assert len(msgs) == 1


def test_extract_json_single_message():
    raw = '{"version": "v0.9", "createSurface": {"surfaceId": "s"}}'
    msgs = _extract_json_messages(raw)
    assert len(msgs) == 1


def test_extract_json_wrapper_object():
    raw = '{"messages": [{"version": "v0.9", "createSurface": {"surfaceId": "s"}}]}'
    msgs = _extract_json_messages(raw)
    assert len(msgs) == 1


def test_extract_json_fences_without_lang():
    raw = """```
[{"version": "v0.9", "createSurface": {"surfaceId": "s"}}]
```"""
    msgs = _extract_json_messages(raw)
    assert len(msgs) == 1
