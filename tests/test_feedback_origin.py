"""Every feedback row must say what produced it.

This is the control that makes model-generated feedback safe to accept. Without
it you cannot exclude model-derived judgments from a measurement, cannot hold a
human-only slice to measure against, and cannot keep a floor on the human ratio
-- so bootstrapping model feedback from human feedback is unauditable by
construction.

Two halves, deliberately different in kind:

- `origin_kind` is a CLOSED enum. It is the thing filters are written against,
  and an open vocabulary here fails silently: one writer records `llm`, another
  records `model`, and an exclusion filter quietly misses rows. A new kind of
  producer is an engineering decision -- measurement code has to handle it -- so
  it belongs in code review, not in a row.
- `origin_id` is OPEN, via `dim_feedback_origin`. Which person, which model
  version, which upstream system is discovered by running the loop, and new ones
  must not require a schema change.

The default is `unspecified` rather than `human`. An unlabeled row that
defaulted to human would silently contaminate the one slice you measure
against, and it would look like a clean measurement while doing it.
"""

from __future__ import annotations

import itertools

import pytest

from freud_schema.tables import (
    CorrectionType,
    Extraction,
    FeedbackOrigin,
    FeedbackOriginKind,
    Session,
    Skill,
    Source,
)


_n = itertools.count()


def _extraction(store) -> str:
    """A fresh extraction each call -- dim_skill is SCD-2, so re-inserting the
    same domain/task_type at the same version is correctly rejected."""
    i = next(_n)
    skill_key = store.insert_skill(
        Skill(domain=f"d{i}", task_type="t", content="c"))
    source_key = store.insert_source(
        Source(content_path=f"/f{i}", media_type="text/plain"))
    session_key = store.insert_session(Session(task_description="t"))
    return store.insert_extraction(Extraction(
        source_key=source_key, skill_key=skill_key,
        session_key=session_key, output={}))


class TestOriginKindIsClosed:
    def test_unlabeled_feedback_is_unspecified_not_human(self, store):
        """The safety property. Defaulting to human would contaminate the
        human-only slice with rows nobody attributed."""
        from freud_schema import ops
        key = _extraction(store)
        result = ops.feedback_add(
            store, extraction_key=key,
            correction_type=CorrectionType.WRONG_VALUE, correction={"a": 1})
        fb = store.get_feedback(result["feedback_key"])
        assert fb.origin_kind == FeedbackOriginKind.UNSPECIFIED

    def test_unknown_origin_kind_is_rejected(self, store):
        """A CHECK constraint, not a convention -- this is what stops `llm` and
        `model` diverging into two spellings of the same thing."""
        with pytest.raises(Exception):
            store.con.execute(
                "INSERT INTO dim_feedback_origin "
                "(feedback_origin_key, origin_id, origin_kind) "
                "VALUES ('k', 'some-model', 'llm')")


class TestOriginIdIsOpen:
    def test_new_origin_registers_without_a_schema_change(self, store):
        key = store.register_feedback_origin(FeedbackOrigin(
            origin_id="claude-opus-4-8",
            origin_kind=FeedbackOriginKind.MODEL,
            description="seeded from the human-reviewed slice"))
        assert key
        again = store.register_feedback_origin(FeedbackOrigin(
            origin_id="claude-opus-4-8", origin_kind=FeedbackOriginKind.MODEL))
        assert again == key, "registration must be idempotent"

    def test_origin_kind_is_denormalized_onto_the_fact(self, store):
        """Filtering must not require a join. The whole point is that excluding
        model-derived rows from a measurement is cheap enough to always do."""
        from freud_schema import ops
        store.register_feedback_origin(FeedbackOrigin(
            origin_id="claude-opus-4-8", origin_kind=FeedbackOriginKind.MODEL))
        key = _extraction(store)
        result = ops.feedback_add(
            store, extraction_key=key,
            correction_type=CorrectionType.WRONG_VALUE, correction={"a": 1},
            origin_id="claude-opus-4-8")
        fb = store.get_feedback(result["feedback_key"])
        assert fb.origin_kind == FeedbackOriginKind.MODEL
        assert fb.feedback_origin_key

    def test_unregistered_origin_is_rejected(self, store):
        """Same fail-closed rule as finding_type: the registry validates, so a
        typo becomes an error rather than a new silent category."""
        from freud_schema import ops
        key = _extraction(store)
        with pytest.raises(ValueError, match="not registered"):
            ops.feedback_add(
                store, extraction_key=key,
                correction_type=CorrectionType.WRONG_VALUE, correction={},
                origin_id="claude-opus-4-8-typo")


class TestTheMeasurementItEnables:
    def test_human_only_slice_excludes_model_and_unspecified(self, store):
        """The measurement this whole feature exists to make possible."""
        from freud_schema import ops
        store.register_feedback_origin(FeedbackOrigin(
            origin_id="owner", origin_kind=FeedbackOriginKind.HUMAN))
        store.register_feedback_origin(FeedbackOrigin(
            origin_id="claude-opus-4-8", origin_kind=FeedbackOriginKind.MODEL))

        for origin in ("owner", "claude-opus-4-8", None):
            ops.feedback_add(
                store, extraction_key=_extraction(store),
                correction_type=CorrectionType.WRONG_VALUE,
                correction={"a": 1}, origin_id=origin)

        all_fb = store.list_feedback()
        assert len(all_fb) == 3
        human = [f for f in all_fb
                 if f.origin_kind == FeedbackOriginKind.HUMAN]
        assert len(human) == 1, (
            "a human-only slice must exclude both model-derived and "
            "unattributed rows")
