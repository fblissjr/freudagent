"""A2UI validation and parsing bridge.

Provides structural validation of A2UI v0.9 messages. Optionally delegates
to a2ui.core.schema for full catalog-aware validation if installed.
"""

from __future__ import annotations

import re
from typing import Any

# RFC 6901 JSON Pointer pattern
_JSON_POINTER_RE = re.compile(r"^(?:/(?:[^~/]|~[01])*)*$")

_VALID_MESSAGE_TYPES = frozenset(
    {"createSurface", "updateComponents", "updateDataModel", "deleteSurface"}
)

# Components that reference children by single ID
_SINGLE_CHILD_FIELDS = {"child", "contentChild", "entryPointChild", "itemTemplate"}
# Components that reference children by list of IDs
_LIST_CHILD_FIELDS = {"children"}


class ValidationError(Exception):
    """Raised when A2UI validation fails."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"A2UI validation failed: {'; '.join(errors)}")


class A2UIBridge:
    """Validates and parses A2UI messages.

    Uses a built-in structural validator by default. If ``a2ui-agent`` is
    installed, upgrades to full schema validation via ``a2ui.core``.
    """

    def __init__(self) -> None:
        self._full_validator: Any | None = None
        try:
            from a2ui.core.schema.catalog import A2uiCatalog
            from a2ui.core.schema.validator import A2uiValidator

            catalog = A2uiCatalog()
            self._full_validator = A2uiValidator(catalog)
        except ImportError:
            pass

    @property
    def has_full_validation(self) -> bool:
        return self._full_validator is not None

    def validate(self, messages: list[dict[str, Any]]) -> list[str]:
        """Validate a list of A2UI messages.

        Returns an empty list on success, or a list of error strings.
        """
        errors: list[str] = []

        # Structural checks (always run)
        errors.extend(self._validate_structural(messages))

        # Full schema validation (if available)
        if self._full_validator is not None and not errors:
            try:
                self._full_validator.validate(messages)
            except (ValueError, Exception) as exc:
                errors.append(str(exc))

        return errors

    def validate_or_raise(self, messages: list[dict[str, Any]]) -> None:
        """Validate and raise ``ValidationError`` on failure."""
        errors = self.validate(messages)
        if errors:
            raise ValidationError(errors)

    # ------------------------------------------------------------------
    # Structural validation (built-in, no external deps)
    # ------------------------------------------------------------------

    def _validate_structural(self, messages: list[dict[str, Any]]) -> list[str]:
        errors: list[str] = []

        if not isinstance(messages, list):
            return ["messages must be a list"]
        if not messages:
            return ["messages list is empty"]

        has_create = False
        has_components = False
        component_ids: set[str] = set()
        child_refs: list[tuple[str, str]] = []  # (parent_id, child_id)

        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                errors.append(f"message[{i}]: not a dict")
                continue

            # Version check
            version = msg.get("version")
            if version != "v0.9":
                errors.append(
                    f"message[{i}]: expected version 'v0.9', got {version!r}"
                )

            # Identify message type
            msg_types = [k for k in msg if k in _VALID_MESSAGE_TYPES]
            if not msg_types:
                errors.append(
                    f"message[{i}]: no valid message type found "
                    f"(keys: {list(msg.keys())})"
                )
                continue

            if len(msg_types) > 1:
                errors.append(
                    f"message[{i}]: multiple message types: {msg_types}"
                )

            msg_type = msg_types[0]
            body = msg[msg_type]

            if not isinstance(body, dict):
                errors.append(f"message[{i}].{msg_type}: body must be a dict")
                continue

            # surfaceId required on all types
            if "surfaceId" not in body:
                errors.append(f"message[{i}].{msg_type}: missing surfaceId")

            if msg_type == "createSurface":
                has_create = True

            elif msg_type == "updateComponents":
                has_components = True
                components = body.get("components")
                if not isinstance(components, list):
                    errors.append(
                        f"message[{i}].updateComponents: "
                        "components must be a list"
                    )
                    continue

                for j, comp in enumerate(components):
                    if not isinstance(comp, dict):
                        errors.append(
                            f"message[{i}].updateComponents.components[{j}]: "
                            "not a dict"
                        )
                        continue

                    comp_id = comp.get("id")
                    if not comp_id or not isinstance(comp_id, str):
                        errors.append(
                            f"message[{i}].updateComponents.components[{j}]: "
                            "missing or invalid id"
                        )
                        continue

                    if comp_id in component_ids:
                        errors.append(
                            f"message[{i}].updateComponents.components[{j}]: "
                            f"duplicate id '{comp_id}'"
                        )
                    component_ids.add(comp_id)

                    comp_type = comp.get("component")
                    if not comp_type or not isinstance(comp_type, str):
                        errors.append(
                            f"message[{i}].updateComponents.components[{j}]: "
                            "missing or invalid component type"
                        )

                    # Collect child references for topology check
                    for field in _SINGLE_CHILD_FIELDS:
                        val = comp.get(field)
                        if isinstance(val, str):
                            child_refs.append((comp_id, val))

                    for field in _LIST_CHILD_FIELDS:
                        val = comp.get(field)
                        if isinstance(val, list):
                            for item in val:
                                if isinstance(item, str):
                                    child_refs.append((comp_id, item))

                    # Tabs special case
                    tabs = comp.get("tabs")
                    if isinstance(tabs, list):
                        for tab in tabs:
                            if isinstance(tab, dict):
                                tab_child = tab.get("child")
                                if isinstance(tab_child, str):
                                    child_refs.append((comp_id, tab_child))

            elif msg_type == "updateDataModel":
                path = body.get("path")
                if path is not None and isinstance(path, str):
                    if not _JSON_POINTER_RE.fullmatch(path):
                        errors.append(
                            f"message[{i}].updateDataModel: "
                            f"invalid JSON Pointer: {path!r}"
                        )

        # Cross-message checks
        if has_create and not has_components:
            # Not necessarily an error for incremental updates, but warn
            pass

        if has_components:
            # Root component check
            if "root" not in component_ids:
                errors.append("no component with id='root' found")

            # Dangling reference check
            for parent_id, child_id in child_refs:
                if child_id not in component_ids:
                    errors.append(
                        f"component '{parent_id}' references "
                        f"non-existent component '{child_id}'"
                    )

            # Self-reference check
            for parent_id, child_id in child_refs:
                if parent_id == child_id:
                    errors.append(
                        f"component '{parent_id}' references itself"
                    )

            # Circular reference check (DFS from root)
            adj: dict[str, list[str]] = {cid: [] for cid in component_ids}
            for parent_id, child_id in child_refs:
                if parent_id in adj and child_id in component_ids:
                    adj[parent_id].append(child_id)

            visited: set[str] = set()
            stack: set[str] = set()

            def _dfs(node: str) -> str | None:
                visited.add(node)
                stack.add(node)
                for neighbor in adj.get(node, []):
                    if neighbor not in visited:
                        cycle = _dfs(neighbor)
                        if cycle:
                            return cycle
                    elif neighbor in stack:
                        return neighbor
                stack.discard(node)
                return None

            if "root" in adj:
                cycle_node = _dfs("root")
                if cycle_node:
                    errors.append(
                        f"circular reference detected involving "
                        f"component '{cycle_node}'"
                    )

                # Orphan check
                orphans = component_ids - visited
                if orphans:
                    errors.append(
                        f"orphaned components not reachable from root: "
                        f"{sorted(orphans)}"
                    )

        return errors


# Module-level singleton for convenience
_bridge: A2UIBridge | None = None


def get_bridge() -> A2UIBridge:
    """Return the module-level bridge singleton."""
    global _bridge
    if _bridge is None:
        _bridge = A2UIBridge()
    return _bridge
