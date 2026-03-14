"""Tests for adapter.py -- v0.9 to v0.8 message conversion."""

import orjson
import pytest
from adapter import adapt_v09_to_v08


# ──────────────────────────────────────────────────────────────────
# createSurface -> beginRendering
# ──────────────────────────────────────────────────────────────────


def test_create_surface_to_begin_rendering():
    v09 = [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": "test-surface",
                "catalogId": "https://a2ui.org/specification/v0_9/basic_catalog.json",
                "sendDataModel": True,
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    assert len(result) == 1
    msg = result[0]
    assert "beginRendering" in msg
    assert "version" not in msg
    assert msg["beginRendering"]["surfaceId"] == "test-surface"
    assert msg["beginRendering"]["root"] == "root"


def test_create_surface_strips_catalog_and_version():
    v09 = [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": "x",
                "catalogId": "some-catalog",
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    br = result[0]["beginRendering"]
    assert "catalogId" not in br
    assert "sendDataModel" not in br


# ──────────────────────────────────────────────────────────────────
# updateComponents -> surfaceUpdate
# ──────────────────────────────────────────────────────────────────


def test_text_component():
    v09 = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s1",
                "components": [
                    {"id": "root", "component": "Text", "text": "Hello", "variant": "h1"},
                ],
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    su = result[0]["surfaceUpdate"]
    assert su["surfaceId"] == "s1"
    comp = su["components"][0]
    assert comp["id"] == "root"
    assert comp["component"]["Text"]["text"] == {"literalString": "Hello"}
    assert comp["component"]["Text"]["usageHint"] == "h1"


def test_text_component_with_path_binding():
    v09 = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s1",
                "components": [
                    {"id": "root", "component": "Text", "text": {"path": "/name"}, "variant": "body"},
                ],
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    text_props = result[0]["surfaceUpdate"]["components"][0]["component"]["Text"]
    assert text_props["text"] == {"path": "/name"}
    assert text_props["usageHint"] == "body"


def test_row_component():
    v09 = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s1",
                "components": [
                    {
                        "id": "root",
                        "component": "Row",
                        "children": ["a", "b"],
                        "align": "center",
                        "justify": "spaceBetween",
                        "gap": 8,
                    },
                ],
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    row = result[0]["surfaceUpdate"]["components"][0]["component"]["Row"]
    assert row["children"] == {"explicitList": ["a", "b"]}
    assert row["alignment"] == "center"
    assert row["distribution"] == "spaceBetween"
    # gap is not in v0.8
    assert "gap" not in row


def test_column_component():
    v09 = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s1",
                "components": [
                    {
                        "id": "root",
                        "component": "Column",
                        "children": ["x", "y"],
                        "align": "stretch",
                        "gap": 12,
                    },
                ],
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    col = result[0]["surfaceUpdate"]["components"][0]["component"]["Column"]
    assert col["children"] == {"explicitList": ["x", "y"]}
    assert col["alignment"] == "stretch"
    assert "gap" not in col


def test_card_component():
    v09 = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s1",
                "components": [
                    {"id": "root", "component": "Card", "child": "content", "padding": 16},
                ],
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    card = result[0]["surfaceUpdate"]["components"][0]["component"]["Card"]
    assert card["child"] == "content"
    assert "padding" not in card


def test_button_primary():
    v09 = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s1",
                "components": [
                    {
                        "id": "root",
                        "component": "Button",
                        "child": "label",
                        "variant": "primary",
                        "action": {
                            "event": {
                                "name": "submit",
                                "context": {
                                    "id": {"path": "/id"},
                                    "name": "test",
                                },
                            }
                        },
                    },
                ],
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    btn = result[0]["surfaceUpdate"]["components"][0]["component"]["Button"]
    assert btn["child"] == "label"
    assert btn["primary"] is True
    assert btn["action"]["name"] == "submit"
    ctx = btn["action"]["context"]
    assert len(ctx) == 2
    # Find entries by key
    id_entry = next(e for e in ctx if e["key"] == "id")
    name_entry = next(e for e in ctx if e["key"] == "name")
    assert id_entry["value"] == {"path": "/id"}
    assert name_entry["value"] == {"literalString": "test"}


def test_button_secondary_no_primary_flag():
    v09 = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s1",
                "components": [
                    {"id": "root", "component": "Button", "child": "l", "variant": "secondary"},
                ],
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    btn = result[0]["surfaceUpdate"]["components"][0]["component"]["Button"]
    assert "primary" not in btn


def test_icon_component():
    v09 = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s1",
                "components": [
                    {"id": "root", "component": "Icon", "name": "send"},
                ],
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    icon = result[0]["surfaceUpdate"]["components"][0]["component"]["Icon"]
    assert icon["name"] == {"literalString": "send"}


def test_divider_component():
    v09 = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s1",
                "components": [
                    {"id": "root", "component": "Divider"},
                ],
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    divider = result[0]["surfaceUpdate"]["components"][0]["component"]["Divider"]
    assert divider == {}


def test_image_component():
    v09 = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s1",
                "components": [
                    {"id": "root", "component": "Image", "url": "https://example.com/img.png", "alt": "A photo"},
                ],
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    img = result[0]["surfaceUpdate"]["components"][0]["component"]["Image"]
    assert img["url"] == {"literalString": "https://example.com/img.png"}
    assert img["altText"] == {"literalString": "A photo"}


def test_tabs_component():
    v09 = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s1",
                "components": [
                    {
                        "id": "root",
                        "component": "Tabs",
                        "tabs": [
                            {"label": "Tab 1", "child": "c1"},
                            {"label": "Tab 2", "child": "c2"},
                        ],
                    },
                ],
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    tabs = result[0]["surfaceUpdate"]["components"][0]["component"]["Tabs"]
    assert len(tabs["tabItems"]) == 2
    assert tabs["tabItems"][0]["title"] == {"literalString": "Tab 1"}
    assert tabs["tabItems"][0]["child"] == "c1"
    assert tabs["tabItems"][1]["title"] == {"literalString": "Tab 2"}


def test_textfield_component():
    v09 = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s1",
                "components": [
                    {
                        "id": "root",
                        "component": "TextField",
                        "label": "Name",
                        "value": {"path": "/form/name"},
                    },
                ],
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    tf = result[0]["surfaceUpdate"]["components"][0]["component"]["TextField"]
    assert tf["label"] == {"literalString": "Name"}
    assert tf["text"] == {"path": "/form/name"}


def test_checkbox_component():
    v09 = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s1",
                "components": [
                    {"id": "root", "component": "Checkbox", "label": "Accept", "checked": {"path": "/accepted"}},
                ],
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    cb = result[0]["surfaceUpdate"]["components"][0]["component"]["Checkbox"]
    assert cb["label"] == {"literalString": "Accept"}
    assert cb["value"] == {"path": "/accepted"}


def test_slider_component():
    v09 = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s1",
                "components": [
                    {"id": "root", "component": "Slider", "min": 0, "max": 100, "value": {"path": "/val"}},
                ],
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    sl = result[0]["surfaceUpdate"]["components"][0]["component"]["Slider"]
    assert sl["minValue"] == 0
    assert sl["maxValue"] == 100
    assert sl["value"] == {"path": "/val"}


def test_list_component_with_template():
    v09 = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s1",
                "components": [
                    {
                        "id": "root",
                        "component": "List",
                        "items": {"path": "/items"},
                        "itemTemplate": "item-card",
                        "direction": "vertical",
                    },
                ],
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    lst = result[0]["surfaceUpdate"]["components"][0]["component"]["List"]
    assert lst["children"]["template"]["componentId"] == "item-card"
    assert lst["children"]["template"]["dataBinding"] == "/items"
    assert lst["direction"] == "vertical"


def test_modal_component():
    v09 = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s1",
                "components": [
                    {
                        "id": "root",
                        "component": "Modal",
                        "entryPointChild": "trigger",
                        "contentChild": "content",
                    },
                ],
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    modal = result[0]["surfaceUpdate"]["components"][0]["component"]["Modal"]
    assert modal["entryPointChild"] == "trigger"
    assert modal["contentChild"] == "content"


def test_weight_preserved():
    v09 = [
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "s1",
                "components": [
                    {"id": "root", "component": "Text", "text": "hi", "weight": 2},
                ],
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    comp = result[0]["surfaceUpdate"]["components"][0]
    assert comp["weight"] == 2


# ──────────────────────────────────────────────────────────────────
# updateDataModel -> dataModelUpdate
# ──────────────────────────────────────────────────────────────────


def test_data_model_simple():
    v09 = [
        {
            "version": "v0.9",
            "updateDataModel": {
                "surfaceId": "s1",
                "value": {"name": "Alice", "age": 30, "active": True},
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    dm = result[0]["dataModelUpdate"]
    assert dm["surfaceId"] == "s1"

    contents = dm["contents"]
    assert len(contents) == 3

    by_key = {c["key"]: c for c in contents}
    assert by_key["name"]["valueString"] == "Alice"
    assert by_key["age"]["valueNumber"] == 30
    assert by_key["active"]["valueBoolean"] is True


def test_data_model_nested_dict():
    v09 = [
        {
            "version": "v0.9",
            "updateDataModel": {
                "surfaceId": "s1",
                "value": {"address": {"city": "NYC", "zip": 10001}},
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    contents = result[0]["dataModelUpdate"]["contents"]
    assert len(contents) == 1

    addr = contents[0]
    assert addr["key"] == "address"
    assert "valueMap" in addr
    nested = {c["key"]: c for c in addr["valueMap"]}
    assert nested["city"]["valueString"] == "NYC"
    assert nested["zip"]["valueNumber"] == 10001


def test_data_model_array_serialized_as_json():
    v09 = [
        {
            "version": "v0.9",
            "updateDataModel": {
                "surfaceId": "s1",
                "value": {"items": [{"id": 1}, {"id": 2}]},
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    contents = result[0]["dataModelUpdate"]["contents"]
    items_entry = contents[0]
    assert items_entry["key"] == "items"
    assert items_entry["valueString"] == orjson.dumps([{"id": 1}, {"id": 2}]).decode()


def test_data_model_none_becomes_empty_string():
    v09 = [
        {
            "version": "v0.9",
            "updateDataModel": {
                "surfaceId": "s1",
                "value": {"missing": None},
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    entry = result[0]["dataModelUpdate"]["contents"][0]
    assert entry["valueString"] == ""


def test_data_model_preserves_path():
    v09 = [
        {
            "version": "v0.9",
            "updateDataModel": {
                "surfaceId": "s1",
                "path": "/user",
                "value": {"name": "Bob"},
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    dm = result[0]["dataModelUpdate"]
    assert dm["path"] == "/user"


def test_data_model_bool_before_int():
    """Booleans must be checked before ints since bool is a subclass of int."""
    v09 = [
        {
            "version": "v0.9",
            "updateDataModel": {
                "surfaceId": "s1",
                "value": {"flag": True, "count": 1},
            },
        }
    ]
    result = adapt_v09_to_v08(v09)
    by_key = {c["key"]: c for c in result[0]["dataModelUpdate"]["contents"]}
    assert "valueBoolean" in by_key["flag"]
    assert by_key["flag"]["valueBoolean"] is True
    assert "valueNumber" in by_key["count"]
    assert by_key["count"]["valueNumber"] == 1


# ──────────────────────────────────────────────────────────────────
# deleteSurface passthrough
# ──────────────────────────────────────────────────────────────────


def test_delete_surface():
    v09 = [
        {
            "version": "v0.9",
            "deleteSurface": {"surfaceId": "old"},
        }
    ]
    result = adapt_v09_to_v08(v09)
    assert result[0]["deleteSurface"]["surfaceId"] == "old"


# ──────────────────────────────────────────────────────────────────
# Full message sequence (3-message pattern)
# ──────────────────────────────────────────────────────────────────


def test_full_three_message_sequence():
    """End-to-end: createSurface + updateComponents + updateDataModel."""
    v09 = [
        {
            "version": "v0.9",
            "createSurface": {
                "surfaceId": "flight-status",
                "catalogId": "https://a2ui.org/specification/v0_9/basic_catalog.json",
                "sendDataModel": True,
            },
        },
        {
            "version": "v0.9",
            "updateComponents": {
                "surfaceId": "flight-status",
                "components": [
                    {"id": "root", "component": "Card", "child": "col"},
                    {"id": "col", "component": "Column", "children": ["title", "divider", "info"], "align": "stretch"},
                    {"id": "title", "component": "Text", "text": {"path": "/flightNumber"}, "variant": "h2"},
                    {"id": "divider", "component": "Divider"},
                    {"id": "info", "component": "Text", "text": {"path": "/status"}, "variant": "body"},
                ],
            },
        },
        {
            "version": "v0.9",
            "updateDataModel": {
                "surfaceId": "flight-status",
                "value": {
                    "flightNumber": "UA 123",
                    "status": "On Time",
                },
            },
        },
    ]

    result = adapt_v09_to_v08(v09)
    assert len(result) == 3

    # beginRendering
    assert "beginRendering" in result[0]
    assert result[0]["beginRendering"]["surfaceId"] == "flight-status"
    assert result[0]["beginRendering"]["root"] == "root"

    # surfaceUpdate
    assert "surfaceUpdate" in result[1]
    comps = result[1]["surfaceUpdate"]["components"]
    assert len(comps) == 5
    # Card wraps correctly
    assert comps[0]["component"]["Card"]["child"] == "col"
    # Column children wrapped
    assert comps[1]["component"]["Column"]["children"]["explicitList"] == ["title", "divider", "info"]
    # Text values wrapped
    assert comps[2]["component"]["Text"]["text"] == {"path": "/flightNumber"}
    assert comps[2]["component"]["Text"]["usageHint"] == "h2"

    # dataModelUpdate
    assert "dataModelUpdate" in result[2]
    by_key = {c["key"]: c for c in result[2]["dataModelUpdate"]["contents"]}
    assert by_key["flightNumber"]["valueString"] == "UA 123"
    assert by_key["status"]["valueString"] == "On Time"


def test_empty_list():
    assert adapt_v09_to_v08([]) == []
