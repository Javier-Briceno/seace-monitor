"""
Unit tests for orchestrator extraction machinery.

All HTTP calls are mocked — no real pdf-extractor or Celery needed.
Tests verify:
  - poll_until_done() halts on terminal statuses
  - ExtractionTimeout is raised when the job stalls
  - run_extraction() normalises the result dict
  - error results are surfaced, not dropped
  - strip_internal_fields() removes all _-prefixed keys
  - strip_markdown() backward-compat alias works
"""
from unittest.mock import MagicMock, patch, call
import pytest

from orchestrator.clients.extractor import ExtractorClient, ExtractionTimeout
from orchestrator.extract import (
    run_extraction,
    strip_internal_fields,
    strip_markdown,
    EXPECTED_FIELDS,
)
from orchestrator.config import Config


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _cfg() -> Config:
    """Minimal config for tests — URLs point nowhere real."""
    return Config(
        pg_host="localhost",
        pg_port=5432,
        pg_db="seace",
        pg_user="javier",
        pg_password="test",
        redis_url="redis://localhost:6379/0",
        runner_url="http://vpn:3000",
        runner_token="tok",
        extractor_url="http://pdf-extractor:8000",
    )


def _make_client(cfg: Config | None = None) -> ExtractorClient:
    return ExtractorClient(cfg or _cfg())


# ─── poll_until_done() tests ──────────────────────────────────────────────────

class TestPollUntilDone:
    def test_returns_immediately_on_done(self):
        client = _make_client()
        done_job = {"status": "done", "progress": "100", "result": {"stats": {}}}
        client.job_status = MagicMock(return_value=done_job)

        result = client.poll_until_done("job-abc", _sleep=lambda s: None)

        assert result["status"] == "done"
        client.job_status.assert_called_once_with("job-abc")

    def test_returns_after_intermediate_statuses(self):
        client = _make_client()
        sequence = [
            {"status": "queued",     "progress": "0"},
            {"status": "ocr",        "progress": "40"},
            {"status": "done",       "progress": "100", "result": {"stats": {}}},
        ]
        client.job_status = MagicMock(side_effect=sequence)
        calls_to_sleep = []

        result = client.poll_until_done("job-abc", _sleep=calls_to_sleep.append)

        assert result["status"] == "done"
        assert client.job_status.call_count == 3
        assert len(calls_to_sleep) == 2  # slept before 2nd and 3rd polls

    def test_returns_immediately_on_error(self):
        client = _make_client()
        error_job = {"status": "error", "progress": "0", "error": "API key missing"}
        client.job_status = MagicMock(return_value=error_job)

        result = client.poll_until_done("job-err", _sleep=lambda s: None)

        assert result["status"] == "error"
        assert result["error"] == "API key missing"

    def test_raises_timeout_when_job_stalls(self):
        client = _make_client()
        in_progress = {"status": "ocr", "progress": "40"}
        client.job_status = MagicMock(return_value=in_progress)

        # max_wait=0 triggers timeout on the first check
        with pytest.raises(ExtractionTimeout, match="job-stall"):
            client.poll_until_done("job-stall", max_wait=0, _sleep=lambda s: None)

    def test_sleep_called_with_poll_interval(self):
        client = _make_client()
        sequence = [
            {"status": "ocr", "progress": "40"},
            {"status": "done", "progress": "100", "result": {}},
        ]
        client.job_status = MagicMock(side_effect=sequence)
        slept = []

        client.poll_until_done("j", poll_interval=15, _sleep=slept.append)

        assert slept == [15]


# ─── run_extraction() tests ───────────────────────────────────────────────────

class TestRunExtraction:
    def _patch(self, submit_return="job-001", job_return=None):
        """Return a pair (submit_mock, job_status_mock) pre-configured."""
        if job_return is None:
            job_return = {
                "status": "done",
                "progress": "100",
                "result": {
                    "factores_evaluacion": None,
                    "otras_penalidades": None,
                    "equipamiento_estrategico": None,
                    "garantia_fiel_cumplimiento_pct": 10.0,
                    "stats": {"total_pages": 115, "subset_pages": 60, "file_size_mb": 1.5},
                    "_markdown": "# Some markdown content",
                },
            }
        return submit_return, job_return

    def test_returns_normalised_dict_on_success(self):
        cfg = _cfg()
        sub_rv, job_rv = self._patch()

        with patch.object(ExtractorClient, "submit", return_value=sub_rv), \
             patch.object(ExtractorClient, "job_status", return_value=job_rv):
            out = run_extraction(cfg, "downloads/test.pdf", _sleep=lambda s: None)

        assert out["status"] == "done"
        assert out["job_id"] == "job-001"
        assert isinstance(out["result"], dict)
        assert out["error"] is None

    def test_result_contains_stats(self):
        cfg = _cfg()
        sub_rv, job_rv = self._patch()

        with patch.object(ExtractorClient, "submit", return_value=sub_rv), \
             patch.object(ExtractorClient, "job_status", return_value=job_rv):
            out = run_extraction(cfg, "downloads/test.pdf", _sleep=lambda s: None)

        assert "stats" in out["result"]
        assert out["result"]["stats"]["total_pages"] == 115

    def test_error_surfaced_in_return_value(self):
        cfg = _cfg()
        err_job = {"status": "error", "progress": "0", "error": "[permanent] MISTRAL_API_KEY missing"}

        with patch.object(ExtractorClient, "submit", return_value="job-err"), \
             patch.object(ExtractorClient, "job_status", return_value=err_job):
            out = run_extraction(cfg, "downloads/test.pdf", _sleep=lambda s: None)

        assert out["status"] == "error"
        assert "MISTRAL_API_KEY" in out["error"]
        assert out["result"] is None

    def test_timeout_propagates(self):
        cfg = _cfg()

        with patch.object(ExtractorClient, "submit", return_value="job-slow"), \
             patch.object(ExtractorClient, "job_status", return_value={"status": "ocr"}):
            with pytest.raises(ExtractionTimeout):
                run_extraction(cfg, "downloads/test.pdf", max_wait=0, _sleep=lambda s: None)

    def test_result_json_string_is_parsed(self):
        """job_status may return result as a JSON string from Redis decode."""
        import json
        cfg = _cfg()
        inner = {"stats": {"total_pages": 90}, "garantia_fiel_cumplimiento_pct": 10.0}
        job_rv = {"status": "done", "progress": "100", "result": json.dumps(inner)}

        with patch.object(ExtractorClient, "submit", return_value="job-j"), \
             patch.object(ExtractorClient, "job_status", return_value=job_rv):
            out = run_extraction(cfg, "downloads/test.pdf", _sleep=lambda s: None)

        assert isinstance(out["result"], dict)
        assert out["result"]["stats"]["total_pages"] == 90


# ─── strip_internal_fields() tests ───────────────────────────────────────────

class TestStripInternalFields:
    def test_removes_markdown(self):
        result = {"stats": {}, "_markdown": "# heading\n\ntext", "valor_referencial_monto": 500000.0}
        cleaned = strip_internal_fields(result)
        assert "_markdown" not in cleaned
        assert "stats" in cleaned
        assert "valor_referencial_monto" in cleaned

    def test_removes_haiku_debug_keys(self):
        result = {
            "stats": {},
            "factores_evaluacion": None,
            "_haiku_general_parse_error": True,
            "_haiku_general_raw": "{ broken json",
            "_haiku_factores_parse_error": True,
            "_haiku_factores_error": "timeout",
            "_haiku_general_error": "HTTP 500",
        }
        cleaned = strip_internal_fields(result)
        for key in list(result):
            if key.startswith("_"):
                assert key not in cleaned, f"expected {key!r} to be stripped"
        assert "stats" in cleaned
        assert "factores_evaluacion" in cleaned

    def test_preserves_public_fields(self):
        public = {
            "valor_referencial_monto": 1_000_000.0,
            "plazo_ejecucion_dias": 90,
            "modalidad_pago": "SUMA ALZADA",
            "stats": {"total_pages": 100},
        }
        result = {**public, "_markdown": "...", "_haiku_general_error": "err"}
        assert strip_internal_fields(result) == public

    def test_original_dict_not_mutated(self):
        result = {"stats": {}, "_markdown": "big text"}
        strip_internal_fields(result)
        assert "_markdown" in result

    def test_returns_copy_not_same_object(self):
        result = {"stats": {}}
        assert strip_internal_fields(result) is not result

    def test_no_op_when_no_internal_keys(self):
        result = {"stats": {}, "valor_referencial_monto": 500000.0}
        assert strip_internal_fields(result) == result


# ─── strip_markdown() backward-compat alias ───────────────────────────────────

class TestStripMarkdownAlias:
    def test_alias_removes_markdown(self):
        result = {"stats": {}, "_markdown": "# heading"}
        cleaned = strip_markdown(result)
        assert "_markdown" not in cleaned
        assert "stats" in cleaned

    def test_alias_also_removes_haiku_keys(self):
        result = {"stats": {}, "_markdown": "x", "_haiku_general_error": "err"}
        cleaned = strip_markdown(result)
        assert "_haiku_general_error" not in cleaned


# ─── EXPECTED_FIELDS sanity check ─────────────────────────────────────────────

def test_expected_fields_list():
    assert "factores_evaluacion" in EXPECTED_FIELDS
    assert "otras_penalidades" in EXPECTED_FIELDS
    assert "equipamiento_estrategico" in EXPECTED_FIELDS
    assert "stats" in EXPECTED_FIELDS
