"""Schema tests for the v0.17 meta-harness dimensional model.

Contract under test:
- MD5 hash surrogate keys everywhere; no sequences remain.
- SCD Type 2 columns on every versioned dimension.
- Lineage columns (record_source, etl_run_id) on every fact.
- Eight new tables: dim_project, dim_facet_type, dim_finding_type,
  fact_message, fact_tool_use, fact_session_facets, fact_finding,
  fact_proposal, plus meta_load_log.
- reset_schema() round-trips.
"""

import duckdb
import pytest

from freud_schema.db import get_schema_version, init_schema, reset_schema


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    init_schema(c)
    yield c
    c.close()


def _tables(con) -> set[str]:
    return {r[0] for r in con.execute(
        "SELECT table_name FROM duckdb_tables()").fetchall()}


def _columns(con, table: str) -> set[str]:
    return {r[1] for r in con.execute(
        f"PRAGMA table_info('{table}')").fetchall()}


DIMS = {"dim_skill", "dim_source", "dim_rule", "dim_sampling_config"}
REGISTRIES = {
    "dim_project", "dim_tenant", "dim_facet_type", "dim_feedback_origin", "dim_finding_type",
    "dim_event_type",
}
FACTS = {
    "fact_session", "fact_trace", "fact_extraction", "fact_feedback",
    "fact_trace_feedback", "fact_message", "fact_tool_use",
    "fact_session_facets", "fact_finding", "fact_proposal", "fact_event",
}
META = {"meta_schema_version", "meta_load_log", "meta_key_algorithm"}


class TestTableInventory:
    def test_all_tables_exist(self, con):
        assert DIMS | REGISTRIES | FACTS | META <= _tables(con)

    def test_inventory_matches_canonical_list(self, con):
        # db.ALL_TABLES / ALL_VIEWS are the single source of truth other
        # consumers (reset_schema, the CLI's db status) iterate -- keep
        # both honest against what the DDL actually creates.
        from freud_schema.db import ALL_TABLES, ALL_VIEWS
        assert set(ALL_TABLES) == DIMS | REGISTRIES | FACTS | META
        assert set(ALL_TABLES) == _tables(con)
        views = {r[0] for r in con.execute(
            "SELECT view_name FROM duckdb_views() WHERE NOT internal").fetchall()}
        assert set(ALL_VIEWS) == views

    def test_no_sequences(self, con):
        seqs = con.execute("SELECT * FROM duckdb_sequences()").fetchall()
        assert seqs == []

    def test_views_exist(self, con):
        views = {r[0] for r in con.execute(
            "SELECT view_name FROM duckdb_views() WHERE NOT internal").fetchall()}
        assert {
            "v_feedback_by_skill", "v_feedback_fields", "v_recurring_traces",
            "v_recurring_trace_feedback", "v_skill_feedback_patterns",
            "v_session_feedback_count",
        } <= views


class TestKeysAndScd2:
    @pytest.mark.parametrize("table,key", [
        ("dim_skill", "skill_key"),
        ("dim_source", "source_key"),
        ("dim_rule", "rule_key"),
        ("dim_sampling_config", "config_key"),
        ("dim_project", "project_key"),
        ("dim_facet_type", "facet_type_key"),
        ("dim_finding_type", "finding_type_key"),
        ("fact_session", "session_key"),
        ("fact_trace", "trace_key"),
        ("fact_extraction", "extraction_key"),
        ("fact_feedback", "feedback_key"),
        ("fact_trace_feedback", "trace_feedback_key"),
        ("fact_message", "message_key"),
        ("fact_tool_use", "tool_use_key"),
        ("fact_session_facets", "facet_row_key"),
        ("fact_finding", "finding_key"),
        ("fact_proposal", "proposal_key"),
    ])
    def test_hash_key_column(self, con, table, key):
        cols = _columns(con, table)
        assert key in cols
        assert "id" not in cols  # integer surrogate ids are gone

    @pytest.mark.parametrize("table", sorted(DIMS))
    def test_scd2_columns_on_dims(self, con, table):
        cols = _columns(con, table)
        assert {"effective_from", "effective_to", "is_current", "hash_diff",
                "record_source"} <= cols
        assert "updated_at" not in cols  # SCD-2 rows close, they don't mutate

    @pytest.mark.parametrize("table", sorted(FACTS))
    def test_lineage_columns_on_facts(self, con, table):
        assert {"record_source", "etl_run_id"} <= _columns(con, table)

    def test_no_session_id_anywhere(self, con):
        # Decided 2026-07-07: session_id is banned from the new DDL --
        # etl_run_id for lineage, session_key for the harness session.
        for table in DIMS | REGISTRIES | FACTS | META:
            assert "session_id" not in _columns(con, table), table


class TestChecksAndConstraints:
    def test_skill_status_check(self, con):
        with pytest.raises(duckdb.ConstraintException):
            con.execute(
                """INSERT INTO dim_skill (skill_key, domain, task_type, content, status)
                   VALUES ('k', 'd', 't', 'c', 'bogus')""")

    def test_record_source_check(self, con):
        with pytest.raises(duckdb.ConstraintException):
            con.execute(
                """INSERT INTO fact_session (session_key, native_session_id, record_source)
                   VALUES ('k', 'n', 'bogus')""")

    def test_proposal_status_check(self, con):
        with pytest.raises(duckdb.ConstraintException):
            con.execute(
                """INSERT INTO fact_proposal (proposal_key, target_dimension,
                   proposed_content, status)
                   VALUES ('k', 'dim_rule', 'c', 'bogus')""")

    def test_finding_type_has_no_check(self, con):
        # finding_type is registry-validated (dim_finding_type), not a CHECK
        # enum -- new vocabularies must be insertable without DDL changes.
        con.execute(
            """INSERT INTO fact_finding (finding_key, finding_type,
               finding_type_key, scope, summary)
               VALUES ('k', 'brand_new_type', 'ftk', 'global', 's')""")
        row = con.execute(
            "SELECT finding_type FROM fact_finding WHERE finding_key = 'k'"
        ).fetchone()
        assert row[0] == "brand_new_type"


class TestMetaAndReset:
    def test_schema_version_is_4(self, con):
        assert get_schema_version(con) >= 4

    def test_meta_load_log_columns(self, con):
        assert {"etl_run_id", "operation", "status", "rows_read",
                "rows_written", "rows_skipped"} <= _columns(con, "meta_load_log")

    def test_reset_schema_round_trip(self, con):
        con.execute(
            """INSERT INTO dim_rule (rule_key, name, content)
               VALUES ('k', 'test-rule', 'text')""")
        reset_schema(con)
        assert con.execute("SELECT COUNT(*) FROM dim_rule").fetchone()[0] == 0
        # Still fully queryable after reset
        assert DIMS | REGISTRIES | FACTS | META <= _tables(con)
        assert get_schema_version(con) >= 4
