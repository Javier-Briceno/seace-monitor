"""
Ingestion layer: takes a /seace/export payload and persists it to the seace DB.

Field mappings mirror the n8n workflow nodes:
  Licitaciones, Cronogramas, Documentos, Convocatoria, Entidad Contratante.

The n8n `Filter` node logic is exposed as `select_bases_administrativas()`.
"""
from __future__ import annotations

from typing import Any


# ─── Date parsing ─────────────────────────────────────────────────────────────

def parse_fecha(raw: str | None) -> str | None:
    """
    Convert SEACE date string 'DD/MM/YYYY HH:MM' → 'YYYY-MM-DDTHH:MM:00',
    which Postgres accepts as a TIMESTAMP literal.

    Returns None for empty / None / malformed input.
    """
    if not raw:
        return None
    raw = raw.strip()
    date_part, _, time_part = raw.partition(" ")
    time_part = time_part.strip() or "00:00"
    parts = date_part.split("/")
    if len(parts) != 3:
        return None
    d, m, y = parts
    return f"{y}-{m}-{d}T{time_part}:00"


# ─── Per-table insert helpers ──────────────────────────────────────────────────

def _upsert_licitacion(cur, item: dict, meta: dict) -> int | None:
    """
    INSERT one licitacion row.
    Returns the new serial id, or None when ON CONFLICT DO NOTHING fires
    (i.e. the row already existed — no children should be inserted).
    """
    cur.execute(
        """
        INSERT INTO licitaciones
          (numero, nomenclatura, entidad, fecha_publicacion,
           reiniciado_desde, objeto_de_contratacion, descripcion,
           codigo_snip, codigo_cui, monto, moneda, version_seace,
           departamento, scraped_at)
        VALUES
          (%(numero)s, %(nomenclatura)s, %(entidad)s, %(fecha_publicacion)s,
           %(reiniciado_desde)s, %(objeto_de_contratacion)s, %(descripcion)s,
           %(codigo_snip)s, %(codigo_cui)s, %(monto)s, %(moneda)s, %(version_seace)s,
           %(departamento)s, %(scraped_at)s)
        ON CONFLICT (nomenclatura, entidad, fecha_publicacion) DO NOTHING
        RETURNING id
        """,
        {
            "numero":                 item.get("numero") or None,
            "nomenclatura":           item.get("nomenclatura"),
            "entidad":                item.get("entidad"),
            "fecha_publicacion":      parse_fecha(item.get("fecha_publicacion")),
            "reiniciado_desde":       item.get("reiniciado_desde") or None,
            "objeto_de_contratacion": item.get("objeto_de_contratacion"),
            "descripcion":            item.get("descripcion"),
            "codigo_snip":            item.get("codigo_snip") or None,
            "codigo_cui":             item.get("codigo_cui") or None,
            "monto":                  item.get("monto"),
            "moneda":                 item.get("moneda"),
            "version_seace":          item.get("version_seace"),
            "departamento":           (meta.get("filtros_aplicados") or {}).get("departamento"),
            "scraped_at":             meta.get("scraped_at"),
        },
    )
    row = cur.fetchone()
    return row["id"] if row else None


def _insert_cronograma(cur, licitacion_id: int, entries: list[dict]) -> int:
    count = 0
    for entry in entries:
        cur.execute(
            """
            INSERT INTO cronograma (licitacion_id, etapa, lugar, fecha_inicio, fecha_fin)
            VALUES (%(licitacion_id)s, %(etapa)s, %(lugar)s, %(fecha_inicio)s, %(fecha_fin)s)
            """,
            {
                "licitacion_id": licitacion_id,
                "etapa":         entry.get("Etapa"),
                "lugar":         entry.get("Lugar"),
                "fecha_inicio":  entry.get("Fecha Inicio"),
                "fecha_fin":     entry.get("Fecha Fin"),
            },
        )
        count += 1
    return count


def _insert_documentos(cur, licitacion_id: int, docs: list[dict]) -> int:
    count = 0
    for doc in docs:
        archivo = doc.get("Archivo") or {}
        cur.execute(
            """
            INSERT INTO documentos
              (licitacion_id, nro, etapa, documento, uuid, filename,
               tamanio, local_path, fecha_publicacion,
               page_count, file_size_mb, exceeds_claude_limit)
            VALUES
              (%(licitacion_id)s, %(nro)s, %(etapa)s, %(documento)s, %(uuid)s, %(filename)s,
               %(tamanio)s, %(local_path)s, %(fecha_publicacion)s,
               %(page_count)s, %(file_size_mb)s, %(exceeds_claude_limit)s)
            ON CONFLICT (uuid) DO NOTHING
            """,
            {
                "licitacion_id":        licitacion_id,
                "nro":                  doc.get("Nro"),
                "etapa":                doc.get("Etapa"),
                "documento":            doc.get("Documento"),
                "uuid":                 archivo.get("uuid"),
                "filename":             archivo.get("filename"),
                "tamanio":              archivo.get("tamanio"),
                "local_path":           archivo.get("local_path"),
                "fecha_publicacion":    doc.get("Fecha de publicación"),
                "page_count":           archivo.get("pageCount"),
                "file_size_mb":         archivo.get("fileSizeMB"),
                "exceeds_claude_limit": archivo.get("exceedsClaudeLimit"),
            },
        )
        count += 1
    return count


def _insert_convocatoria(cur, licitacion_id: int, conv: dict) -> None:
    cur.execute(
        """
        INSERT INTO convocatoria
          (licitacion_id, nomenclatura, n_convocatoria, tipo_compra, normativa,
           version_seace, entidad_convocante, direccion_legal, pagina_web,
           telefono, objeto_contratacion, descripcion_objeto, monto, fecha_publicacion)
        VALUES
          (%(licitacion_id)s, %(nomenclatura)s, %(n_convocatoria)s, %(tipo_compra)s, %(normativa)s,
           %(version_seace)s, %(entidad_convocante)s, %(direccion_legal)s, %(pagina_web)s,
           %(telefono)s, %(objeto_contratacion)s, %(descripcion_objeto)s, %(monto)s, %(fecha_publicacion)s)
        """,
        {
            "licitacion_id":      licitacion_id,
            "nomenclatura":       conv.get("Nomenclatura"),
            "n_convocatoria":     conv.get("N° Convocatoria"),
            "tipo_compra":        conv.get("Tipo Compra o Selección"),
            "normativa":          conv.get("Normativa Aplicable"),
            "version_seace":      conv.get("Versión SEACE"),
            "entidad_convocante": conv.get("Entidad Convocante"),
            "direccion_legal":    conv.get("Direccion Legal"),
            "pagina_web":         conv.get("Pagina Web"),
            "telefono":           conv.get("Télefono de la Entidad"),
            "objeto_contratacion":  conv.get("Objeto de Contratación"),
            "descripcion_objeto": conv.get("Descripción del Objeto"),
            "monto":              conv.get("VR / VE / Cuantía de la contratación"),
            "fecha_publicacion":  conv.get("Fecha y Hora Publicación"),
        },
    )


def _insert_entidad_contratante(cur, licitacion_id: int, entidades: list[dict]) -> None:
    for e in entidades:
        cur.execute(
            """
            INSERT INTO entidad_contratante (licitacion_id, ruc, entidad)
            VALUES (%(licitacion_id)s, %(ruc)s, %(entidad)s)
            """,
            {
                "licitacion_id": licitacion_id,
                "ruc":           e.get("N° Ruc"),
                "entidad":       e.get("Entidad Contratante"),
            },
        )


# ─── Public API ────────────────────────────────────────────────────────────────

def ingest_payload(conn, payload: dict, *, commit: bool = True) -> dict[str, Any]:
    """
    Process a full /seace/export payload into the seace database.

    - New licitaciones are inserted; duplicates (same nomenclatura+entidad+fecha)
      are silently skipped via ON CONFLICT DO NOTHING.
    - Child rows (cronograma, documentos, convocatoria, entidad_contratante) are
      only inserted when the parent licitacion was just created, matching n8n
      behavior.
    - documentos uses its own ON CONFLICT (uuid) guard so partial re-scrapes
      don't produce duplicates.

    commit=False is used in tests so callers control the transaction boundary.

    Returns stats: {inserted, skipped, cronograma, documentos}
    """
    meta = payload.get("meta") or {}
    items = payload.get("items") or []
    stats: dict[str, Any] = {
        "inserted": 0,
        "skipped": 0,
        "cronograma": 0,
        "documentos": 0,
    }

    with conn.cursor() as cur:
        for item in items:
            lic_id = _upsert_licitacion(cur, item, meta)

            if lic_id is None:
                # Already in DB — skip all children (idempotency)
                stats["skipped"] += 1
                continue

            stats["inserted"] += 1
            ficha = item.get("ficha") or {}

            cronograma = ficha.get("cronograma") or []
            stats["cronograma"] += _insert_cronograma(cur, lic_id, cronograma)

            documentos = ficha.get("documentos") or []
            stats["documentos"] += _insert_documentos(cur, lic_id, documentos)

            conv = ficha.get("convocatoria")
            if isinstance(conv, dict):
                _insert_convocatoria(cur, lic_id, conv)

            entidades = ficha.get("entidad_contratante") or []
            _insert_entidad_contratante(cur, lic_id, entidades)

    if commit:
        conn.commit()

    return stats


def select_bases_administrativas(conn, licitacion_id: int | None = None) -> list[dict]:
    """
    Return documentos rows where etapa='convocatoria' AND documento='bases administrativas'.
    Optionally filtered to a single licitacion_id.

    Mirrors the n8n Filter node conditions (case-insensitive).
    These are the documents queued for AI extraction in the next pipeline stage.
    """
    sql = """
        SELECT
            d.id, d.licitacion_id, d.nro, d.etapa, d.documento,
            d.uuid, d.filename, d.local_path,
            d.page_count, d.file_size_mb, d.exceeds_claude_limit,
            l.nomenclatura
        FROM documentos d
        JOIN licitaciones l ON l.id = d.licitacion_id
        WHERE LOWER(d.etapa)     = 'convocatoria'
          AND LOWER(d.documento) = 'bases administrativas'
    """
    params: list[Any] = []
    if licitacion_id is not None:
        sql += " AND d.licitacion_id = %s"
        params.append(licitacion_id)
    sql += " ORDER BY d.licitacion_id, d.nro"

    with conn.cursor() as cur:
        cur.execute(sql, params or None)
        return cur.fetchall()
