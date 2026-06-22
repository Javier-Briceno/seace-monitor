"""
Unit tests for orchestrator.validate.validate_extraction().

No database access — all tests are pure function calls.
"""
from datetime import datetime

import pytest

from orchestrator.validate import validate_extraction


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _lic(**overrides) -> dict:
    """Minimal valid licitacion row (all critical fields present)."""
    base = {
        "nomenclatura":           "LPA-TEST-001-2026-MDH/CS",
        "entidad":                "MUNICIPALIDAD DE HUANCAYO",
        "objeto_de_contratacion": "CONSTRUCCION DE OBRA",
        "descripcion":            "Descripcion detallada",
        "fecha_publicacion":      datetime(2026, 1, 15, 9, 0),
    }
    base.update(overrides)
    return base


def _result(**overrides) -> dict:
    """Minimal valid extraction result (status=done, positive monto and plazo)."""
    base: dict = {
        "status": "done",
        "job_id": "test-job-id",
        "result": {
            "valor_referencial_monto": 1_000_000.0,
            "plazo_ejecucion_dias":    120,
            "stats": {"total_pages": 115},
        },
        "error": None,
    }
    base.update(overrides)
    return base


# ─── Clean extraction ──────────────────────────────────────────────────────────

def test_clean_extraction_is_ok():
    v = validate_extraction(_lic(), _result())
    assert v["estado"] == "ok"
    assert v["issues"] is None


# ─── Empty / substantively empty extraction ───────────────────────────────────

def test_empty_result_is_revision_requerida():
    r = {"status": "done", "job_id": "j", "result": {}, "error": None}
    v = validate_extraction(_lic(), r)
    assert v["estado"] == "revision_requerida"
    assert "extraccion" in v["issues"]


def test_only_stats_result_is_revision_requerida():
    # stats is guaranteed when done, but alone it contains no useful content.
    r = {"status": "done", "job_id": "j",
         "result": {"stats": {"total_pages": 115}}, "error": None}
    v = validate_extraction(_lic(), r)
    assert v["estado"] == "revision_requerida"
    assert "extraccion" in v["issues"]


def test_only_internal_fields_result_is_revision_requerida():
    # A result whose only keys are _-prefixed is effectively empty after stripping.
    r = {"status": "done", "job_id": "j",
         "result": {"_markdown": "big text", "_haiku_general_error": "err"},
         "error": None}
    v = validate_extraction(_lic(), r)
    assert v["estado"] == "revision_requerida"
    assert "extraccion" in v["issues"]


def test_single_useful_field_is_not_empty():
    # One real extracted field is enough; empty-result gate should not fire.
    r = {"status": "done", "job_id": "j",
         "result": {"modalidad_pago": "SUMA ALZADA", "stats": {"total_pages": 60},
                    "_markdown": "x"},
         "error": None}
    v = validate_extraction(_lic(), r)
    # Empty-extraction issue must NOT be present
    assert v.get("issues") is None or "extraccion" not in (v.get("issues") or {})


# ─── Extraction error ──────────────────────────────────────────────────────────

def test_extraction_error_gives_error_estado():
    err = {"status": "error", "result": None, "error": "[permanent] MISTRAL_API_KEY missing"}
    v = validate_extraction(_lic(), err)
    assert v["estado"] == "error"
    assert "extraction_error" in v["issues"]
    assert "MISTRAL_API_KEY" in v["issues"]["extraction_error"]


def test_extraction_error_takes_precedence_over_missing_lic_fields():
    # Even with a completely broken licitacion, extraction error wins.
    err = {"status": "error", "result": None, "error": "boom"}
    v = validate_extraction(_lic(nomenclatura=None, entidad=None), err)
    assert v["estado"] == "error"
    # Only extraction_error issue present, not nomenclatura / entidad
    assert list(v["issues"].keys()) == ["extraction_error"]


# ─── Missing critical licitacion fields ───────────────────────────────────────

def test_missing_nomenclatura_is_revision_requerida():
    v = validate_extraction(_lic(nomenclatura=None), _result())
    assert v["estado"] == "revision_requerida"
    assert "nomenclatura" in v["issues"]


def test_empty_nomenclatura_is_revision_requerida():
    v = validate_extraction(_lic(nomenclatura=""), _result())
    assert v["estado"] == "revision_requerida"
    assert "nomenclatura" in v["issues"]


def test_missing_entidad_is_revision_requerida():
    v = validate_extraction(_lic(entidad=None), _result())
    assert v["estado"] == "revision_requerida"
    assert "entidad" in v["issues"]


def test_empty_entidad_is_revision_requerida():
    v = validate_extraction(_lic(entidad=""), _result())
    assert v["estado"] == "revision_requerida"
    assert "entidad" in v["issues"]


def test_missing_both_objeto_and_descripcion():
    v = validate_extraction(
        _lic(objeto_de_contratacion=None, descripcion=None),
        _result(),
    )
    assert v["estado"] == "revision_requerida"
    assert "objeto_descripcion" in v["issues"]


def test_objeto_present_without_descripcion_is_ok():
    # Either field is sufficient.
    v = validate_extraction(
        _lic(objeto_de_contratacion="OBRA DE AGUA", descripcion=None),
        _result(),
    )
    assert v["estado"] == "ok"


def test_descripcion_present_without_objeto_is_ok():
    v = validate_extraction(
        _lic(objeto_de_contratacion=None, descripcion="Desc"),
        _result(),
    )
    assert v["estado"] == "ok"


def test_missing_fecha_publicacion():
    v = validate_extraction(_lic(fecha_publicacion=None), _result())
    assert v["estado"] == "revision_requerida"
    assert "fecha_publicacion" in v["issues"]


# ─── Monetary value checks ────────────────────────────────────────────────────

def test_null_monto_is_ok():
    r = _result()
    del r["result"]["valor_referencial_monto"]
    v = validate_extraction(_lic(), r)
    assert v["estado"] == "ok"


def test_positive_monto_is_ok():
    r = _result()
    r["result"]["valor_referencial_monto"] = 0.01
    v = validate_extraction(_lic(), r)
    assert v["estado"] == "ok"


def test_zero_monto_is_revision_requerida():
    r = _result()
    r["result"]["valor_referencial_monto"] = 0
    v = validate_extraction(_lic(), r)
    assert v["estado"] == "revision_requerida"
    assert "valor_referencial_monto" in v["issues"]


def test_negative_monto_is_revision_requerida():
    r = _result()
    r["result"]["valor_referencial_monto"] = -500.0
    v = validate_extraction(_lic(), r)
    assert v["estado"] == "revision_requerida"
    assert "valor_referencial_monto" in v["issues"]


def test_nonnumeric_monto_is_revision_requerida():
    r = _result()
    r["result"]["valor_referencial_monto"] = "S/ 1,000,000"
    v = validate_extraction(_lic(), r)
    assert v["estado"] == "revision_requerida"
    assert "valor_referencial_monto" in v["issues"]


# ─── Plazo checks ─────────────────────────────────────────────────────────────

def test_null_plazo_is_ok():
    r = _result()
    del r["result"]["plazo_ejecucion_dias"]
    v = validate_extraction(_lic(), r)
    assert v["estado"] == "ok"


def test_positive_int_plazo_is_ok():
    r = _result()
    r["result"]["plazo_ejecucion_dias"] = 1
    v = validate_extraction(_lic(), r)
    assert v["estado"] == "ok"


def test_zero_plazo_is_revision_requerida():
    r = _result()
    r["result"]["plazo_ejecucion_dias"] = 0
    v = validate_extraction(_lic(), r)
    assert v["estado"] == "revision_requerida"
    assert "plazo_ejecucion_dias" in v["issues"]


def test_negative_plazo_is_revision_requerida():
    r = _result()
    r["result"]["plazo_ejecucion_dias"] = -30
    v = validate_extraction(_lic(), r)
    assert v["estado"] == "revision_requerida"
    assert "plazo_ejecucion_dias" in v["issues"]


def test_float_plazo_is_revision_requerida():
    r = _result()
    r["result"]["plazo_ejecucion_dias"] = 60.5
    v = validate_extraction(_lic(), r)
    assert v["estado"] == "revision_requerida"
    assert "plazo_ejecucion_dias" in v["issues"]


def test_bool_plazo_is_revision_requerida():
    # bool is a subclass of int; True == 1 but should not be valid as a plazo.
    r = _result()
    r["result"]["plazo_ejecucion_dias"] = True
    v = validate_extraction(_lic(), r)
    assert v["estado"] == "revision_requerida"
    assert "plazo_ejecucion_dias" in v["issues"]


# ─── Multiple issues all reported ─────────────────────────────────────────────

def test_multiple_issues_all_reported():
    r = _result()
    r["result"]["valor_referencial_monto"] = -1
    v = validate_extraction(
        _lic(nomenclatura=None, entidad=None, fecha_publicacion=None),
        r,
    )
    assert v["estado"] == "revision_requerida"
    assert "nomenclatura" in v["issues"]
    assert "entidad" in v["issues"]
    assert "fecha_publicacion" in v["issues"]
    assert "valor_referencial_monto" in v["issues"]
    assert len(v["issues"]) >= 4
