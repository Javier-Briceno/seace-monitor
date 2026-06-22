"""
Loads all runtime configuration from environment variables.
No secrets are logged or printed here.
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    pg_host: str
    pg_port: int
    pg_db: str
    pg_user: str
    pg_password: str
    redis_url: str
    runner_url: str
    runner_token: str
    extractor_url: str


def load() -> Config:
    missing = [k for k in ("PG_PASSWORD", "RUNNER_TOKEN") if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    return Config(
        pg_host=os.getenv("PG_HOST", "postgres"),
        pg_port=int(os.getenv("PG_PORT", "5432")),
        pg_db=os.getenv("PG_DB", "seace"),
        pg_user=os.getenv("PG_USER", "javier"),
        pg_password=os.environ["PG_PASSWORD"],
        redis_url=os.getenv("REDIS_URL", "redis://redis:6379/0"),
        runner_url=os.getenv("RUNNER_URL", "http://vpn:3000"),
        runner_token=os.environ["RUNNER_TOKEN"],
        extractor_url=os.getenv("EXTRACTOR_URL", "http://pdf-extractor:8000"),
    )
