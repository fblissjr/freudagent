"""Deterministic surrogate key generation for the dimensional model.

SHA-256 hash keys (truncated to 32 hex chars) from natural key components,
per the star-schema reference pattern: deterministic, NULL-safe,
composable. No sequences, no coordination. Any consumer can compute a
row's key without a lookup, which is what makes transcript re-ingestion
idempotent -- re-ingesting the same file computes the same keys and can
skip existing rows.

KEY_ALGORITHM = "sha256/32": full SHA-256 hexdigest truncated to the
first 32 characters -- the same length as the MD5 hex digest this scheme
replaced (v0.23, see CLAUDE.md), so no column width or prefix-resolution
changes were needed. SHA-256 is FIPS-friendly where MD5 is not; the
truncation keeps keys short without giving up the collision margin that
matters at this warehouse's scale. The chosen algorithm is recorded in
meta_key_algorithm so a database self-describes its key scheme.

Two distinct functions, not to be conflated:

- dimension_key() identifies an ENTITY (or a fact event) from its natural
  key parts. SCD-2 dimension rows for the same entity share this key;
  is_current / effective ranges distinguish versions.
- hash_diff() fingerprints a row's CONTENT for change detection. Same
  entity, changed attributes -> different hash_diff -> new SCD-2 row.
"""

from __future__ import annotations

import hashlib

KEY_ALGORITHM = "sha256/32"


def dimension_key(*natural_keys: object) -> str:
    """sha256/32 hex key from pipe-joined natural key parts.

    None maps to the "-1" sentinel (NULL-safe); everything else is
    str()-coerced. Order-sensitive by design.
    """
    parts = [str(k) if k is not None else "-1" for k in natural_keys]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]


def hash_diff(**attributes: object) -> str:
    """sha256/32 hex fingerprint of a row's content for change detection.

    Attributes are sorted by name so call-site ordering is irrelevant.
    None values are skipped entirely: adding a None field to a row must
    not change its content hash.
    """
    parts = [f"{k}={v}" for k, v in sorted(attributes.items()) if v is not None]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:32]
