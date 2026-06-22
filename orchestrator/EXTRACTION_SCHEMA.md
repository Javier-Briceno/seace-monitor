# Extraction Result Schema

This document is the canonical reference for the JSON structure produced by
`pdf-extractor`'s Celery task and consumed by the orchestrator.

---

## 1. Job State (Redis hash `job:{job_id}`)

| Key        | Type   | Values |
|------------|--------|--------|
| `status`   | string | `queued` → `detecting_anexo` → `building_subset` → `ocr` → `regex_extraction` → `semantic_extraction` → `done` \| `error` |
| `progress` | int    | 0–100 |
| `result`   | JSON string | Present when `status=done`; parsed by `ExtractorClient` |
| `error`    | string | Present when `status=error` |

### Error prefixes on `error` field

| Prefix           | Meaning |
|------------------|---------|
| `[permanent]`    | Config / caller error — retrying won't help (bad API key, file not found, etc.) |
| `[max_retries]`  | Transient error that exhausted retry budget |
| *(no prefix)*    | Legacy format — treat as transient |

---

## 2. Extraction Result (parsed `result` field)

All fields are optional unless marked **guaranteed**.

### Stats — **guaranteed** when `status=done`

```jsonc
"stats": {
  "total_pages":       115,      // pages in the original PDF
  "subset_pages":       62,      // pages sent to Mistral OCR (after trimming)
  "anexo_page":         97,      // 1-based page number of ANEXO Nº 1; null if not found
  "markdown_chars":  42381,      // total chars returned by Mistral OCR
  "regex_fields_count": 8,       // fields extracted by regex (before Haiku)
  "file_size_mb":      1.47      // size of the original file
}
```

### Regex-extracted fields (present if found in document)

| Field | Type | Notes |
|-------|------|-------|
| `valor_referencial_monto` | float | e.g. `1250000.0` |
| `plazo_ejecucion_dias` | int | Calendar days |
| `plazo_ejecucion_tipo_dias` | str | Always `"calendarios"` when set |
| `plazo_inicio_computo` | str | Narrative start trigger |
| `modalidad_pago` | str | `"SUMA ALZADA"` \| `"PRECIOS UNITARIOS"` |
| `garantia_fiel_cumplimiento_pct` | float | **Always** `10.0` (Ley 32069) |
| `adelanto_directo_pct` | int | 0 = explicitly none |
| `adelanto_materiales_pct` | int | |
| `penalidad_mora_formula` | str | e.g. `"F = 0.10 / N * K"` |
| `fuente_financiamiento` | str | |
| `lugar_ejecucion` | str | |
| `tipo_evaluacion_economica` | str | `"EVALUACIÓN LIMITADA"` etc. |
| `forma_pago_detalle` | str | |
| `otras_penalidades` | object | See structure below |
| `equipamiento_estrategico` | object | See structure below |

#### `otras_penalidades` structure
```jsonc
{
  "valor": [
    { "numero": 1, "supuesto": "texto del supuesto", "calculo": "(0.10 UIT ...)" }
  ],
  "texto_original": "Tabla sección 3.3.19 — 4 penalidades"
}
```

#### `equipamiento_estrategico` structure
```jsonc
{
  "valor": [
    { "nombre": "RETROEXCAVADORA", "cantidad": 1 },
    { "nombre": "VOLQUETE",        "cantidad": 3 }
  ],
  "texto_original": "Tabla B.3 — 4 equipos requeridos"
}
```

### Semantic-extracted fields (Claude Haiku; null if not found in document)

| Field | Type | Notes |
|-------|------|-------|
| `factores_evaluacion` | object | See structure below |
| `personal_clave` | object \| null | |
| `requisitos_calificacion` | object \| null | |
| `resumen_ejecutivo` | object \| null | |
| `documentos_admision_oferta` | object \| null | |
| `perfeccionamiento_contrato` | object \| null | |
| `requisitos_perfeccionar_contrato` | object \| null | |
| `proforma_contrato` | object \| null | Only set when real contract clauses present |
| `anexos_tecnicos_clave` | object \| null | |

#### `factores_evaluacion` structure
```jsonc
{
  "valor": [
    { "factor": "Experiencia del Contratista", "puntaje_maximo": 40, "criterio": "..." },
    { "factor": "Personal Clave",              "puntaje_maximo": 35, "criterio": "..." }
  ],
  "puntaje_total": 100,
  "texto_original": "CUADRO RESUMEN FACTORES DE EVALUACIÓN ..."
}
```

### Internal / development fields (do not persist to DB)

All keys starting with `_` are internal. Strip them with `orchestrator.extract.strip_internal_fields(result)` before persisting.

| Field | Notes |
|-------|-------|
| `_markdown` | Full Mistral OCR output. Can be 40–100 KB. |
| `_haiku_general_parse_error` | Haiku returned invalid JSON; `_haiku_general_raw` has first 1000 chars |
| `_haiku_factores_parse_error` | Same for the dedicated factores call |
| `_haiku_general_error` | Unexpected exception in the general Haiku call |
| `_haiku_factores_error` | Unexpected exception in the factores Haiku call |

---

## 3. Orchestrator normalised result (`orchestrator.extract.run_extraction`)

```python
{
    "job_id":  str,           # UUID assigned by FastAPI
    "status":  "done"|"error",
    "result":  dict | None,   # parsed extraction dict; None when status=error
    "error":   str  | None,   # error string; None when status=done
}
```

---

## 4. Single code path — no size branching

All PDF sizes (small 1.5 MB ↔ large 45 MB) go through the identical extraction path:

```
PDF → find_anexo_page (Tesseract, headers only)
    → build_subset_pdf (pages 18 → ANEXO, or page 80 if no ANEXO found)
    → extract_with_mistral (Mistral OCR → Markdown)
    → extract_regex_fields (regex, ~0s)
    → extract_semantic_fields (Claude Haiku, ~8s)
    → Redis job:done
```

The n8n branches (small-PDF direct Claude, large-PDF special path, `licitacion_id == 14` gate)
have been removed from the migration path. The above is the only path.

---

## 5. Persistence contract (TASK-D)

When persisting to `extracciones.extraccion` (JSONB):
1. Call `strip_internal_fields(result)` to remove all `_`-prefixed keys (markdown, Haiku debug fields, etc.).
2. Map `status=done` → `estado='done'`, `status=error` → `estado='error'`.
3. Store `error` string in `validation_issues` as `{"extraction_error": "..."}` when applicable.
