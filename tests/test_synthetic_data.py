"""Guards on the public synthetic corpus (data/synthetic/).

Three properties matter: the generator is deterministic, the manifest
matches what is on disk, and the cross-source references the README
advertises (the corpus's whole value for eval) actually hold. Event
streams must also flow through the real ingest path idempotently.
"""

import csv
import importlib.util
from pathlib import Path

import orjson
import pytest

from freud_schema.ingest import ingest_events
from freud_schema.tables import CorrectionType

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS = REPO_ROOT / "data" / "synthetic"
GENERATOR = REPO_ROOT / "scripts" / "generate_synthetic_data.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_synthetic_data", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def manifest() -> dict:
    return orjson.loads((CORPUS / "MANIFEST.json").read_bytes())


@pytest.fixture(scope="module")
def tickets() -> list[dict]:
    path = CORPUS / "saas" / "tickets" / "support_tickets.jsonl"
    return [orjson.loads(line) for line in path.read_bytes().splitlines()
            if line.strip()]


@pytest.fixture(scope="module")
def issues() -> list[dict]:
    data = orjson.loads(
        (CORPUS / "saas" / "project_mgmt" / "issues.json").read_bytes())
    return data["issues"]


def test_manifest_matches_disk(manifest):
    on_disk = {p.relative_to(CORPUS).as_posix()
               for p in CORPUS.rglob("*")
               if p.is_file() and p.name != "MANIFEST.json"}
    in_manifest = {f["path"] for f in manifest["files"]}
    assert on_disk == in_manifest
    assert all(f["source_system"] != "unclassified" for f in manifest["files"])


def test_generator_is_deterministic(tmp_path):
    gen = _load_generator()
    gen.generate(tmp_path / "a")
    gen.generate(tmp_path / "b")
    files_a = sorted(p.relative_to(tmp_path / "a").as_posix()
                     for p in (tmp_path / "a").rglob("*") if p.is_file())
    files_b = sorted(p.relative_to(tmp_path / "b").as_posix()
                     for p in (tmp_path / "b").rglob("*") if p.is_file())
    assert files_a == files_b
    for rel in files_a:
        assert (tmp_path / "a" / rel).read_bytes() == \
            (tmp_path / "b" / rel).read_bytes(), rel


def test_event_streams_ingest_idempotently(store):
    first = ingest_events(store, root=CORPUS / "events")
    assert first["streams"] == 4
    assert first["rows_written"] > 500
    second = ingest_events(store, root=CORPUS / "events")
    assert second["rows_written"] == 0
    assert second["rows_skipped"] == second["rows_read"]


def test_event_lines_match_adapter_shape():
    for stream in sorted((CORPUS / "events").glob("*.jsonl")):
        for line in stream.read_bytes().splitlines():
            row = orjson.loads(line)
            assert row["id"] and row["type"] and row["actor"], stream.name
            # Adapter tolerates bad timestamps; the corpus should not have any.
            assert row["timestamp"].endswith("Z"), stream.name


def test_ticket_references_resolve(tickets, issues):
    issue_keys = {i["key"] for i in issues}
    with open(CORPUS / "saas" / "crm" / "accounts.csv", encoding="utf-8") as f:
        account_ids = {r["account_id"] for r in csv.DictReader(f)}
    for t in tickets:
        assert t["account_id"] in account_ids, t["ticket_id"]
        if t["linked_issue"]:
            assert t["linked_issue"] in issue_keys, t["ticket_id"]


def test_issue_sprints_resolve(issues):
    sprints = orjson.loads(
        (CORPUS / "saas" / "project_mgmt" / "sprints.json").read_bytes())
    sprint_ids = {s["sprint_id"] for s in sprints}
    for i in issues:
        if i["sprint"]:
            assert i["sprint"] in sprint_ids, i["key"]


def test_feedback_references_resolve(tickets):
    ticket_ids = {t["ticket_id"] for t in tickets}
    with open(CORPUS / "feedback" / "csat_survey.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            assert r["ticket_id"] in ticket_ids, r["response_id"]

    corrections_path = CORPUS / "feedback" / "annotation_corrections.jsonl"
    valid_types = {c.value for c in CorrectionType}
    for line in corrections_path.read_bytes().splitlines():
        c = orjson.loads(line)
        assert c["correction_type"] in valid_types, c["correction_id"]
        assert (CORPUS / c["source_path"]).is_file(), c["source_path"]


def test_incident_anchors_hold(tickets):
    """The 2026-03-11 incident narrative the README promises."""
    by_id = {t["ticket_id"]: t for t in tickets}
    assert by_id["SUP-1042"]["linked_issue"] == "ACME-231"
    assert by_id["SUP-1042"]["satisfaction_score"] == 4
    assert "INV-202603-0063" in by_id["SUP-1063"]["messages"][0]["body"]

    with open(CORPUS / "relational" / "invoices.csv", encoding="utf-8") as f:
        disputed = [r for r in csv.DictReader(f)
                    if r["invoice_id"] == "INV-202603-0063"]
    assert disputed and disputed[0]["status"] == "past_due"

    log = (CORPUS / "unstructured" / "logs" /
           "api-gateway-2026-03-11.log").read_text(encoding="utf-8")
    assert "status=502" in log and "consumer_lag_high" in log
