"""
Orchestrator extraction coordinator.

Wraps pdf-extractor submit + poll into a single call and normalises the result.
Does NOT persist to the database — that belongs to TASK-D (extracciones table).

Canonical result shape is documented in EXTRACTION_SCHEMA.md.
"""
from __future__ import annotations

import time
from typing import Any

from .clients.extractor import ExtractorClient, ExtractionTimeout
from .config import Config

# Re-export so callers only need to import from orchestrator.extract
__all__ = ["run_extraction", "ExtractionTimeout", "EXPECTED_FIELDS", "strip_internal_fields", "strip_markdown"]

# Fields that a healthy extraction result should contain.
# Absence of any individual field does NOT fail extraction — they may be null in the document.
# Named EXPECTED (not REQUIRED) because run_extraction() does not enforce their presence.
EXPECTED_FIELDS = [
    "factores_evaluacion",
    "otras_penalidades",
    "equipamiento_estrategico",
    "stats",
]


def run_extraction(
    cfg: Config,
    file_path: str,
    *,
    poll_interval: int = 10,
    max_wait: int = 600,
    _sleep=time.sleep,
) -> dict[str, Any]:
    """
    Submit *file_path* to pdf-extractor and wait for the job to finish.

    file_path must be relative to /app inside the container, e.g.:
        "downloads/uuid_BASES_LPA.pdf"

    Returns a normalised dict:
    {
        "job_id":  str,
        "status":  "done" | "error",
        "result":  dict | None,   # extraction fields when status=done
        "error":   str  | None,   # error message when status=error
    }

    Raises ExtractionTimeout if the job does not finish within max_wait seconds.
    Never silently drops errors — status="error" is always reflected in the return value.
    """
    client = ExtractorClient(cfg)
    job_id = client.submit(file_path)

    job = client.poll_until_done(
        job_id,
        poll_interval=poll_interval,
        max_wait=max_wait,
        _sleep=_sleep,
    )

    result = job.get("result")
    if isinstance(result, str):
        import json as _json
        try:
            result = _json.loads(result)
        except Exception:
            pass

    return {
        "job_id": job_id,
        "status": job.get("status"),
        "result": result,
        "error": job.get("error"),
    }


def strip_internal_fields(result: dict) -> dict:
    """
    Return a shallow copy of *result* with all internal/debug keys removed.

    Internal keys are those whose names start with '_', e.g.:
      _markdown, _haiku_general_parse_error, _haiku_general_raw,
      _haiku_factores_parse_error, _haiku_factores_error, _haiku_general_error

    Call this before handing the result to TASK-D persistence code; the raw
    OCR markdown alone can be 40–100 KB.
    """
    return {k: v for k, v in result.items() if not k.startswith("_")}


def strip_markdown(result: dict) -> dict:
    """Backward-compatible alias for strip_internal_fields()."""
    return strip_internal_fields(result)
