"""A2UI v0.9-to-v0.8 message adapter.

Converts v0.9 messages (as produced by LLMs using the A2UI authoring skill)
into v0.8 messages (as consumed by @a2ui/lit renderer).

Three message transformations:
  createSurface  -> beginRendering
  updateComponents -> surfaceUpdate  (flat component format -> nested)
  updateDataModel  -> dataModelUpdate (plain dict -> typed key-value contents)
"""

from __future__ import annotations

from typing import Any

import orjson


# ──────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────


def adapt_v09_to_v08(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert a list of v0.9 A2UI messages to v0.8 format."""
    return [_adapt_message(msg) for msg in messages]


# ──────────────────────────────────────────────────────────────────
# Message-level dispatch
# ──────────────────────────────────────────────────────────────────


def _adapt_message(msg: dict[str, Any]) -> dict[str, Any]:
    if "createSurface" in msg:
        return _adapt_create_surface(msg["createSurface"])
    if "updateComponents" in msg:
        return _adapt_update_components(msg["updateComponents"])
    if "updateDataModel" in msg:
        return _adapt_update_data_model(msg["updateDataModel"])
    if "deleteSurface" in msg:
        return {"deleteSurface": {"surfaceId": msg["deleteSurface"]["surfaceId"]}}
    return msg  # pass through unknown


# ──────────────────────────────────────────────────────────────────
# createSurface -> beginRendering
# ──────────────────────────────────────────────────────────────────


def _adapt_create_surface(body: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "beginRendering": {
            "surfaceId": body["surfaceId"],
            "root": "root",
        }
    }
    return result


# ──────────────────────────────────────────────────────────────────
# updateComponents -> surfaceUpdate
# ──────────────────────────────────────────────────────────────────


def _adapt_update_components(body: dict[str, Any]) -> dict[str, Any]:
    v09_components = body.get("components", [])
    v08_components = [_adapt_component(c) for c in v09_components]
    return {
        "surfaceUpdate": {
            "surfaceId": body["surfaceId"],
            "components": v08_components,
        }
    }


# Keys that live at the ComponentInstance level, not inside the component props
_INSTANCE_KEYS = frozenset({"id", "component", "weight"})


def _adapt_component(comp: dict[str, Any]) -> dict[str, Any]:
    comp_type = comp.get("component", "")
    comp_id = comp.get("id", "")

    # Collect all keys that aren't instance-level
    raw_props = {k: v for k, v in comp.items() if k not in _INSTANCE_KEYS}

    # Transform props based on component type
    transformer = _COMPONENT_TRANSFORMERS.get(comp_type, _transform_generic)
    v08_props = transformer(raw_props)

    result: dict[str, Any] = {
        "id": comp_id,
        "component": {comp_type: v08_props},
    }
    if "weight" in comp:
        result["weight"] = comp["weight"]
    return result


# ──────────────────────────────────────────────────────────────────
# Component property transformers
# ──────────────────────────────────────────────────────────────────


def _transform_text(props: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if "text" in props:
        result["text"] = _wrap_string_value(props["text"])
    if "variant" in props:
        result["usageHint"] = props["variant"]
    return result


def _transform_row(props: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if "children" in props:
        result["children"] = {"explicitList": props["children"]}
    if "align" in props:
        result["alignment"] = props["align"]
    if "justify" in props:
        result["distribution"] = props["justify"]
    # gap is not in v0.8 schema -- dropped
    return result


def _transform_column(props: dict[str, Any]) -> dict[str, Any]:
    # Same structure as Row
    return _transform_row(props)


def _transform_card(props: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if "child" in props:
        result["child"] = props["child"]
    # padding is not in v0.8 schema -- dropped
    return result


def _transform_button(props: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if "child" in props:
        result["child"] = props["child"]

    variant = props.get("variant", "primary")
    if variant == "primary":
        result["primary"] = True

    if "action" in props:
        result["action"] = _transform_action(props["action"])

    return result


def _transform_action(action: dict[str, Any]) -> dict[str, Any]:
    """Convert v0.9 action (with event wrapper) to v0.8 action format."""
    # v0.9: {"event": {"name": "...", "context": {key: val, ...}}}
    # v0.8: {"name": "...", "context": [{key: "k", value: {literalString/path/...}}, ...]}
    event = action.get("event", action)
    result: dict[str, Any] = {"name": event.get("name", "")}

    context = event.get("context", {})
    if context:
        result["context"] = _transform_action_context(context)

    return result


def _transform_action_context(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert context dict to v0.8 array of {key, value} entries."""
    entries = []
    for key, val in context.items():
        entry: dict[str, Any] = {"key": key}
        if isinstance(val, dict) and "path" in val:
            entry["value"] = {"path": val["path"]}
        elif isinstance(val, str):
            entry["value"] = {"literalString": val}
        elif isinstance(val, bool):
            entry["value"] = {"literalBoolean": val}
        elif isinstance(val, (int, float)):
            entry["value"] = {"literalNumber": val}
        else:
            entry["value"] = {"literalString": str(val)}
        entries.append(entry)
    return entries


def _transform_icon(props: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if "name" in props:
        result["name"] = _wrap_string_value(props["name"])
    return result


def _transform_divider(props: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if "axis" in props:
        result["axis"] = props["axis"]
    if "color" in props:
        result["color"] = props["color"]
    if "thickness" in props:
        result["thickness"] = props["thickness"]
    return result


def _transform_image(props: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if "url" in props:
        result["url"] = _wrap_string_value(props["url"])
    if "alt" in props:
        result["altText"] = _wrap_string_value(props["alt"])
    if "usageHint" in props:
        result["usageHint"] = props["usageHint"]
    if "fit" in props:
        result["fit"] = props["fit"]
    return result


def _transform_tabs(props: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    tabs = props.get("tabs", [])
    tab_items = []
    for tab in tabs:
        item: dict[str, Any] = {}
        if "label" in tab:
            item["title"] = _wrap_string_value(tab["label"])
        if "child" in tab:
            item["child"] = tab["child"]
        tab_items.append(item)
    result["tabItems"] = tab_items
    return result


def _transform_modal(props: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if "child" in props:
        result["contentChild"] = props["child"]
    if "contentChild" in props:
        result["contentChild"] = props["contentChild"]
    if "entryPointChild" in props:
        result["entryPointChild"] = props["entryPointChild"]
    return result


def _transform_textfield(props: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if "label" in props:
        result["label"] = _wrap_string_value(props["label"])
    if "value" in props:
        result["text"] = _wrap_string_value(props["value"])
    if "multiline" in props and props["multiline"]:
        result["textFieldType"] = "longText"
    if "validationRegexp" in props:
        result["validationRegexp"] = props["validationRegexp"]
    return result


def _transform_checkbox(props: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if "label" in props:
        result["label"] = _wrap_string_value(props["label"])
    if "checked" in props:
        result["value"] = _wrap_boolean_value(props["checked"])
    return result


def _transform_slider(props: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if "min" in props:
        result["minValue"] = props["min"]
    if "max" in props:
        result["maxValue"] = props["max"]
    if "value" in props:
        result["value"] = _wrap_number_value(props["value"])
    return result


def _transform_list(props: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}

    # v0.9 List uses itemTemplate + items (path-bound data)
    # v0.8 List uses children.template = {componentId, dataBinding}
    item_template = props.get("itemTemplate")
    items = props.get("items")

    if item_template and isinstance(items, dict) and "path" in items:
        result["children"] = {
            "template": {
                "componentId": item_template,
                "dataBinding": items["path"],
            }
        }
    elif "children" in props:
        # Fallback: explicit children list
        result["children"] = {"explicitList": props["children"]}

    if "direction" in props:
        result["direction"] = props["direction"]
    if "align" in props:
        result["alignment"] = props["align"]
    return result


def _transform_audio(props: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if "url" in props:
        result["url"] = _wrap_string_value(props["url"])
    if "description" in props:
        result["description"] = _wrap_string_value(props["description"])
    return result


def _transform_video(props: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if "url" in props:
        result["url"] = _wrap_string_value(props["url"])
    return result


def _transform_multiple_choice(props: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if "selections" in props:
        sel = props["selections"]
        if isinstance(sel, dict) and "path" in sel:
            result["selections"] = {"path": sel["path"]}
        elif isinstance(sel, list):
            result["selections"] = {"literalArray": sel}
    if "options" in props:
        v08_options = []
        for opt in props["options"]:
            v08_opt: dict[str, Any] = {}
            if "label" in opt:
                v08_opt["label"] = _wrap_string_value(opt["label"])
            if "value" in opt:
                v08_opt["value"] = opt["value"]
            v08_options.append(v08_opt)
        result["options"] = v08_options
    if "maxAllowedSelections" in props:
        result["maxAllowedSelections"] = props["maxAllowedSelections"]
    if "type" in props:
        result["type"] = props["type"]
    if "filterable" in props:
        result["filterable"] = props["filterable"]
    return result


def _transform_datetime_input(props: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if "value" in props:
        result["value"] = _wrap_string_value(props["value"])
    if "mode" in props:
        mode = props["mode"]
        if mode in ("date", "datetime"):
            result["enableDate"] = True
        if mode in ("time", "datetime"):
            result["enableTime"] = True
    if "enableDate" in props:
        result["enableDate"] = props["enableDate"]
    if "enableTime" in props:
        result["enableTime"] = props["enableTime"]
    if "outputFormat" in props:
        result["outputFormat"] = props["outputFormat"]
    return result


def _transform_generic(props: dict[str, Any]) -> dict[str, Any]:
    """Fallback: pass through props as-is for unknown component types."""
    return dict(props)


_COMPONENT_TRANSFORMERS = {
    "Text": _transform_text,
    "Row": _transform_row,
    "Column": _transform_column,
    "Card": _transform_card,
    "Button": _transform_button,
    "Icon": _transform_icon,
    "Divider": _transform_divider,
    "Image": _transform_image,
    "Tabs": _transform_tabs,
    "Modal": _transform_modal,
    "TextField": _transform_textfield,
    "Checkbox": _transform_checkbox,
    "Slider": _transform_slider,
    "List": _transform_list,
    "AudioPlayer": _transform_audio,
    "Video": _transform_video,
    "MultipleChoice": _transform_multiple_choice,
    "DateTimeInput": _transform_datetime_input,
    # Surface works like Column
    "Surface": _transform_column,
}


# ──────────────────────────────────────────────────────────────────
# updateDataModel -> dataModelUpdate
# ──────────────────────────────────────────────────────────────────


def _adapt_update_data_model(body: dict[str, Any]) -> dict[str, Any]:
    value = body.get("value", {})
    result: dict[str, Any] = {
        "dataModelUpdate": {
            "surfaceId": body["surfaceId"],
            "contents": _dict_to_contents(value),
        }
    }
    if "path" in body:
        result["dataModelUpdate"]["path"] = body["path"]
    return result


def _dict_to_contents(d: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert a plain dict to v0.8 typed key-value contents array.

    Recursive: nested dicts become valueMap arrays.
    Arrays serialize to JSON strings (v0.8 DataValue has no array type).
    """
    contents: list[dict[str, Any]] = []
    for key, val in d.items():
        entry: dict[str, Any] = {"key": key}
        if isinstance(val, bool):
            # Must check bool before int (bool is subclass of int)
            entry["valueBoolean"] = val
        elif isinstance(val, (int, float)):
            entry["valueNumber"] = val
        elif isinstance(val, str):
            entry["valueString"] = val
        elif isinstance(val, dict):
            entry["valueMap"] = _dict_to_contents(val)
        elif isinstance(val, list):
            # v0.8 DataValue has no array type; serialize as JSON string
            entry["valueString"] = orjson.dumps(val).decode()
        elif val is None:
            entry["valueString"] = ""
        else:
            entry["valueString"] = str(val)
        contents.append(entry)
    return contents


# ──────────────────────────────────────────────────────────────────
# Value wrapping helpers
# ──────────────────────────────────────────────────────────────────


def _wrap_string_value(val: Any) -> dict[str, Any]:
    """Wrap a raw string or path-object into v0.8 StringValueSchema."""
    if isinstance(val, str):
        return {"literalString": val}
    if isinstance(val, dict) and "path" in val:
        return {"path": val["path"]}
    # Pass through if already in correct format or unknown
    if isinstance(val, dict):
        return val
    return {"literalString": str(val)}


def _wrap_number_value(val: Any) -> dict[str, Any]:
    """Wrap a raw number or path-object into v0.8 NumberValueSchema."""
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return {"literalNumber": val}
    if isinstance(val, dict) and "path" in val:
        return {"path": val["path"]}
    if isinstance(val, dict):
        return val
    return {"literalNumber": float(val)}


def _wrap_boolean_value(val: Any) -> dict[str, Any]:
    """Wrap a raw bool or path-object into v0.8 BooleanValueSchema."""
    if isinstance(val, bool):
        return {"literalBoolean": val}
    if isinstance(val, dict) and "path" in val:
        return {"path": val["path"]}
    if isinstance(val, dict):
        return val
    return {"literalBoolean": bool(val)}
