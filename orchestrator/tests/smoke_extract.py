"""
Manual smoke test for the extraction engine.

Submits two local fixture PDFs through pdf-extractor and reports whether
the required fields are present in the result.

Cost: ~$0.05–$0.10 per PDF (Mistral OCR + Claude Haiku).
Run only when explicitly verifying the extraction pipeline.

Usage (from project root):
    EXTRACTOR_URL=http://localhost:8010 \\
    RUNNER_TOKEN=dummy PG_PASSWORD=dummy \\
    python -m orchestrator.tests.smoke_extract

Or inside Docker:
    docker-compose run --rm orchestrator \\
      python -m orchestrator.tests.smoke_extract
"""
from __future__ import annotations

import json
import os
import sys
import time

# ── Fixtures ──────────────────────────────────────────────────────────────────
# Relative to /app/downloads/ inside the pdf-extractor container.
# These files must exist in seace_downloads/ on the host (volume-mounted).
FIXTURES = [
    "downloads/06b3fa52-61b7-4c63-9bca-66a1ee1d2008_BASES_LPA_032026_MIRADOR_SAN_CRISTOBASL.pdf",
    "downloads/dccb0053-61db-4ebb-a157-805eb4e868bf_BASES_ADMINISTRATIVAS.pdf",
]

REQUIRED = ["factores_evaluacion", "otras_penalidades", "equipamiento_estrategico", "stats"]

_GREEN = "\033[92m"
_RED   = "\033[91m"
_RESET = "\033[0m"


def _ok(msg: str) -> None:
    print(f"{_GREEN}✓{_RESET}  {msg}")

def _fail(msg: str) -> None:
    print(f"{_RED}✗{_RESET}  {msg}")

def _info(msg: str) -> None:
    print(f"    {msg}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    # Build a minimal config from env
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from orchestrator.config import Config
    from orchestrator.clients.extractor import ExtractorClient, ExtractionTimeout

    # Allow EXTRACTOR_URL override so the script works from the host (localhost:8010)
    # or from inside Docker (pdf-extractor:8000)
    extractor_url = os.getenv("EXTRACTOR_URL", "http://pdf-extractor:8000")
    cfg = Config(
        pg_host="localhost", pg_port=5432, pg_db="seace", pg_user="javier",
        pg_password=os.getenv("PG_PASSWORD", "x"),
        redis_url="redis://localhost:6379/0",
        runner_url="http://vpn:3000",
        runner_token=os.getenv("RUNNER_TOKEN", "x"),
        extractor_url=extractor_url,
    )
    client = ExtractorClient(cfg)

    # Verify service is reachable
    try:
        h = client.health()
        _ok(f"pdf-extractor reachable at {extractor_url}  → {h}")
    except Exception as exc:
        _fail(f"Cannot reach pdf-extractor: {exc}")
        print("Set EXTRACTOR_URL to the correct address, e.g. http://localhost:8010")
        return 1

    overall_ok = True

    for file_path in FIXTURES:
        filename = file_path.split("/")[-1][:60]
        print(f"\n{'─'*70}")
        print(f"  Submitting: {filename}")
        print(f"{'─'*70}")

        t0 = time.monotonic()
        try:
            job_id = client.submit(file_path)
            _ok(f"Submitted — job_id={job_id}")
        except Exception as exc:
            _fail(f"Submit failed: {exc}")
            overall_ok = False
            continue

        # Poll with visible progress dots
        print("  Polling", end="", flush=True)
        try:
            deadline = time.monotonic() + 600
            job = None
            while time.monotonic() < deadline:
                job = client.job_status(job_id)
                status = job.get("status")
                progress = job.get("progress", "?")
                print(f" [{status}/{progress}%]", end="", flush=True)
                if status in ("done", "error"):
                    break
                time.sleep(10)
            print()  # newline after dots
        except KeyboardInterrupt:
            print("\n  Interrupted.")
            return 1
        except Exception as exc:
            print()
            _fail(f"Polling failed: {exc}")
            overall_ok = False
            continue

        elapsed = time.monotonic() - t0

        if job is None or job.get("status") != "done":
            _fail(f"Job ended with status={job.get('status') if job else 'N/A'}: {job.get('error', '')}")
            overall_ok = False
            continue

        _ok(f"Done in {elapsed:.0f}s")

        # Parse result
        raw_result = job.get("result")
        if isinstance(raw_result, str):
            import json as _json
            raw_result = _json.loads(raw_result)

        result = raw_result or {}

        # Stats
        stats = result.get("stats") or {}
        _info(f"pages: {stats.get('total_pages')} total, {stats.get('subset_pages')} processed")
        _info(f"ANEXO found at page: {stats.get('anexo_page')}")
        _info(f"markdown chars: {stats.get('markdown_chars')}")
        _info(f"regex fields: {stats.get('regex_fields_count')}")

        # Check required fields
        for field in REQUIRED:
            val = result.get(field)
            if val is not None:
                if field == "stats":
                    _ok(f"{field} present")
                elif isinstance(val, dict):
                    snippet = str(val.get("texto_original", ""))[:80]
                    _ok(f"{field}: {snippet}")
                else:
                    _ok(f"{field}: {str(val)[:80]}")
            else:
                _info(f"  {field}: null (not found in this document — not an error)")

        # Key numeric fields
        for key in ("valor_referencial_monto", "plazo_ejecucion_dias", "modalidad_pago"):
            if key in result:
                _ok(f"{key} = {result[key]}")

        print(f"\n  Full result keys: {[k for k in result if not k.startswith('_')]}")

    print(f"\n{'═'*70}")
    if overall_ok:
        _ok("All fixture PDFs processed successfully.")
        return 0
    else:
        _fail("One or more fixture PDFs failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
