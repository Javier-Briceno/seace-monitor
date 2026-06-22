"""
Manual integration smoke: B (ingestion layer) → C (extraction) → D (validation + persistence).

Proves all three Python modules work end-to-end:
  1. A synthetic smoke licitacion is upserted into licitaciones (idempotent).
  2. A local fixture PDF is submitted to pdf-extractor (real API call, ~$0.05).
  3. The result is validated.
  4. A row is persisted into extracciones (real commit, NOT a rollback).

The row is tagged  doc_tipo='smoke'  for easy identification and cleanup.

Cost: ~$0.05 per run (Mistral OCR + Claude Haiku on a ~115-page PDF).

─── Usage ──────────────────────────────────────────────────────────────────
From project root (inside Docker — recommended):
    docker-compose run --rm orchestrator python -m orchestrator.tests.smoke_b_c_d

From host (requires PG_HOST=localhost, EXTRACTOR_URL=http://localhost:8010):
    PG_HOST=localhost EXTRACTOR_URL=http://localhost:8010 \\
    python -m orchestrator.tests.smoke_b_c_d

─── Cleanup ─────────────────────────────────────────────────────────────────
Remove just the extracciones smoke row (licitacion stays — it's harmless):
    docker exec postgres psql -U javier -d seace \\
      -c "DELETE FROM extracciones WHERE doc_tipo = 'smoke';"

Remove both (licitacion cascade-deletes extracciones):
    docker exec postgres psql -U javier -d seace \\
      -c "DELETE FROM licitaciones WHERE nomenclatura LIKE 'SMOKE-%';"
"""
from __future__ import annotations

import os
import sys
import time

# ── Smoke fixture ─────────────────────────────────────────────────────────────
# Path relative to /app/ inside the pdf-extractor container (seace_downloads/ is
# mounted at /app/downloads/).  Confirmed working in smoke_extract.py (41 s, 115 pp).
_SMOKE_PDF = "downloads/06b3fa52-61b7-4c63-9bca-66a1ee1d2008_BASES_LPA_032026_MIRADOR_SAN_CRISTOBASL.pdf"

# Synthetic licitacion for the smoke run.  Values are deterministic so the
# INSERT is idempotent (ON CONFLICT on nomenclatura+entidad+fecha_publicacion).
_SMOKE_NOM   = "SMOKE-BCD-2026-ORCHESTRATOR"
_SMOKE_ENT   = "ENTIDAD SMOKE TEST"
_SMOKE_FECHA = "2026-01-01"

# ── ANSI colours ──────────────────────────────────────────────────────────────
_G = "\033[92m"   # green
_R = "\033[91m"   # red
_Y = "\033[93m"   # yellow
_B = "\033[96m"   # cyan / bold
_X = "\033[0m"    # reset


def _ok(msg: str)   -> None: print(f"  {_G}✓{_X}  {msg}")
def _fail(msg: str) -> None: print(f"  {_R}✗{_X}  {msg}");
def _info(msg: str) -> None: print(f"      {msg}")
def _sec(title: str)-> None: print(f"\n{_B}── {title} {'─'*(60-len(title))}{_X}")


# ── Step helpers ──────────────────────────────────────────────────────────────

def _ensure_smoke_licitacion(conn) -> tuple[int, dict]:
    """
    Upsert the synthetic smoke licitacion and return (id, licitacion_row_dict).
    Safe to call multiple times — ON CONFLICT DO NOTHING makes it idempotent.
    """
    from datetime import datetime

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO licitaciones
              (nomenclatura, entidad, fecha_publicacion,
               objeto_de_contratacion, descripcion, departamento, scraped_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (nomenclatura, entidad, fecha_publicacion) DO NOTHING
            """,
            (
                _SMOKE_NOM, _SMOKE_ENT, _SMOKE_FECHA,
                "CONSTRUCCION DE OBRA VIAL",
                "Smoke test de integración B→C→D (puede eliminarse)",
                "LIMA",
            ),
        )
        cur.execute(
            "SELECT id FROM licitaciones WHERE nomenclatura=%s AND entidad=%s",
            (_SMOKE_NOM, _SMOKE_ENT),
        )
        lic_id = cur.fetchone()["id"]
    conn.commit()

    licitacion_row = {
        "nomenclatura":           _SMOKE_NOM,
        "entidad":                _SMOKE_ENT,
        "objeto_de_contratacion": "CONSTRUCCION DE OBRA VIAL",
        "descripcion":            "Smoke test de integración B→C→D",
        "fecha_publicacion":      datetime(2026, 1, 1),
    }
    return lic_id, licitacion_row


def _check_extractor(client) -> bool:
    try:
        h = client.health()
        _ok(f"pdf-extractor reachable → {h}")
        return True
    except Exception as exc:
        _fail(f"Cannot reach pdf-extractor: {exc}")
        return False


def _run_extraction(cfg, file_path: str) -> dict:
    """Submit to pdf-extractor and poll with visible progress."""
    from orchestrator.clients.extractor import ExtractorClient, ExtractionTimeout

    client = ExtractorClient(cfg)
    t0 = time.monotonic()

    job_id = client.submit(file_path)
    _ok(f"Submitted — job_id = {job_id}")

    print("      Polling", end="", flush=True)
    deadline = time.monotonic() + 660
    job = None
    while time.monotonic() < deadline:
        job = client.job_status(job_id)
        status  = job.get("status", "?")
        progress = job.get("progress", "?")
        print(f" [{status}/{progress}%]", end="", flush=True)
        if status in ("done", "error"):
            break
        time.sleep(10)
    print()

    elapsed = time.monotonic() - t0
    if job is None:
        raise RuntimeError("No job response received before timeout")

    # Normalise — job_status may return result as JSON string (Redis decode)
    import json as _json
    raw = job.get("result")
    if isinstance(raw, str):
        try:
            raw = _json.loads(raw)
        except Exception:
            pass
    job["result"] = raw  # normalised

    status = job.get("status")
    if status == "done":
        _ok(f"Extraction done in {elapsed:.0f}s")
    else:
        _fail(f"Extraction ended with status={status} in {elapsed:.0f}s")

    return {
        "job_id": job_id,
        "status": status,
        "result": raw,
        "error":  job.get("error"),
    }


def _verify_no_internal_fields(conn, extraccion_id: int) -> bool:
    """Return True if no _-prefixed keys are present in the persisted JSONB."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT extraccion FROM extracciones WHERE id = %s",
            (extraccion_id,),
        )
        extraccion = cur.fetchone()["extraccion"]
    internal = [k for k in (extraccion or {}) if k.startswith("_")]
    if internal:
        _fail(f"Internal keys found in persisted extraccion: {internal}")
        return False
    _ok("No internal (_-prefixed) fields in persisted extraccion")
    return True


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print(f"\n{_B}{'='*68}{_X}")
    print(f"{_B}  SEACE Orchestrator — Integration Smoke B→C→D{_X}")
    print(f"{_B}{'='*68}{_X}")

    # ── Load config ───────────────────────────────────────────────────────────
    try:
        from orchestrator.config import load as load_cfg
        cfg = load_cfg()
    except RuntimeError as exc:
        _fail(f"Config error: {exc}")
        return 1

    extractor_url = os.getenv("EXTRACTOR_URL", cfg.extractor_url)
    # Allow override so the script also works from the host (localhost:8010)
    from orchestrator.config import Config
    cfg = Config(
        pg_host=cfg.pg_host, pg_port=cfg.pg_port, pg_db=cfg.pg_db,
        pg_user=cfg.pg_user, pg_password=cfg.pg_password,
        redis_url=cfg.redis_url,
        runner_url=cfg.runner_url, runner_token=cfg.runner_token,
        extractor_url=extractor_url,
    )

    # ── Connect to Postgres ───────────────────────────────────────────────────
    _sec("Setup")
    try:
        from orchestrator.db import get_connection
        conn = get_connection(cfg)
        conn.autocommit = False
        _ok(f"Connected to postgres ({cfg.pg_host}:{cfg.pg_port}/{cfg.pg_db})")
    except Exception as exc:
        _fail(f"Cannot connect to postgres: {exc}")
        return 1

    # ── Verify pdf-extractor ──────────────────────────────────────────────────
    from orchestrator.clients.extractor import ExtractorClient
    if not _check_extractor(ExtractorClient(cfg)):
        return 1

    # ── B: Ensure smoke licitacion ────────────────────────────────────────────
    _sec("B — Licitacion")
    try:
        lic_id, lic_row = _ensure_smoke_licitacion(conn)
        _ok(f"Smoke licitacion ready — id={lic_id}  nomenclatura={_SMOKE_NOM}")
    except Exception as exc:
        _fail(f"Failed to upsert smoke licitacion: {exc}")
        conn.close()
        return 1

    _info(f"entidad:              {lic_row['entidad']}")
    _info(f"objeto:               {lic_row['objeto_de_contratacion']}")
    _info(f"fecha_publicacion:    {lic_row['fecha_publicacion'].date()}")
    _info(f"document (fixture):   {_SMOKE_PDF}")

    # ── C: Extraction ─────────────────────────────────────────────────────────
    _sec("C — Extraction  (Mistral OCR + Claude Haiku, ~40–70 s)")
    try:
        extraction_result = _run_extraction(cfg, _SMOKE_PDF)
    except Exception as exc:
        _fail(f"Extraction raised: {exc}")
        conn.close()
        return 1

    result = extraction_result.get("result") or {}
    stats  = result.get("stats") or {}
    _info(f"total_pages:          {stats.get('total_pages')}")
    _info(f"subset_pages:         {stats.get('subset_pages')}")
    _info(f"ANEXO at page:        {stats.get('anexo_page')}")
    _info(f"markdown chars:       {stats.get('markdown_chars')}")
    _info(f"regex fields:         {stats.get('regex_fields_count')}")

    # Report key extracted fields
    KEY_FIELDS = [
        "valor_referencial_monto",
        "plazo_ejecucion_dias",
        "modalidad_pago",
        "factores_evaluacion",
        "equipamiento_estrategico",
        "otras_penalidades",
    ]
    print()
    for field in KEY_FIELDS:
        val = result.get(field)
        if val is not None:
            snippet = str(val.get("texto_original", val) if isinstance(val, dict) else val)[:60]
            _ok(f"{field:<32} = {snippet}")
        else:
            _info(f"{field:<32} = null (not extracted — not an error)")

    # ── D: Validation ─────────────────────────────────────────────────────────
    _sec("D — Validation")
    from orchestrator.validate import validate_extraction
    validation = validate_extraction(lic_row, extraction_result)
    estado = validation["estado"]
    issues = validation["issues"] or {}

    if estado == "ok":
        _ok(f"estado = ok  (0 issues)")
    elif estado == "revision_requerida":
        _info(f"{_Y}estado = revision_requerida  ({len(issues)} issue(s)){_X}")
        for k, v in issues.items():
            _info(f"  • {k}: {v}")
    else:
        _fail(f"estado = {estado}")
        for k, v in issues.items():
            _info(f"  • {k}: {v}")

    # ── D: Persistence ────────────────────────────────────────────────────────
    _sec("D — Persistence  (real commit, doc_tipo='smoke')")
    try:
        from orchestrator.persist import persist_extraccion
        persisted = persist_extraccion(
            conn,
            licitacion_id=lic_id,
            nomenclatura=_SMOKE_NOM,
            licitacion=lic_row,
            extraction_result=extraction_result,
            modelo="mistral-ocr + haiku-4-5",
            doc_tipo="smoke",
            commit=True,
        )
        _ok(f"Persisted — extracciones.id = {persisted['id']}")
        _ok(f"estado stored:               {persisted['estado']}")
        if persisted["issues"]:
            _info(f"validation_issues: {persisted['issues']}")
        else:
            _ok("validation_issues = NULL")
    except Exception as exc:
        _fail(f"Persistence failed: {exc}")
        conn.close()
        return 1

    # ── Verify internal fields not persisted ─────────────────────────────────
    clean = _verify_no_internal_fields(conn, persisted["id"])

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{_B}{'='*68}{_X}")
    ok = (extraction_result["status"] in ("done", "error")) and clean
    if ok:
        print(f"{_G}  B→C→D smoke PASSED{_X}")
    else:
        print(f"{_R}  B→C→D smoke FAILED — see errors above{_X}")
    print(f"{_B}{'='*68}{_X}")

    # ── DB verification hints ─────────────────────────────────────────────────
    print(f"""
DB verification:
  docker exec postgres psql -U javier -d seace -c \\
    "SELECT id, nomenclatura, estado, validation_issues, fecha \\
     FROM extracciones WHERE doc_tipo = 'smoke';"

Cleanup (optional):
  docker exec postgres psql -U javier -d seace \\
    -c "DELETE FROM licitaciones WHERE nomenclatura LIKE 'SMOKE-%';"
""")

    conn.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
