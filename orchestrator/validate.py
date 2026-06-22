"""
Validation module for extraction results.

Takes a licitacion row dict and an extraction_result dict (from
orchestrator.extract.run_extraction) and returns a validation report.

No database access — pure functions, easily unit-testable.
"""
from __future__ import annotations

from typing import Any


def validate_extraction(
    licitacion: dict,
    extraction_result: dict,
) -> dict[str, Any]:
    """
    Validate an extraction result against its parent licitacion row.

    Parameters
    ----------
    licitacion:
        Dict containing at minimum the licitaciones columns:
        nomenclatura, entidad, objeto_de_contratacion, descripcion,
        fecha_publicacion.  fecha_publicacion is expected to be a Python
        datetime (as returned by psycopg2 for TIMESTAMP columns) or None.
    extraction_result:
        Dict returned by orchestrator.extract.run_extraction():
        {"job_id", "status", "result", "error"}.

    Returns
    -------
    {
        "estado":  "ok" | "revision_requerida" | "error",
        "issues":  dict | None,   # None when estado == "ok"
    }
    """
    # ── Extraction-level failure takes precedence ─────────────────────────────
    if extraction_result.get("status") == "error":
        return {
            "estado": "error",
            "issues": {"extraction_error": extraction_result.get("error")},
        }

    issues: dict[str, str] = {}
    result: dict = extraction_result.get("result") or {}

    # ── Substantively empty result ────────────────────────────────────────────
    # A done job whose cleaned result has no keys besides the guaranteed stats
    # dict (or is outright empty) means the extractor ran but extracted nothing.
    # Internal _-prefixed keys are ignored; they are stripped before persistence.
    useful_keys = {k for k in result if not k.startswith("_") and k != "stats"}
    if not useful_keys:
        issues["extraccion"] = "La extracción no contiene campos útiles"

    # ── Critical licitacion fields ────────────────────────────────────────────
    if not licitacion.get("nomenclatura"):
        issues["nomenclatura"] = "Nomenclatura ausente"

    if not licitacion.get("entidad"):
        issues["entidad"] = "Entidad ausente"

    # objeto / descripcion: at least one must be non-empty
    if not licitacion.get("objeto_de_contratacion") and not licitacion.get("descripcion"):
        issues["objeto_descripcion"] = "Objeto de contratación y descripción ausentes"

    # fecha_publicacion: stored as TIMESTAMP by ingest layer; None = unparseable or absent.
    # NOTE: Postgres UNIQUE allows multiple NULLs, so a NULL fecha_publicacion is a data
    # quality issue worth flagging even though it doesn't break the unique constraint.
    if licitacion.get("fecha_publicacion") is None:
        issues["fecha_publicacion"] = "Fecha de publicación ausente o inválida"

    # ── Format checks on extraction fields ────────────────────────────────────
    monto = result.get("valor_referencial_monto")
    if monto is not None:
        try:
            if float(monto) <= 0:
                issues["valor_referencial_monto"] = (
                    f"Monto debe ser positivo (got {monto})"
                )
        except (TypeError, ValueError):
            issues["valor_referencial_monto"] = (
                f"Monto no es un número válido: {monto!r}"
            )

    plazo = result.get("plazo_ejecucion_dias")
    if plazo is not None:
        # bool is a subclass of int in Python; exclude it explicitly.
        valid = (
            isinstance(plazo, int)
            and not isinstance(plazo, bool)
            and plazo > 0
        )
        if not valid:
            issues["plazo_ejecucion_dias"] = (
                f"Plazo debe ser entero positivo (got {plazo!r})"
            )

    # ── Derive estado ─────────────────────────────────────────────────────────
    if issues:
        return {"estado": "revision_requerida", "issues": issues}
    return {"estado": "ok", "issues": None}
