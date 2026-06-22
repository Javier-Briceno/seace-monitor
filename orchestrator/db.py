"""
Thin Postgres helpers for the orchestrator.
All interaction with the `seace` database goes through here.
"""
import psycopg2
import psycopg2.extras

from .config import Config


def get_connection(cfg: Config) -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=cfg.pg_host,
        port=cfg.pg_port,
        dbname=cfg.pg_db,
        user=cfg.pg_user,
        password=cfg.pg_password,
        connect_timeout=5,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def check_connection(cfg: Config) -> None:
    """Raises on failure; silent on success."""
    with get_connection(cfg) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            row = cur.fetchone()
            if row["ok"] != 1:
                raise RuntimeError("Unexpected result from SELECT 1")
