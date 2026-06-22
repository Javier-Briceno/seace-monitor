"""
Dependency smoke-check.

Usage (inside container or with deps installed):
    python -m orchestrator.healthcheck
"""
import sys

import redis as redis_lib

from .config import load
from .db import check_connection
from .clients.runner import RunnerClient
from .clients.extractor import ExtractorClient

_GREEN = "\033[92m"
_RED = "\033[91m"
_RESET = "\033[0m"


def _ok(label: str, detail: str = "") -> None:
    suffix = f"  ({detail})" if detail else ""
    print(f"{_GREEN}✓{_RESET}  {label}{suffix}")


def _fail(label: str, err: str) -> None:
    print(f"{_RED}✗{_RESET}  {label}: {err}")


def main() -> int:
    cfg = load()
    failures = 0

    # ── Postgres ──────────────────────────────────────────────────────────────
    try:
        check_connection(cfg)
        _ok("postgres", f"{cfg.pg_host}:{cfg.pg_port}/{cfg.pg_db}")
    except Exception as exc:
        _fail("postgres", str(exc))
        failures += 1

    # ── seace-runner ──────────────────────────────────────────────────────────
    try:
        data = RunnerClient(cfg).health()
        _ok("seace-runner", f"{cfg.runner_url}  →  {data}")
    except Exception as exc:
        _fail("seace-runner", str(exc))
        failures += 1

    # ── pdf-extractor ─────────────────────────────────────────────────────────
    try:
        data = ExtractorClient(cfg).health()
        _ok("pdf-extractor", f"{cfg.extractor_url}  →  {data}")
    except Exception as exc:
        _fail("pdf-extractor", str(exc))
        failures += 1

    # ── Redis ─────────────────────────────────────────────────────────────────
    try:
        r = redis_lib.from_url(cfg.redis_url, socket_timeout=3)
        r.ping()
        _ok("redis", cfg.redis_url)
    except Exception as exc:
        _fail("redis", str(exc))
        failures += 1

    # ── Result ────────────────────────────────────────────────────────────────
    print()
    if failures:
        print(f"{failures} check(s) failed.")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
