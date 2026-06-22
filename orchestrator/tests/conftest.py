"""
Pytest configuration for orchestrator DB tests.

Each test gets a fresh connection inside a rolled-back transaction, so no
test data survives between tests and nothing is left in the DB after the suite.

Required env vars (set these before running):
  PG_PASSWORD   postgres password for user 'javier'

Optional overrides (defaults work when running on the host machine):
  PG_HOST       default: localhost  (postgres port 5432 is host-bound)
  PG_PORT       default: 5432
  PG_DB         default: seace
  PG_USER       default: javier
"""
import json
import os
from pathlib import Path

import psycopg2
import psycopg2.extras
import pytest

_FIXTURES = Path(__file__).parent / "fixtures"


def _connect():
    return psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", "5432")),
        dbname=os.getenv("PG_DB", "seace"),
        user=os.getenv("PG_USER", "javier"),
        password=os.environ["PG_PASSWORD"],
        connect_timeout=5,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


@pytest.fixture(scope="function")
def db_conn():
    """
    Yields a psycopg2 connection inside an open transaction.
    Rolls back unconditionally after each test — DB state is never persisted.
    """
    if not os.environ.get("PG_PASSWORD"):
        pytest.skip("PG_PASSWORD not set; export it to run DB tests")

    try:
        conn = _connect()
    except psycopg2.OperationalError as exc:
        pytest.skip(f"Cannot reach postgres: {exc}")

    conn.autocommit = False
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture(scope="session")
def export_sample() -> dict:
    """Load the synthetic /seace/export fixture once for the whole session."""
    with open(_FIXTURES / "export_sample.json", encoding="utf-8") as fh:
        return json.load(fh)
