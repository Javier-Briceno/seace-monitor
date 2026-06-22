"""
HTTP client for the pdf-extractor FastAPI service.
"""
import httpx

from ..config import Config

_TIMEOUT = 10


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
