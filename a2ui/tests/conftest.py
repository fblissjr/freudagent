"""Shared fixtures for a2ui tests."""

import pytest
from bridge import A2UIBridge


@pytest.fixture
def bridge():
    return A2UIBridge()
