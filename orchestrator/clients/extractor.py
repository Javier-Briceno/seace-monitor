"""
HTTP client for the pdf-extractor FastAPI service.
"""
import time

import httpx

from ..config import Config

_TIMEOUT = 10
_TERMINAL = frozenset({"done", "error"})


class ExtractionTimeout(Exception):
    """Raised when a job does not reach a terminal state within the allowed window."""


class ExtractorClient:
    def __init__(self, cfg: Config) -> None:
        self._base = cfg.extractor_url.rstrip("/")

    def health(self) -> dict:
        with httpx.Client(timeout=_TIMEOUT) as c:
            r = c.get(f"{self._base}/health")
            r.raise_for_status()
            return r.json()

    def submit(self, file_path: str) -> str:
        """POST /extract → returns jobId string."""
        with httpx.Client(timeout=_TIMEOUT) as c:
            r = c.post(f"{self._base}/extract", json={"filePath": file_path})
            r.raise_for_status()
            return r.json()["jobId"]

    def job_status(self, job_id: str) -> dict:
        """GET /jobs/{job_id}."""
        with httpx.Client(timeout=_TIMEOUT) as c:
            r = c.get(f"{self._base}/jobs/{job_id}")
            r.raise_for_status()
            return r.json()

    def poll_until_done(
        self,
        job_id: str,
        *,
        poll_interval: int = 10,
        max_wait: int = 600,
        _sleep=time.sleep,
    ) -> dict:
        """
        Poll GET /jobs/{job_id} until status is 'done' or 'error'.

        Returns the final job dict unchanged so callers can inspect both outcomes.
        Raises ExtractionTimeout if max_wait seconds elapse before a terminal state.

        _sleep is injectable (pass a no-op in tests to skip real waits).
        """
        deadline = time.monotonic() + max_wait
        while time.monotonic() < deadline:
            job = self.job_status(job_id)
            if job.get("status") in _TERMINAL:
                return job
            _sleep(poll_interval)
        raise ExtractionTimeout(f"job {job_id} did not finish within {max_wait}s")
