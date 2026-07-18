"""Guards on the public synthetic corpus (data/synthetic/).

Several properties matter: the generator is deterministic, the manifest
matches what is on disk, and the cross-source references the README
advertises (the corpus's whole value for eval) actually hold. Event
streams must also flow through the real ingest path idempotently.

Two safety guards form a dual pair, because data/synthetic/ is
public-by-construction (the manifest inventories whatever lands there):
- test_manifest_paths_are_git_tracked -- completeness: nothing the manifest
  lists may be silently gitignored (a fresh clone must have every file).
- test_no_private_data_in_corpus -- safety: nothing under the corpus may
  carry a real email, routable IP, home path, or secret-shaped token.
"""

import csv
import importlib.util
import ipaddress
import re
import subprocess
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
    assert spec and spec.loader
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


# ---------------------------------------------------------------------------
# Safety guards -- data/synthetic/ is public-by-construction (dual pair)
# ---------------------------------------------------------------------------


def test_manifest_paths_are_git_tracked(manifest):
    """Completeness: every manifest path must be git-tracked. A broad
    .gitignore rule that silently drops a corpus file -- while the manifest
    still lists it -- leaves a fresh clone with a missing file (happened 3x:
    the internal/ subtree, then *.log eating the incident log). Catch it here
    instead of on someone's cold checkout. Skips outside a git work tree
    (installed wheel / export tarball) so it never false-fails there."""
    inside = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=REPO_ROOT, capture_output=True, text=True)
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        pytest.skip("not a git work tree")
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", "data/synthetic"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    tracked = set(out.stdout.split("\0")) - {""}
    untracked = [f["path"] for f in manifest["files"]
                 if f"data/synthetic/{f['path']}" not in tracked]
    assert not untracked, (
        "manifest lists files git does not track (gitignored? check "
        f".gitignore): {untracked}")


# Emails in the corpus use the reserved .example TLD by convention. A leak
# would be a *routable* address, i.e. one on a real public TLD -- so flag a
# non-.example email only when its TLD is a real one. This ignores both the
# reserved suffix and intentional garbage (the messy/ocr/ fixtures truncate
# .example to .exa on purpose) without a per-file exemption.
_REAL_TLDS = frozenset((
    "com", "net", "org", "io", "co", "ai", "edu", "gov", "mil", "biz",
    "info", "dev", "app", "cloud", "tech", "xyz", "me", "us", "uk", "ca",
    "de", "fr", "jp", "cn", "au", "eu", "in", "nl", "se", "es", "it", "ru",
    "online", "site", "store", "email", "mail",
))
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.([A-Za-z]{2,})\b")
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_HOMEPATH_RE = re.compile(r"/(?:Users|home)/[A-Za-z][A-Za-z0-9._-]+")
_SECRET_RE = re.compile(
    r"AKIA[0-9A-Z]{16}"
    r"|sk-[A-Za-z0-9]{20,}"
    r"|ghp_[A-Za-z0-9]{20,}"
    r"|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
_SCANNED_EXT = {".md", ".txt", ".json", ".jsonl", ".csv", ".sql", ".xml",
                ".ics", ".html", ".eml", ".log", ".yaml", ".yml"}


def _ip_is_public(s: str) -> bool:
    """True only for a real, routable public IP -- the leak we care about.
    Doc ranges (RFC 5737), private, loopback, reserved, and non-IPs (an
    octet > 255, e.g. a version-looking quad) are all fine."""
    try:
        ip = ipaddress.ip_address(s)
    except ValueError:
        return False
    return not (ip.is_private or ip.is_loopback or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified
                or ip in ipaddress.ip_network("203.0.113.0/24")
                or ip in ipaddress.ip_network("198.51.100.0/24")
                or ip in ipaddress.ip_network("192.0.2.0/24"))


def test_no_private_data_in_corpus():
    """Safety: nothing under data/synthetic/ may carry a real (routable)
    email, a public IP, a home path, or a secret-shaped token. This is the
    dual of the completeness guard -- it guards against private data leaking
    *in*, which the manifest/tracked checks do not."""
    violations = []
    for path in sorted(CORPUS.rglob("*")):
        if not path.is_file() or path.suffix not in _SCANNED_EXT:
            continue
        rel = path.relative_to(CORPUS).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        for tld in _EMAIL_RE.findall(text):
            if tld.lower() in _REAL_TLDS:
                violations.append((rel, "email", tld))
        for m in _IP_RE.findall(text):
            if _ip_is_public(m):
                violations.append((rel, "public-ip", m))
        for m in _HOMEPATH_RE.findall(text):
            violations.append((rel, "home-path", m))
        if _SECRET_RE.search(text):
            violations.append((rel, "secret-token", "<redacted>"))
    assert not violations, (
        f"possible private data in the public corpus: {violations[:20]}")
