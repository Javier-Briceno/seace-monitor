"""
HTTP client for the seace-runner Node/Playwright service.
Authenticated routes use Bearer token; /health is open.
"""
import httpx

from ..config import Config

_TIMEOUT = 10


class RunnerClient:
    def __init__(self, cfg: Config) -> None:
        self._base = cfg.runner_url.rstrip("/")
        self._auth = {"Authorization": f"Bearer {cfg.runner_token}"}

    def health(self) -> dict:
        with httpx.Client(timeout=_TIMEOUT) as c:
            r = c.get(f"{self._base}/health")
            r.raise_for_status()
            return r.json()

    def scrape(self, params: dict) -> dict:
        """POST /seace/scrape — authenticated."""
        with httpx.Client(timeout=60) as c:
            r = c.post(f"{self._base}/seace/scrape", json=params, headers=self._auth)
            r.raise_for_status()
            return r.json()
