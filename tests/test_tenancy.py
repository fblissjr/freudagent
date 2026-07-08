"""Tests for M2+M3: sha256/32 keys and tenant-scoped natural keys.

Contract under test:
- keys.py golden values and KEY_ALGORITHM constant (test_keys.py covers
  the low-level hash contract; this module covers the schema/store
  surface built on top of it).
- dim_tenant registry + meta_key_algorithm self-description, seeded at
  init_schema.
- The four SCD-2 dims (dim_skill, dim_rule, dim_source,
  dim_sampling_config) key off (tenant_id, ...natural key...): two
  tenants can hold the "same" entity without collision.
- Default-tenant back-compat: omitting tenant_id behaves exactly as
  before M3.
- resolve_key() tenant scoping for the four tenant-keyed dims.
"""

import pytest

from freud_schema.keys import dimension_key
from freud_schema.tables import Project, Rule, Skill, SkillStatus


def _skill(**over) -> Skill:
    base = dict(domain="freud", task_type="extraction", content="Extract things.")
    base.update(over)
    return Skill(**base)


class TestInitSchemaSeeds:
    def test_dim_tenant_has_default_row(self, store):
        tenants = store.list_tenants()
        assert len(tenants) == 1
        assert tenants[0].tenant_id == "default"
        assert tenants[0].tenant_key == dimension_key("default")

    def test_meta_key_algorithm_seeded(self, store):
        row = store.con.execute(
            "SELECT algorithm FROM meta_key_algorithm").fetchone()
        assert row is not None
        assert row[0] == "sha256/32"

    def test_init_schema_is_idempotent(self, store):
        # ExperimentStore.__init__ already called init_schema once; calling
        # it again must not duplicate the seed rows.
        from freud_schema.db import init_schema
        init_schema(store.con)
        assert store.con.execute(
            "SELECT COUNT(*) FROM meta_key_algorithm").fetchone()[0] == 1
        assert store.con.execute(
            "SELECT COUNT(*) FROM dim_tenant WHERE tenant_id = 'default'"
        ).fetchone()[0] == 1


class TestTwoTenantCollision:
    def test_same_natural_key_different_tenants_no_collision(self, store):
        key_a = store.insert_skill(_skill(tenant_id="team-a"))
        key_b = store.insert_skill(_skill(tenant_id="team-b"))
        assert key_a != key_b
        assert key_a == dimension_key("team-a", "freud", "extraction")
        assert key_b == dimension_key("team-b", "freud", "extraction")

        skill_a = store.get_skill(key_a)
        skill_b = store.get_skill(key_b)
        assert skill_a.is_current and skill_b.is_current
        assert skill_a.status.value == "draft"
        assert skill_b.status.value == "draft"

    def test_get_active_skill_scopes_by_tenant(self, store):
        store.insert_skill(_skill(tenant_id="team-a", status=SkillStatus.ACTIVE))
        store.insert_skill(_skill(tenant_id="team-b", status=SkillStatus.ACTIVE,
                                   content="Extract differently."))
        found_a = store.get_active_skill("freud", "extraction", tenant_id="team-a")
        found_b = store.get_active_skill("freud", "extraction", tenant_id="team-b")
        assert found_a is not None and found_b is not None
        assert found_a.skill_key != found_b.skill_key
        assert found_a.content == "Extract things."
        assert found_b.content == "Extract differently."
        # Wrong tenant must not see the other tenant's skill
        assert store.get_active_skill("freud", "extraction", tenant_id="team-c") is None

    def test_dim_tenant_gains_a_row_per_new_tenant(self, store):
        store.insert_skill(_skill(tenant_id="team-a"))
        store.insert_skill(_skill(tenant_id="team-b", content="v2"))
        tenants = {t.tenant_id for t in store.list_tenants()}
        assert tenants == {"default", "team-a", "team-b"}
        assert len(store.list_tenants()) == 3


class TestDefaultTenantBackCompat:
    def test_skill_round_trips_without_tenant_arg(self, store):
        skill_key = store.insert_skill(_skill())
        assert skill_key == dimension_key("default", "freud", "extraction")
        found = store.get_active_skill("freud", "extraction")
        assert found is None  # draft, not active -- matches pre-M3 semantics
        store.activate_skill(skill_key)
        found = store.get_active_skill("freud", "extraction")
        assert found is not None
        assert found.skill_key == skill_key
        assert found.tenant_id == "default"

    def test_rule_round_trips_without_tenant_arg(self, store):
        key = store.insert_rule(Rule(name="no-emoji", content="No emojis."))
        assert key == dimension_key("default", "no-emoji")
        rule = store.get_rule(key)
        assert rule.status.value == "active"
        assert rule.tenant_id == "default"
        # insert_rule defaults status=active, scope=global -- get_rules()
        # with no domain and the default tenant finds it, matching pre-M3
        # behavior exactly.
        rules = store.get_rules()
        assert len(rules) == 1
        assert rules[0].rule_key == key


class TestResolveKeyTenantScoping:
    def test_resolve_key_scopes_to_tenant(self, store):
        key_a = store.insert_skill(_skill(tenant_id="team-a"))
        key_b = store.insert_skill(_skill(tenant_id="team-b"))
        # Same domain/task_type means the two keys likely share no common
        # prefix by construction, so use the full key's own prefix scoped
        # by tenant to prove the AND tenant_id clause is applied.
        resolved_a = store.resolve_key("dim_skill", key_a[:8], tenant_id="team-a")
        assert resolved_a == key_a
        resolved_b = store.resolve_key("dim_skill", key_b[:8], tenant_id="team-b")
        assert resolved_b == key_b

    def test_resolve_key_tenant_scoping_excludes_other_tenant(self, store):
        key_a = store.insert_skill(_skill(tenant_id="team-a"))
        with pytest.raises(ValueError, match="[Nn]o .*match"):
            store.resolve_key("dim_skill", key_a[:8], tenant_id="team-b")

    def test_resolve_key_ignores_tenant_for_non_scoped_tables(self, store):
        # dim_project is not in _TENANT_SCOPED_DIMS; passing tenant_id must
        # not raise or filter anything out.
        key = store.ensure_project(Project(project_path="/repo/x"))
        resolved = store.resolve_key("dim_project", key[:8], tenant_id="team-a")
        assert resolved == key
