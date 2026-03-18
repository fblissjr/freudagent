"""Shared fixtures for experiment harness tests."""

import pytest

from freud_schema.db import connect
from freud_schema.store import ExperimentStore


@pytest.fixture
def store():
    """In-memory DuckDB store for each test."""
    with ExperimentStore(connect(":memory:")) as s:
        yield s
