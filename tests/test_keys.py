"""Tests for deterministic surrogate key generation (keys.py).

The key contract comes from the star-schema reference pattern: sha256/32
(SHA-256 hexdigest truncated to 32 chars) over pipe-joined natural key
parts, NULL-safe via "-1" sentinel. Deterministic keys are what make
transcript re-ingestion idempotent.
"""

from freud_schema.keys import KEY_ALGORITHM, dimension_key, hash_diff


class TestDimensionKey:
    def test_deterministic(self):
        assert dimension_key("a", "b") == dimension_key("a", "b")

    def test_is_sha256_32_hex(self):
        key = dimension_key("freud", "extraction")
        assert len(key) == 32
        assert all(c in "0123456789abcdef" for c in key)

    def test_order_sensitive(self):
        assert dimension_key("a", "b") != dimension_key("b", "a")

    def test_none_is_null_safe(self):
        # None maps to the "-1" sentinel, so it produces a stable key
        assert dimension_key("a", None) == dimension_key("a", None)
        assert dimension_key("a", None) == dimension_key("a", "-1")

    def test_none_differs_from_empty_string(self):
        assert dimension_key("a", None) != dimension_key("a", "")

    def test_non_string_parts_coerced(self):
        assert dimension_key("skill", 3) == dimension_key("skill", "3")

    def test_single_part(self):
        import hashlib

        assert dimension_key("only") == hashlib.sha256(b"only").hexdigest()[:32]

    def test_pipe_join(self):
        import hashlib

        assert dimension_key("a", "b") == hashlib.sha256(b"a|b").hexdigest()[:32]

    def test_golden_natural_key(self):
        import hashlib

        assert dimension_key("insurance", "extract") == (
            hashlib.sha256(b"insurance|extract").hexdigest()[:32]
        )

    def test_golden_null_sentinel(self):
        import hashlib

        assert dimension_key(None) == hashlib.sha256(b"-1").hexdigest()[:32]

    def test_key_algorithm_constant(self):
        assert KEY_ALGORITHM == "sha256/32"


class TestHashDiff:
    def test_deterministic(self):
        assert hash_diff(a=1, b="x") == hash_diff(a=1, b="x")

    def test_key_order_irrelevant(self):
        # Attributes are sorted by name before hashing
        assert hash_diff(b="x", a=1) == hash_diff(a=1, b="x")

    def test_value_change_changes_hash(self):
        assert hash_diff(a=1) != hash_diff(a=2)

    def test_none_values_skipped(self):
        # A None attribute is absent, not a sentinel -- adding a None
        # field to a row must not change its content hash
        assert hash_diff(a=1, b=None) == hash_diff(a=1)

    def test_is_sha256_32_hex(self):
        h = hash_diff(content="rule text", priority=10)
        assert len(h) == 32
        assert all(c in "0123456789abcdef" for c in h)
