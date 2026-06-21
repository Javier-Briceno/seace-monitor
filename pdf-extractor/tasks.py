"""
tasks.py — Task Celery principal de extracción.

Flujo completo por documento:
  1. Detectar ANEXO Nº 1 con header-only OCR (~1s)
  2. Recortar sub-PDF (págs 18 → ANEXO) con PyMuPDF
  3. Enviar sub-PDF a Mistral OCR → Markdown (~35s)
  4. Regex → ~60% de campos (~0s)
  5. Claude Haiku texto → ~40% restante (~8s)
  6. Guardar resultado en Redis

Jobs persisten 24h en Redis (result_expires=86400 en worker.py).
"""

import os
import asyncio
import json
import pymupdf
import redis

from worker import celery_app
from ocr import find_anexo_page, build_subset_pdf, extract_with_mistral
from extract import extract_regex_fields, extract_semantic_fields

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
DOWNLOADS_BASE = "/app/downloads"

# Cliente Redis para guardar el progreso del job (separado del result backend de Celery)
# Usamos un hash por job_id: {status, progress, result, error}
_redis_client = None

def get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def update_job(job_id: str, status: str, progress: int, result=None, error=None):
    """Actualiza el estado del job en Redis. FastAPI lo lee en GET /jobs/{id}."""
    r = get_redis()
    data = {"status": status, "progress": progress}
    if result is not None:
        data["result"] = json.dumps(result)
    if error is not None:
        data["error"] = error
    r.hset(f"job:{job_id}", mapping=data)
    r.expire(f"job:{job_id}", 86400)  # TTL 24h
    print(f"[{job_id[:8]}] [{progress}%] {status}")


def get_job_status(job_id: str) -> dict | None:
    """Lee el estado del job desde Redis."""
    r = get_redis()
    data = r.hgetall(f"job:{job_id}")
    if not data:
        return None
    if "result" in data:
        try:
            data["result"] = json.loads(data["result"])
        except Exception:
            pass
    return data


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30, queue="extraction")
def process_document(self, job_id: str, file_path: str):
    """
    Task principal. Llamada por FastAPI vía .apply_async().
    bind=True permite acceder a self para reintentos.
    """
    try:
        # Validar path traversal
        abs_path = os.path.realpath(f"/app/{file_path}")
        allowed = os.path.realpath(DOWNLOADS_BASE)
        if not abs_path.startswith(allowed):
            update_job(job_id, "error", 0, error="Access denied")
            return

        if not os.path.exists(abs_path):
            update_job(job_id, "error", 0, error=f"File not found: {file_path}")
            return

        file_size_mb = os.path.getsize(abs_path) / (1024 * 1024)
        print(f"[{job_id[:8]}] Procesando: {file_path} ({file_size_mb:.1f} MB)")

        # ── Etapa 1: Detectar ANEXO Nº 1 ─────────────────────────────────────
        update_job(job_id, "detecting_anexo", 10)
        doc = pymupdf.open(abs_path)
        total_pages = len(doc)
        anexo_page = find_anexo_page(doc)

        # ── Etapa 2: Recortar sub-PDF ─────────────────────────────────────────
        update_job(job_id, "building_subset", 25)
        pdf_bytes = build_subset_pdf(doc, anexo_page)
        doc.close()
        subset_pages = len(pymupdf.open(stream=pdf_bytes, filetype="pdf"))

        # ── Etapa 3: Mistral OCR ──────────────────────────────────────────────
        update_job(job_id, "ocr", 40)
        markdown = asyncio.run(extract_with_mistral(pdf_bytes))

        # ── Etapa 4: Regex ────────────────────────────────────────────────────
        update_job(job_id, "regex_extraction", 70)
        regex_fields = extract_regex_fields(markdown)

        # ── Etapa 5: Claude Haiku ─────────────────────────────────────────────
        update_job(job_id, "semantic_extraction", 85)
        semantic_fields = extract_semantic_fields(markdown, regex_fields)

        # ── Resultado final ───────────────────────────────────────────────────
        result = {
            **regex_fields,
            **semantic_fields,
            "stats": {
                "total_pages": total_pages,
                "subset_pages": subset_pages,
                "anexo_page": (anexo_page + 1) if anexo_page is not None else None,
                "markdown_chars": len(markdown),
                "regex_fields_count": len(regex_fields),
                "file_size_mb": round(file_size_mb, 2),
            },
            # El Markdown completo lo incluimos para que n8n pueda verificar citas
            "_markdown": markdown,
        }

        update_job(job_id, "done", 100, result=result)
        print(f"[{job_id[:8]}] COMPLETADO — {total_pages} págs totales, {subset_pages} procesadas")
        return result

    except Exception as exc:
        error_msg = str(exc)
        print(f"[{job_id[:8]}] ERROR: {error_msg}")
        update_job(job_id, "error", 0, error=error_msg)
        # Reintento automático con backoff de 30s
        raise self.retry(exc=exc)
