"""Unit tests for eva-postgres adapter (no live DB required)."""
import json
import sys
import types
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

# Stub psycopg2 so import doesn't fail without the C extension
pg2 = types.ModuleType("psycopg2")
sys.modules.setdefault("psycopg2", pg2)


def test_adapter_imports():
    from eva_postgres.adapter import PostgresStorageAdapter
    assert PostgresStorageAdapter is not None


def test_adapter_init_stores_url():
    with patch("eva_postgres.adapter.create_engine") as mock_eng:
        mock_eng.return_value = MagicMock()
        from eva_postgres.adapter import PostgresStorageAdapter
        adapter = PostgresStorageAdapter(url="postgresql://fake/db")
        mock_eng.assert_called_once_with("postgresql://fake/db")


def test_run_record_model_exists():
    from eva_postgres.adapter import RunRecord
    assert RunRecord.__tablename__ == "eva_runs"
