"""
Persistence layer for extracciones.

Upserts one row into the extracciones table using the output of
orchestrator.extract.run_extraction() + orchestrator.validate.validate_extraction().

ON CONFLICT (licitacion_id) DO UPDATE is used intentionally: re-running
extraction for the same licitacion replaces the old result, not ignores it.
"""
from __future__ import annotations

from typing import Any

import psycopg2.extras

from .extract import strip_internal_fields
from .validate import validate_extraction


def persist_extraccion(
    conn,
    *,
    licitacion_id: int,
    nomenclatura: str,
    licitacion: dict,
    extraction_result: dict,
    modelo: str | None = None,
    doc_tipo: str | None = None,
    commit: bool = True,
) -> dict[str, Any]:
    """
    Validate and upsert one row into extracciones.

    Parameters
    ----------
    conn:
        psycopg2 connection with autocommit=False.
    licitacion_id:
        FK into licitaciones.  Never NULL (enforced by UNIQUE constraint).
    nomenclatura:
        Stored verbatim for the idx_extracciones_nomenclatura index.
    licitacion:
        Dict of licitacion columns used for validation (nomenclatura, entidad,
        objeto_de_contratacion, descripcion, fecha_publicacion).
    extraction_result:
        Dict from orchestrator.extract.run_extraction():
        {"job_id", "status", "result", "error"}.
    modelo:
        AI model identifier, e.g. "haiku-4-5".  Optional.
    doc_tipo:
        Document type tag, e.g. "bases_admin".  Optional.
    commit:
        Pass False in tests so the caller controls the transaction boundary.

    Returns
    -------
    {"id": int, "estado": str, "issues": dict | None}
    """
    # 1. Validate
    validation = validate_extraction(licitacion, extraction_result)
    estado = validation["estado"]
    issues = validation["issues"]

    # 2. Build clean JSONB payload
    raw_result = extraction_result.get("result") or {}
    extraccion_json = strip_internal_fields(raw_result)

    # 3. Upsert — DO UPDATE replaces old rows so re-extractions are reflected
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO extracciones
              (licitacion_id, nomenclatura, extraccion, modelo, doc_tipo,
               estado, validation_issues, fecha)
            VALUES
              (%(licitacion_id)s, %(nomenclatura)s, %(extraccion)s::jsonb,
               %(modelo)s, %(doc_tipo)s,
               %(estado)s, %(validation_issues)s::jsonb, NOW())
            ON CONFLICT (licitacion_id) DO UPDATE SET
              nomenclatura      = EXCLUDED.nomenclatura,
              extraccion        = EXCLUDED.extraccion,
              modelo            = EXCLUDED.modelo,
              doc_tipo          = EXCLUDED.doc_tipo,
              estado            = EXCLUDED.estado,
              validation_issues = EXCLUDED.validation_issues,
              fecha             = EXCLUDED.fecha
            RETURNING id
            """,
            {
                "licitacion_id":    licitacion_id,
                "nomenclatura":     nomenclatura,
                "extraccion":       psycopg2.extras.Json(extraccion_json),
                "modelo":           modelo,
                "doc_tipo":         doc_tipo,
                "estado":           estado,
                "validation_issues": psycopg2.extras.Json(issues) if issues else None,
            },
        )
        row = cur.fetchone()

    if commit:
        conn.commit()

    return {"id": row["id"], "estado": estado, "issues": issues}
