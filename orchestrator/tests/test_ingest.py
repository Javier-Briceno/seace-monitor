"""
Tests for orchestrator.ingest using the synthetic export_sample fixture.

All tests use the db_conn fixture which rolls back after each test,
so no data is left in the DB between runs.
"""
import pytest

from orchestrator.ingest import ingest_payload, parse_fecha, select_bases_administrativas


# ─── parse_fecha unit tests (no DB needed) ────────────────────────────────────

class TestParseFecha:
    def test_full_datetime(self):
        assert parse_fecha("15/06/2026 09:30") == "2026-06-15T09:30:00"

    def test_date_only(self):
        assert parse_fecha("01/01/2026") == "2026-01-01T00:00:00"

    def test_none(self):
        assert parse_fecha(None) is None

    def test_empty_string(self):
        assert parse_fecha("") is None

    def test_bad_format_returns_none(self):
        assert parse_fecha("not-a-date") is None


# ─── Ingestion tests (require DB) ─────────────────────────────────────────────

class TestIngestPayload:
    def test_inserts_both_licitaciones(self, db_conn, export_sample):
        stats = ingest_payload(db_conn, export_sample, commit=False)

        assert stats["inserted"] == 2
        assert stats["skipped"] == 0

        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT nomenclatura FROM licitaciones WHERE nomenclatura LIKE 'LPA-SM-TEST-%'"
            )
            rows = cur.fetchall()
        nomenclaturas = {r["nomenclatura"] for r in rows}
        assert "LPA-SM-TEST-001-2026-MDH/CS" in nomenclaturas
        assert "LPA-SM-TEST-002-2026-MDH/CS" not in nomenclaturas  # different entity
        assert "LPA-SM-TEST-002-2026-MPT/CS" in nomenclaturas

    def test_cronograma_count(self, db_conn, export_sample):
        stats = ingest_payload(db_conn, export_sample, commit=False)

        # fixture: item 1 has 3 cronograma entries, item 2 has 1
        assert stats["cronograma"] == 4

        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS n FROM cronograma cr
                JOIN licitaciones l ON l.id = cr.licitacion_id
                WHERE l.nomenclatura LIKE 'LPA-SM-TEST-%'
                """
            )
            assert cur.fetchone()["n"] == 4

    def test_documentos_count(self, db_conn, export_sample):
        stats = ingest_payload(db_conn, export_sample, commit=False)

        # fixture: item 1 has 2 docs, item 2 has 1
        assert stats["documentos"] == 3

        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS n FROM documentos d
                JOIN licitaciones l ON l.id = d.licitacion_id
                WHERE l.nomenclatura LIKE 'LPA-SM-TEST-%'
                """
            )
            assert cur.fetchone()["n"] == 3

    def test_convocatoria_inserted(self, db_conn, export_sample):
        ingest_payload(db_conn, export_sample, commit=False)

        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.entidad_convocante FROM convocatoria c
                JOIN licitaciones l ON l.id = c.licitacion_id
                WHERE l.nomenclatura = 'LPA-SM-TEST-001-2026-MDH/CS'
                """
            )
            row = cur.fetchone()
        assert row is not None
        assert row["entidad_convocante"] == "MUNICIPALIDAD DISTRITAL DE HUANCHACO"

    def test_entidad_contratante_inserted(self, db_conn, export_sample):
        ingest_payload(db_conn, export_sample, commit=False)

        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT ec.ruc FROM entidad_contratante ec
                JOIN licitaciones l ON l.id = ec.licitacion_id
                WHERE l.nomenclatura = 'LPA-SM-TEST-001-2026-MDH/CS'
                """
            )
            row = cur.fetchone()
        assert row is not None
        assert row["ruc"] == "20131369477"

    def test_fecha_publicacion_parsed(self, db_conn, export_sample):
        ingest_payload(db_conn, export_sample, commit=False)

        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT fecha_publicacion FROM licitaciones
                WHERE nomenclatura = 'LPA-SM-TEST-001-2026-MDH/CS'
                """
            )
            row = cur.fetchone()
        assert row is not None
        # Postgres returns a datetime; check date portion
        fp = row["fecha_publicacion"]
        assert fp.year == 2026
        assert fp.month == 6
        assert fp.day == 15

    def test_departamento_from_meta(self, db_conn, export_sample):
        ingest_payload(db_conn, export_sample, commit=False)

        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT departamento FROM licitaciones WHERE nomenclatura = 'LPA-SM-TEST-001-2026-MDH/CS'"
            )
            row = cur.fetchone()
        assert row["departamento"] == "LA LIBERTAD"


# ─── Idempotency tests ────────────────────────────────────────────────────────

class TestIdempotency:
    def test_double_ingest_no_duplicates(self, db_conn, export_sample):
        stats1 = ingest_payload(db_conn, export_sample, commit=False)
        stats2 = ingest_payload(db_conn, export_sample, commit=False)

        assert stats1["inserted"] == 2
        assert stats2["inserted"] == 0       # all skipped on second run
        assert stats2["skipped"] == 2

        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM licitaciones WHERE nomenclatura LIKE 'LPA-SM-TEST-%'"
            )
            assert cur.fetchone()["n"] == 2  # still exactly 2

    def test_double_ingest_no_duplicate_children(self, db_conn, export_sample):
        ingest_payload(db_conn, export_sample, commit=False)
        ingest_payload(db_conn, export_sample, commit=False)

        with db_conn.cursor() as cur:
            # cronograma has no unique constraint so only check documentos (uuid unique)
            cur.execute(
                """
                SELECT COUNT(*) AS n FROM documentos d
                JOIN licitaciones l ON l.id = d.licitacion_id
                WHERE l.nomenclatura LIKE 'LPA-SM-TEST-%'
                """
            )
            assert cur.fetchone()["n"] == 3  # exactly 3, not 6


# ─── Child-parent FK tests ────────────────────────────────────────────────────

class TestChildrenLinked:
    def test_cronograma_fk(self, db_conn, export_sample):
        ingest_payload(db_conn, export_sample, commit=False)

        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT cr.etapa FROM cronograma cr
                JOIN licitaciones l ON l.id = cr.licitacion_id
                WHERE l.nomenclatura = 'LPA-SM-TEST-001-2026-MDH/CS'
                ORDER BY cr.id
                """
            )
            etapas = [r["etapa"] for r in cur.fetchall()]

        assert etapas[0] == "Convocatoria"
        assert len(etapas) == 3  # item 1 has 3 stages

    def test_documentos_fk(self, db_conn, export_sample):
        ingest_payload(db_conn, export_sample, commit=False)

        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT d.documento, d.uuid FROM documentos d
                JOIN licitaciones l ON l.id = d.licitacion_id
                WHERE l.nomenclatura = 'LPA-SM-TEST-001-2026-MDH/CS'
                ORDER BY d.nro
                """
            )
            rows = cur.fetchall()

        assert len(rows) == 2
        assert rows[0]["documento"] == "Bases Administrativas"
        assert rows[0]["uuid"] == "fixture-aaaa-bbbb-cccc-0001"
        assert rows[1]["documento"] == "Expediente Técnico"

    def test_no_children_for_licitacion_from_other_item(self, db_conn, export_sample):
        ingest_payload(db_conn, export_sample, commit=False)

        with db_conn.cursor() as cur:
            cur.execute(
                """
                SELECT d.documento FROM documentos d
                JOIN licitaciones l ON l.id = d.licitacion_id
                WHERE l.nomenclatura = 'LPA-SM-TEST-002-2026-MPT/CS'
                """
            )
            docs = cur.fetchall()
        # item 2 only has Expediente Técnico — no Bases Administrativas
        assert len(docs) == 1
        assert docs[0]["documento"] == "Expediente Técnico"


# ─── Selection query tests ────────────────────────────────────────────────────

class TestSelectBasesAdministrativas:
    def test_returns_only_bases_administrativas(self, db_conn, export_sample):
        ingest_payload(db_conn, export_sample, commit=False)

        results = select_bases_administrativas(db_conn)

        assert len(results) == 1
        row = results[0]
        assert row["documento"] == "Bases Administrativas"
        assert row["etapa"] == "Convocatoria"
        assert row["nomenclatura"] == "LPA-SM-TEST-001-2026-MDH/CS"
        assert row["uuid"] == "fixture-aaaa-bbbb-cccc-0001"

    def test_filter_by_licitacion_id(self, db_conn, export_sample):
        ingest_payload(db_conn, export_sample, commit=False)

        # Get the id for item 1
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM licitaciones WHERE nomenclatura = 'LPA-SM-TEST-001-2026-MDH/CS'"
            )
            lic_id = cur.fetchone()["id"]

        results = select_bases_administrativas(db_conn, licitacion_id=lic_id)
        assert len(results) == 1
        assert results[0]["licitacion_id"] == lic_id

    def test_no_results_when_none_match(self, db_conn, export_sample):
        ingest_payload(db_conn, export_sample, commit=False)

        # Get the id for item 2 (has no bases administrativas)
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM licitaciones WHERE nomenclatura = 'LPA-SM-TEST-002-2026-MPT/CS'"
            )
            lic_id = cur.fetchone()["id"]

        results = select_bases_administrativas(db_conn, licitacion_id=lic_id)
        assert results == []

    def test_case_insensitive_filter(self, db_conn, export_sample):
        """Fixture uses mixed case; select must tolerate any casing in DB."""
        ingest_payload(db_conn, export_sample, commit=False)

        # Manually insert a doc with uppercase etapa/documento
        with db_conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM licitaciones WHERE nomenclatura = 'LPA-SM-TEST-001-2026-MDH/CS'"
            )
            lic_id = cur.fetchone()["id"]
            cur.execute(
                """
                INSERT INTO documentos
                  (licitacion_id, nro, etapa, documento, uuid, filename)
                VALUES (%s, '99', 'CONVOCATORIA', 'BASES ADMINISTRATIVAS',
                        'fixture-case-test-uuid', 'case_test.pdf')
                """,
                (lic_id,),
            )

        results = select_bases_administrativas(db_conn)
        assert len(results) == 2  # original + uppercase one
