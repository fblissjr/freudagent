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
    result = provider.generate("system prompt", "Generate an A2UI v0.9 surface for: dashboard\n\n```json\n{\"total\": 5}\n```")
    assert isinstance(result, A2UIResult)
    assert result.model == "echo"
    assert len(result.messages) == 3

    errors = bridge.validate(result.messages)
    assert errors == [], f"Echo messages failed validation: {errors}"


def test_echo_provider_uses_surface_name_from_prompt():
    provider = EchoA2UIProvider()
    result = provider.generate("sys", "Generate an A2UI v0.9 surface for: my-dashboard\n\nData:\n```json\n{\"x\": 1}\n```")
    sid = result.messages[0]["createSurface"]["surfaceId"]
    assert sid == "my-dashboard"
    # All three messages use the same surfaceId
    assert result.messages[1]["updateComponents"]["surfaceId"] == "my-dashboard"
    assert result.messages[2]["updateDataModel"]["surfaceId"] == "my-dashboard"


def test_echo_provider_includes_actual_data():
    provider = EchoA2UIProvider()
    result = provider.generate("sys", 'Generate an A2UI v0.9 surface for: test\n\nData:\n```json\n{"name": "Alice", "count": 42}\n```')
    dm = result.messages[2]["updateDataModel"]["value"]
    assert dm["name"] == "Alice"
    assert dm["count"] == 42


def test_echo_provider_returns_independent_copies():
    """Each call should return independent copies, not shared references."""
    provider = EchoA2UIProvider()
    r1 = provider.generate("sys", 'Generate an A2UI v0.9 surface for: s1\n\nData:\n```json\n{"val": "one"}\n```')
    r2 = provider.generate("sys", 'Generate an A2UI v0.9 surface for: s2\n\nData:\n```json\n{"val": "two"}\n```')
    assert r1.messages[0]["createSurface"]["surfaceId"] == "s1"
    assert r2.messages[0]["createSurface"]["surfaceId"] == "s2"
    assert r1.messages[2]["updateDataModel"]["value"]["val"] == "one"
    assert r2.messages[2]["updateDataModel"]["value"]["val"] == "two"


def test_echo_provider_no_data_block():
    """When no data block is present, still produces valid messages."""
    provider = EchoA2UIProvider()
    result = provider.generate("sys", "just some text")
    assert len(result.messages) == 3
    from bridge import A2UIBridge
    errors = A2UIBridge().validate(result.messages)
    assert errors == []


def test_echo_provider_flattens_nested_data():
    """Nested dicts/lists are serialized to strings for display."""
    provider = EchoA2UIProvider()
    result = provider.generate("sys", 'Generate an A2UI v0.9 surface for: test\n\nData:\n```json\n{"nested": {"a": 1}, "items": [1, 2]}\n```')
    dm = result.messages[2]["updateDataModel"]["value"]
    # Nested values are JSON strings
    assert isinstance(dm["nested"], str)
    assert isinstance(dm["items"], str)


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
