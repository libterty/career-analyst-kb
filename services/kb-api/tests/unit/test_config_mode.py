"""Unit tests for AppSettings.mode (services/kb-api/src/core/config.py).

Controls whether AgenticRAGPipeline uses the legacy inline
self-reflection loop ("Agentic", default) or the Graph-based
implementation ("Graph") — see docs/graph-design/graph-migration-plan.md.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.config import AppSettings

_DB_URL = "postgresql+asyncpg://user:pass@localhost/db"


def test_mode_defaults_to_agentic():
    settings = AppSettings(database_url=_DB_URL)
    assert settings.mode == "Agentic"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Agentic", "Agentic"),
        ("agentic", "Agentic"),
        ("AGENTIC", "Agentic"),
        ("Graph", "Graph"),
        ("graph", "Graph"),
        ("GRAPH", "Graph"),
    ],
)
def test_mode_is_case_insensitive(raw: str, expected: str):
    settings = AppSettings(database_url=_DB_URL, mode=raw)
    assert settings.mode == expected


def test_mode_rejects_invalid_value():
    with pytest.raises(ValidationError):
        AppSettings(database_url=_DB_URL, mode="bogus")
