"""Tests for bridge.py -- A2UI structural validation."""

import pytest


# ------------------------------------------------------------------
# Valid messages
# ------------------------------------------------------------------


def test_valid_minimal_surface(bridge):
    msgs = [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": "test",
                "catalogId": "https://a2ui.org/specification/v0_9/basic_catalog.json",
            },
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "test",
                "components": [
                    {"id": "root", "component": "Text", "text": "hello"},
                ],
            },
        },
    ]
    errors = bridge.validate(msgs)
    assert errors == []


def test_valid_card_with_children(bridge):
    msgs = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "test", "catalogId": "basic"},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "test",
                "components": [
                    {"id": "root", "component": "Card", "child": "col"},
                    {
                        "id": "col",
                        "component": "Column",
                        "children": ["t1", "t2"],
                    },
                    {"id": "t1", "component": "Text", "text": "one"},
                    {"id": "t2", "component": "Text", "text": "two"},
                ],
            },
        },
    ]
    errors = bridge.validate(msgs)
    assert errors == []


def test_valid_data_model_update(bridge):
    msgs = [
        {
            "version": "v0.9",
            "updateDataModel": {
                "surfaceId": "test",
                "path": "/user/name",
                "value": "Alice",
            },
        },
    ]
    errors = bridge.validate(msgs)
    assert errors == []


# ------------------------------------------------------------------
# Invalid messages
# ------------------------------------------------------------------


def test_empty_list_rejected(bridge):
    errors = bridge.validate([])
    assert len(errors) == 1
    assert "empty" in errors[0]


def test_not_a_list_rejected(bridge):
    errors = bridge.validate("not a list")
    assert len(errors) == 1


def test_wrong_version(bridge):
    msgs = [
        {
            "version": "v0.8",
            "createSurface": {"surfaceId": "test"},
        },
    ]
    errors = bridge.validate(msgs)
    assert any("v0.9" in e for e in errors)


def test_missing_message_type(bridge):
    msgs = [{"version": "v0.9", "bogus": {}}]
    errors = bridge.validate(msgs)
    assert any("no valid message type" in e for e in errors)


def test_missing_surface_id(bridge):
    msgs = [
        {
            "version": "v0.9",
            "createSurface": {},
        },
    ]
    errors = bridge.validate(msgs)
    assert any("surfaceId" in e for e in errors)


def test_missing_root_component(bridge):
    msgs = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "test",
                "components": [
                    {"id": "not-root", "component": "Text", "text": "hi"},
                ],
            },
        },
    ]
    errors = bridge.validate(msgs)
    assert any("root" in e for e in errors)


def test_duplicate_component_id(bridge):
    msgs = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "test",
                "components": [
                    {"id": "root", "component": "Text", "text": "a"},
                    {"id": "root", "component": "Text", "text": "b"},
                ],
            },
        },
    ]
    errors = bridge.validate(msgs)
    assert any("duplicate" in e for e in errors)


def test_dangling_child_reference(bridge):
    msgs = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "test",
                "components": [
                    {"id": "root", "component": "Card", "child": "missing"},
                ],
            },
        },
    ]
    errors = bridge.validate(msgs)
    assert any("non-existent" in e for e in errors)


def test_self_reference(bridge):
    msgs = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "test",
                "components": [
                    {"id": "root", "component": "Card", "child": "root"},
                ],
            },
        },
    ]
    errors = bridge.validate(msgs)
    assert any("itself" in e for e in errors)


def test_orphaned_component(bridge):
    msgs = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "test",
                "components": [
                    {"id": "root", "component": "Text", "text": "a"},
                    {"id": "orphan", "component": "Text", "text": "b"},
                ],
            },
        },
    ]
    errors = bridge.validate(msgs)
    assert any("orphan" in e for e in errors)


def test_invalid_json_pointer(bridge):
    msgs = [
        {
            "version": "v0.9",
            "updateDataModel": {
                "surfaceId": "test",
                "path": "no-leading-slash",
                "value": 42,
            },
        },
    ]
    errors = bridge.validate(msgs)
    assert any("JSON Pointer" in e for e in errors)


def test_circular_reference(bridge):
    msgs = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "test",
                "components": [
                    {"id": "root", "component": "Card", "child": "a"},
                    {"id": "a", "component": "Card", "child": "b"},
                    {"id": "b", "component": "Card", "child": "a"},
                ],
            },
        },
    ]
    errors = bridge.validate(msgs)
    assert any("circular" in e for e in errors)


# ------------------------------------------------------------------
# Validate-or-raise
# ------------------------------------------------------------------


def test_validate_or_raise_passes(bridge):
    msgs = [
        {
            "version": "v0.9",
            "createSurface": {"surfaceId": "test", "catalogId": "basic"},
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "test",
                "components": [
                    {"id": "root", "component": "Text", "text": "ok"},
                ],
            },
        },
    ]
    bridge.validate_or_raise(msgs)  # should not raise


def test_validate_or_raise_raises(bridge):
    from bridge import ValidationError

    with pytest.raises(ValidationError) as exc_info:
        bridge.validate_or_raise([])
    assert len(exc_info.value.errors) > 0
