"""Data access layer for A2UI surfaces.

Wraps ExperimentStore to provide query functions that return plain dicts
suitable for A2UI data models. Uses Pydantic model_dump(mode='json') for
serialization (handles enum .value and datetime conversion automatically).
"""

from __future__ import annotations

import os
from typing import Any

from freud_schema.db import connect
from freud_schema.store import ExperimentStore
from freud_schema.tables import (
    ValidationStatus,
)


def get_store(db_path: str | None = None) -> ExperimentStore:
    """Open (or create) the experiment database and return a store."""
    path = db_path or os.environ.get("FREUDAGENT_DB", None)
    con = connect(path)
    return ExperimentStore(con)


def _to_dict(model: Any, *, exclude: set[str] | None = None) -> dict[str, Any]:
    """Serialize a Pydantic model to a plain dict suitable for JSON/A2UI."""
    return model.model_dump(mode="json", exclude=exclude)


def _skill_to_dict(sk: Any) -> dict[str, Any]:
    """Serialize a Skill, adding a content_preview and excluding full content."""
    d = _to_dict(sk, exclude={"content", "metadata", "parent_skill_id", "created_at", "updated_at"})
    content = sk.content
    d["content_preview"] = (content[:200] + "...") if content and len(content) > 200 else content
    return d


# ------------------------------------------------------------------
# Query functions (return data suitable for A2UI data models)
# ------------------------------------------------------------------


def get_extractions(
    store: ExperimentStore,
    *,
    skill_id: int | None = None,
    validation_status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List extractions with optional filters."""
    vs = ValidationStatus(validation_status) if validation_status else None
    exts = store.list_extractions(skill_id=skill_id, validation_status=vs, limit=limit)
    return [_to_dict(e) for e in exts]


def get_extraction_detail(
    store: ExperimentStore,
    extraction_id: int,
) -> dict[str, Any] | None:
    """Get a single extraction with related source, skill, and feedback."""
    ext = store.get_extraction(extraction_id)
    if ext is None:
        return None

    result = _to_dict(ext)

    # Enrich with source info
    source = store.get_source(ext.source_id)
    result["source"] = _to_dict(source) if source else None

    # Enrich with skill info
    skill = store.get_skill(ext.skill_id)
    result["skill"] = _skill_to_dict(skill) if skill else None

    # Enrich with feedback
    feedback_list = store.list_feedback(skill_id=ext.skill_id)
    result["feedback"] = [
        _to_dict(fb)
        for fb in feedback_list
        if fb.extraction_id == ext.id
    ]

    return result


def get_sessions(
    store: ExperimentStore,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """List recent sessions."""
    sessions = store.list_sessions(limit=limit)
    return [_to_dict(s) for s in sessions]


def get_dashboard_stats(store: ExperimentStore) -> dict[str, Any]:
    """Aggregate stats for the dashboard surface."""
    skills = store.list_skills()
    active_skills = [s for s in skills if s.status.value == "active"]

    extractions = store.list_extractions(limit=1000)
    pending = sum(1 for e in extractions if e.validation_status == ValidationStatus.PENDING)
    validated = sum(1 for e in extractions if e.validation_status == ValidationStatus.VALIDATED)
    rejected = sum(1 for e in extractions if e.validation_status == ValidationStatus.REJECTED)

    recent_sessions = store.list_sessions(limit=5)

    feedback_list = store.list_feedback()

    return {
        "skills": {
            "total": len(skills),
            "active": len(active_skills),
        },
        "extractions": {
            "total": len(extractions),
            "pending": pending,
            "validated": validated,
            "rejected": rejected,
        },
        "sessions": {
            "recent": [_to_dict(s) for s in recent_sessions],
        },
        "feedback": {
            "total": len(feedback_list),
        },
    }


def get_feedback_summary(
    store: ExperimentStore,
    skill_id: int | None = None,
) -> dict[str, Any]:
    """Aggregate feedback by correction type."""
    if skill_id is not None:
        aggregated = store.aggregate_feedback(skill_id)
        by_type = {ct: count for ct, count in aggregated}
    else:
        # Aggregate across all skills
        feedback_list = store.list_feedback()
        by_type: dict[str, int] = {}
        for fb in feedback_list:
            ct = fb.correction_type.value if fb.correction_type else "unknown"
            by_type[ct] = by_type.get(ct, 0) + 1

    return {
        "skill_id": skill_id,
        "by_type": by_type,
        "total": sum(by_type.values()),
    }
