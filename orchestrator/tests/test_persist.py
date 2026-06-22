"""
Integration tests for orchestrator.persist.persist_extraccion().

Require a live Postgres connection; tests are skipped if PG_PASSWORD is not set.
Each test runs inside a rolled-back transaction — no data survives after the suite.
"""
from datetime import datetime

import pytest

from orchestrator.persist import persist_extraccion


# ─── Fixtures ─────────────────────────────────────────────────────────────────

_NOMENCLATURA = "LPA-PERSIST-TEST-2026-MDH/CS"
_ENTIDAD      = "ENTIDAD PERSIST TEST"


def _insert_licitacion(cur, nomenclatura=_NOMENCLATURA) -> int:
    """Insert a minimal licitacion and return its id."""
    cur.execute(
        """
        INSERT INTO licitaciones (nomenclatura, entidad, fecha_publicacion,
                                  objeto_de_contratacion, descripcion)
        VALUES (%s, %s, '2026-03-01', 'OBRA PERSIST TEST', 'Descripcion test')
        RETURNING id
        """,
        (nomenclatura, _ENTIDAD),
    )
    return cur.fetchone()["id"]


def _lic_row(nomenclatura=_NOMENCLATURA) -> dict:
    """Matching licitacion dict for validation checks."""
    return {
        "nomenclatura":           nomenclatura,
        "entidad":                _ENTIDAD,
        "objeto_de_contratacion": "OBRA PERSIST TEST",
        "descripcion":            "Descripcion test",
        "fecha_publicacion":      datetime(2026, 3, 1),
    }


def _ok_extraction() -> dict:
    """Extraction result that should pass all validation checks."""
    return {
        "status": "done",
        "job_id": "test-job-abc",
        "result": {
            "valor_referencial_monto": 750_000.0,
            "plazo_ejecucion_dias":    90,
            "stats":                   {"total_pages": 115, "subset_pages": 50},
            "_markdown":               "# Should NOT be persisted",
            "_haiku_general_error":    "debug info that must be stripped",
        },
        "error": None,
    }


# ─── Basic insert / estado ────────────────────────────────────────────────────

def test_inserts_row_with_ok_estado(db_conn):
    with db_conn.cursor() as cur:
        lic_id = _insert_licitacion(cur)

    out = persist_extraccion(
        db_conn,
        licitacion_id=lic_id,
        nomenclatura=_NOMENCLATURA,
        licitacion=_lic_row(),
        extraction_result=_ok_extraction(),
        modelo="haiku-4-5",
        doc_tipo="bases_admin",
        commit=False,
    )

    assert out["estado"] == "ok"
    assert out["issues"] is None
    assert isinstance(out["id"], int) and out["id"] > 0


def test_revision_requerida_when_entidad_missing(db_conn):
    with db_conn.cursor() as cur:
        lic_id = _insert_licitacion(cur)

    lic = _lic_row()
    lic["entidad"] = None

    out = persist_extraccion(
        db_conn,
        licitacion_id=lic_id,
        nomenclatura=_NOMENCLATURA,
        licitacion=lic,
        extraction_result=_ok_extraction(),
        commit=False,
    )

    assert out["estado"] == "revision_requerida"
    assert "entidad" in out["issues"]


def test_error_estado_persisted(db_conn):
    with db_conn.cursor() as cur:
        lic_id = _insert_licitacion(cur)

    err_result = {
        "status": "error",
        "result": None,
        "error": "[permanent] MISTRAL_API_KEY not set",
    }

    out = persist_extraccion(
        db_conn,
        licitacion_id=lic_id,
        nomenclatura=_NOMENCLATURA,
        licitacion=_lic_row(),
        extraction_result=err_result,
        commit=False,
    )

    assert out["estado"] == "error"
    assert "extraction_error" in out["issues"]

    # Verify DB row
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT estado, validation_issues FROM extracciones WHERE id = %s",
            (out["id"],),
        )
        row = cur.fetchone()

    assert row["estado"] == "error"
    assert row["validation_issues"]["extraction_error"] is not None


# ─── Internal fields must not be persisted ────────────────────────────────────

def test_internal_fields_not_in_persisted_extraccion(db_conn):
    with db_conn.cursor() as cur:
        lic_id = _insert_licitacion(cur)

    out = persist_extraccion(
        db_conn,
        licitacion_id=lic_id,
        nomenclatura=_NOMENCLATURA,
        licitacion=_lic_row(),
        extraction_result=_ok_extraction(),
        commit=False,
    )

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT extraccion FROM extracciones WHERE id = %s", (out["id"],)
        )
        extraccion = cur.fetchone()["extraccion"]

    # psycopg2 deserialises JSONB to a Python dict automatically
    assert isinstance(extraccion, dict)
    internal = [k for k in extraccion if k.startswith("_")]
    assert internal == [], f"Internal keys found in persisted extraccion: {internal}"


def test_public_fields_are_preserved(db_conn):
    with db_conn.cursor() as cur:
        lic_id = _insert_licitacion(cur)

    out = persist_extraccion(
        db_conn,
        licitacion_id=lic_id,
        nomenclatura=_NOMENCLATURA,
        licitacion=_lic_row(),
        extraction_result=_ok_extraction(),
        commit=False,
    )

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT extraccion FROM extracciones WHERE id = %s", (out["id"],)
        )
        extraccion = cur.fetchone()["extraccion"]

    assert extraccion["valor_referencial_monto"] == 750_000.0
    assert extraccion["plazo_ejecucion_dias"] == 90
    assert "stats" in extraccion


# ─── Upsert behaviour (ON CONFLICT DO UPDATE) ────────────────────────────────

def test_upsert_updates_existing_row(db_conn):
    with db_conn.cursor() as cur:
        lic_id = _insert_licitacion(cur)

    # First extraction
    out1 = persist_extraccion(
        db_conn,
        licitacion_id=lic_id,
        nomenclatura=_NOMENCLATURA,
        licitacion=_lic_row(),
        extraction_result=_ok_extraction(),
        commit=False,
    )

    # Second extraction — different monto
    result2 = _ok_extraction()
    result2["result"]["valor_referencial_monto"] = 999_999.0

    out2 = persist_extraccion(
        db_conn,
        licitacion_id=lic_id,
        nomenclatura=_NOMENCLATURA,
        licitacion=_lic_row(),
        extraction_result=result2,
        commit=False,
    )

    assert out1["id"] == out2["id"], "ON CONFLICT should update the same row, not insert a new one"

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT extraccion FROM extracciones WHERE id = %s", (out2["id"],)
        )
        extraccion = cur.fetchone()["extraccion"]

    assert extraccion["valor_referencial_monto"] == 999_999.0


def test_upsert_only_one_row_per_licitacion(db_conn):
    with db_conn.cursor() as cur:
        lic_id = _insert_licitacion(cur)

    for _ in range(3):
        persist_extraccion(
            db_conn,
            licitacion_id=lic_id,
            nomenclatura=_NOMENCLATURA,
            licitacion=_lic_row(),
            extraction_result=_ok_extraction(),
            commit=False,
        )

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS n FROM extracciones WHERE licitacion_id = %s",
            (lic_id,),
        )
        count = cur.fetchone()["n"]

    assert count == 1


# ─── metadata columns ─────────────────────────────────────────────────────────

def test_modelo_and_doc_tipo_stored(db_conn):
    with db_conn.cursor() as cur:
        lic_id = _insert_licitacion(cur)

    out = persist_extraccion(
        db_conn,
        licitacion_id=lic_id,
        nomenclatura=_NOMENCLATURA,
        licitacion=_lic_row(),
        extraction_result=_ok_extraction(),
        modelo="haiku-4-5",
        doc_tipo="bases_admin",
        commit=False,
    )

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT modelo, doc_tipo FROM extracciones WHERE id = %s", (out["id"],)
        )
        row = cur.fetchone()

    assert row["modelo"] == "haiku-4-5"
    assert row["doc_tipo"] == "bases_admin"


def test_validation_issues_stored_as_jsonb(db_conn):
    with db_conn.cursor() as cur:
        lic_id = _insert_licitacion(cur)

    r = _ok_extraction()
    r["result"]["valor_referencial_monto"] = -1

    out = persist_extraccion(
        db_conn,
        licitacion_id=lic_id,
        nomenclatura=_NOMENCLATURA,
        licitacion=_lic_row(),
        extraction_result=r,
        commit=False,
    )

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT validation_issues FROM extracciones WHERE id = %s", (out["id"],)
        )
        row = cur.fetchone()

    # psycopg2 deserialises JSONB to Python dict
    assert isinstance(row["validation_issues"], dict)
    assert "valor_referencial_monto" in row["validation_issues"]


def test_validation_issues_null_when_ok(db_conn):
    with db_conn.cursor() as cur:
        lic_id = _insert_licitacion(cur)

    out = persist_extraccion(
        db_conn,
        licitacion_id=lic_id,
        nomenclatura=_NOMENCLATURA,
        licitacion=_lic_row(),
        extraction_result=_ok_extraction(),
        commit=False,
    )

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT validation_issues FROM extracciones WHERE id = %s", (out["id"],)
        )
        row = cur.fetchone()

    assert row["validation_issues"] is None


def test_error_row_persists_empty_extraccion(db_conn):
    """Error-status rows have result=None; extraccion must be stored as {} (NOT NULL)."""
    with db_conn.cursor() as cur:
        lic_id = _insert_licitacion(cur)

    err_result = {"status": "error", "result": None, "error": "[permanent] API key missing"}

    out = persist_extraccion(
        db_conn,
        licitacion_id=lic_id,
        nomenclatura=_NOMENCLATURA,
        licitacion=_lic_row(),
        extraction_result=err_result,
        commit=False,
    )

    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT extraccion FROM extracciones WHERE id = %s", (out["id"],)
        )
        extraccion = cur.fetchone()["extraccion"]

    assert extraccion == {}


def test_upsert_flips_estado_on_rerun(db_conn):
    """Rerunning extraction for the same licitacion updates estado and issues in place."""
    with db_conn.cursor() as cur:
        lic_id = _insert_licitacion(cur)

    # First run: extraction failed
    err_result = {"status": "error", "result": None, "error": "API timeout"}
    out1 = persist_extraccion(
        db_conn,
        licitacion_id=lic_id,
        nomenclatura=_NOMENCLATURA,
        licitacion=_lic_row(),
        extraction_result=err_result,
        commit=False,
    )
    assert out1["estado"] == "error"

    # Second run: extraction succeeded
    out2 = persist_extraccion(
        db_conn,
        licitacion_id=lic_id,
        nomenclatura=_NOMENCLATURA,
        licitacion=_lic_row(),
        extraction_result=_ok_extraction(),
        commit=False,
    )
    assert out2["estado"] == "ok"
    assert out1["id"] == out2["id"], "ON CONFLICT must update the same row"

    # Verify DB reflects the latest run
    with db_conn.cursor() as cur:
        cur.execute(
            "SELECT estado, validation_issues FROM extracciones WHERE id = %s",
            (out2["id"],),
        )
        row = cur.fetchone()

    assert row["estado"] == "ok"
    assert row["validation_issues"] is None
