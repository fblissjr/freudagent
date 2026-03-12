"""Tests for the Freud Schema package."""

import pytest

from freud_schema.archetypes import (
    ARCHETYPES,
    get_archetype,
    get_by_category,
    list_archetype_names,
    search_archetypes,
)
from freud_schema.dataset import (
    filter_by_book,
    filter_by_topic,
    list_books,
    list_topics,
    load_entries,
    search_terminology,
    search_text,
    to_jsonl,
)
from freud_schema.harness import (
    PRESETS,
    compose_by_category,
    compose_full,
    compose_preset,
    compose_system_prompt,
)
from freud_schema.models import ArchetypeCategory, FreudEntry


@pytest.fixture(scope="module")
def entries():
    return load_entries()


# ---------------------------------------------------------------------------
# Dataset tests
# ---------------------------------------------------------------------------


def test_load_entries(entries):
    assert len(entries) == 17
    assert all(isinstance(e, FreudEntry) for e in entries)


def test_all_entries_have_8_columns(entries):
    for e in entries:
        assert e.book_title
        assert e.chapter_section
        assert e.core_topic
        assert e.major_finding
        assert e.crucial_quote
        assert isinstance(e.key_terminology, list)
        assert len(e.key_terminology) >= 1
        assert e.source_context
        assert e.translation_notes


def test_filter_by_topic(entries):
    dream = filter_by_topic(entries, "Dream")
    assert len(dream) >= 3
    for e in dream:
        assert "dream" in e.core_topic.lower()


def test_filter_by_book(entries):
    interp = filter_by_book(entries, "Interpretation of Dreams")
    assert len(interp) == 4


def test_search_terminology(entries):
    results = search_terminology(entries, "Id")
    assert any("Id" in e.key_terminology for e in results)


def test_search_text(entries):
    results = search_text(entries, "wish")
    assert len(results) >= 1


def test_list_topics(entries):
    topics = list_topics(entries)
    assert len(topics) >= 5
    assert all(isinstance(t, str) for t in topics)


def test_list_books(entries):
    books = list_books(entries)
    assert len(books) >= 5


def test_to_jsonl_roundtrip(entries):
    jsonl = to_jsonl(entries)
    lines = [l for l in jsonl.strip().split("\n") if l]
    assert len(lines) == len(entries)
    for line in lines:
        FreudEntry.model_validate_json(line)


def test_entry_model_serialization():
    entry = FreudEntry(
        book_title="Test Book",
        chapter_section="Ch. 1",
        core_topic="Test Topic",
        major_finding="A finding",
        crucial_quote="A quote",
        key_terminology=["Term1", "Term2"],
        source_context="Some context",
        translation_notes="Some notes",
    )
    data = entry.model_dump()
    assert data["book_title"] == "Test Book"
    assert len(data["key_terminology"]) == 2
    restored = FreudEntry.model_validate(data)
    assert restored == entry


# ---------------------------------------------------------------------------
# Archetype registry tests
# ---------------------------------------------------------------------------


def test_archetype_count():
    assert len(ARCHETYPES) == 9


def test_all_archetypes_have_required_fields():
    for a in ARCHETYPES:
        assert a.name
        assert a.freudian_concept
        assert a.sdk_pattern
        assert a.description
        assert a.prompt_fragment
        assert isinstance(a.category, ArchetypeCategory)


def test_get_archetype():
    a = get_archetype("structural-triad")
    assert a is not None
    assert a.freudian_concept == "Id / Ego / Superego"

    assert get_archetype("nonexistent") is None


def test_get_by_category():
    structural = get_by_category(ArchetypeCategory.STRUCTURAL)
    assert len(structural) == 3
    assert all(a.category == ArchetypeCategory.STRUCTURAL for a in structural)

    behavioral = get_by_category(ArchetypeCategory.BEHAVIORAL)
    assert len(behavioral) == 3
    assert all(a.category == ArchetypeCategory.BEHAVIORAL for a in behavioral)

    diagnostic = get_by_category(ArchetypeCategory.DIAGNOSTIC)
    assert len(diagnostic) == 3
    assert all(a.category == ArchetypeCategory.DIAGNOSTIC for a in diagnostic)


def test_list_archetype_names():
    names = list_archetype_names()
    assert len(names) == 9
    assert "structural-triad" in names
    assert "pleasure-principle" in names
    assert "ephemeral" in names
    assert "dream-work" in names
    assert "freudian-slip" in names
    assert "fixation" in names


def test_search_archetypes():
    results = search_archetypes("loop")
    assert any(a.name == "repetition-compulsion" for a in results)

    results = search_archetypes("ephemeral")
    assert any(a.name == "ephemeral" for a in results)

    results = search_archetypes("compress")
    assert any(a.name == "dream-work" for a in results)


def test_all_categories_have_archetypes():
    for cat in ArchetypeCategory:
        archetypes = get_by_category(cat)
        assert len(archetypes) >= 1, f"No archetypes for {cat}"


def test_three_by_three_grid():
    """The 9 archetypes form a clean 3x3 grid: 3 categories, 3 each."""
    for cat in ArchetypeCategory:
        assert len(get_by_category(cat)) == 3, (
            f"Expected 3 archetypes for {cat.value}, "
            f"got {len(get_by_category(cat))}"
        )


# ---------------------------------------------------------------------------
# Merged archetype tests
# ---------------------------------------------------------------------------


def test_ephemeral_merges_dream_element_and_psychic_apparatus():
    a = get_archetype("ephemeral")
    assert a is not None
    assert "tree" in a.prompt_fragment.lower() or "tree" in a.description.lower()
    assert "ephemeral" in a.description.lower() or "disappear" in a.prompt_fragment.lower()


def test_pleasure_principle_merges_three_drives():
    a = get_archetype("pleasure-principle")
    assert a is not None
    assert "stop" in a.prompt_fragment.lower()
    assert "speed" in a.prompt_fragment.lower() or "fast" in a.prompt_fragment.lower()


def test_dream_work_merges_three_operations():
    a = get_archetype("dream-work")
    assert a is not None
    desc = a.description.lower()
    assert "condensation" in desc
    assert "displacement" in desc
    assert "secondary revision" in desc


def test_freudian_slip_merges_parapraxis_and_resistance():
    a = get_archetype("freudian-slip")
    assert a is not None
    desc = a.description.lower()
    assert "paraprax" in desc
    assert "resistance" in desc


def test_fixation_merges_cathexis_and_sublimation():
    a = get_archetype("fixation")
    assert a is not None
    desc = a.description.lower()
    assert "cathexis" in desc or "besetzung" in desc
    assert "sublimation" in desc


# ---------------------------------------------------------------------------
# Harness tests
# ---------------------------------------------------------------------------


def test_compose_system_prompt():
    prompt = compose_system_prompt(["structural-triad", "pleasure-principle"])
    assert "structural-triad" in prompt
    assert "pleasure-principle" in prompt
    assert "Id / Ego / Superego" in prompt


def test_compose_system_prompt_with_task():
    prompt = compose_system_prompt(
        ["free-association"],
        task_context="Explore this codebase",
    )
    assert "Explore this codebase" in prompt
    assert "free-association" in prompt


def test_compose_system_prompt_unknown_archetype():
    try:
        compose_system_prompt(["nonexistent"])
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "nonexistent" in str(e)


def test_preset_count():
    assert len(PRESETS) == 5


def test_compose_by_category():
    prompt = compose_by_category([ArchetypeCategory.STRUCTURAL])
    assert "structural-triad" in prompt
    assert "censor-gate" in prompt
    assert "ephemeral" in prompt


def test_compose_full():
    prompt = compose_full()
    for a in ARCHETYPES:
        assert a.name in prompt


def test_compose_preset():
    for preset_name in PRESETS:
        prompt = compose_preset(preset_name)
        assert len(prompt) > 100
        assert "Operating Principles" in prompt


def test_compose_preset_unknown():
    try:
        compose_preset("nonexistent")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "nonexistent" in str(e)


def test_preset_archetypes_exist():
    """Every archetype referenced in a preset must exist in the registry."""
    for preset_name, arch_names in PRESETS.items():
        for name in arch_names:
            assert get_archetype(name) is not None, (
                f"Preset {preset_name!r} references unknown archetype {name!r}"
            )


# ---------------------------------------------------------------------------
# Relationship and referential integrity tests
# ---------------------------------------------------------------------------


def test_related_archetypes_bidirectional():
    """If A lists B as related, B must list A. All references must be valid."""
    for a in ARCHETYPES:
        for related_name in a.related_archetypes:
            related = get_archetype(related_name)
            assert related is not None, (
                f"Archetype {a.name!r} references unknown archetype {related_name!r}"
            )
            assert a.name in related.related_archetypes, (
                f"{a.name!r} lists {related_name!r} as related, "
                f"but {related_name!r} does not list {a.name!r} back"
            )


def test_new_jsonl_entries(entries):
    """The 3 new JSONL entries load correctly."""
    topics = [e.core_topic for e in entries]
    assert "Topographic Model and Psychic Apparatus" in topics
    assert "Neural Architecture and Information Processing" in topics
    assert "Memory Systems and Deferred Meaning" in topics
