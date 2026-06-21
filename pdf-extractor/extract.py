"""
Hybrid extraction of OCR text.

Step 3a: extract_regex_fields()
    Extracts ~60% of fields using Mistral's Markdown regex patterns.
    Cost: $0. Speed: <1s.

Step 3b: extract_semantic_fields()
    Claude Haiku extracts the remaining 40% (evaluation factors, personnel, equipment).
    Input: plain text (no images). Cost: ~$0.01/call.
"""

import re
import json
import os
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# Fields that Claude Haiku must extract (require semantic understanding)
SEMANTIC_FIELDS = [
    "factores_evaluacion",
    "personal_clave",
    "equipamiento_estrategico",
    "otras_penalidades",
    "requisitos_calificacion",
    "resumen_ejecutivo",
    "documentos_admision_oferta",
    "perfeccionamiento_contrato",
    "requisitos_perfeccionar_contrato",
    "proforma_contrato",
    "anexos_tecnicos_clave",
]

def extract_regex_fields(text: str) -> dict:
    """
    Extracts structured fields using regular expressions from Mistral OCR Markdown.
    The patterns are tolerant of minor OCR variations.

    Returns a dictionary containing the fields found. Fields not found are not included
    (the merge in n8n will treat them as null during the scraper's pre-fill).
    """
    fields = {}
    
    # --- Reference value ---
    # Pattern: "asciende a la suma de S/ 1'250,000.00" o "S/. 602,864.60"
    m = re.search(
        r"asciende\s+a\s+la\s+suma\s+de\s+S/\.?\s*([\d,\'\.]+)",
        text, re.IGNORECASE
    )
    if m:
        raw = m.group(1).replace("'", "").replace(",", "")
        try:
            fields["valor_referencial_monto"] = float(raw)
        except ValueError:
            pass
    
    # --- Completion deadline ---
    m = re.search(r"(\d+)\s+D[IÍ]AS?\s+CALENDARIOS?", text, re.IGNORECASE)
    if m:
        fields["plazo_ejecucion_dias"] = int(m.group(1))
        fields["plazo_ejecucion_tipo_dias"] = "calendarios"
        
    # --- When does the period begin? ---
    m = re.search(
        r"plazo\s+se\s+computa\s+(?:a\s+partir\s+de[l]?\s+)?([^\.\n]{10,80})",
        text, re.IGNORECASE
    )
    if m:
        fields["plazo_inicio_computo"] = m.group(1).strip()

    # --- Modalidad de pago / sistema de contratación ---
    # Busca en la sección 3.3.13 primero (más específico)
    m = re.search(r"3\.3\.13[^\n]*\n.*?(SUMA\s+ALZADA|PRECIOS\s+UNITARIOS)", text, re.I | re.DOTALL)
    if not m:
        # Fallback: cerca del encabezado de modalidad de pago
        m = re.search(r"(?:MODALIDAD\s+DE\s+PAGO)[^\n]*\n.*?(SUMA\s+ALZADA|PRECIOS\s+UNITARIOS)", text, re.I | re.DOTALL)
    if m:
        fields["modalidad_pago"] = m.group(1).upper().replace("  ", " ")


    # --- Performance bond: always 10% under Law 32069 ---
    fields["garantia_fiel_cumplimiento_pct"] = 10.0

    # --- Direct advance payment ---
    m = re.search(
        r"adelanto\s+directo[^\d]*(\d+)\s*%",
        text, re.IGNORECASE
    )
    if m:
        fields["adelanto_directo_pct"] = int(m.group(1))
    else:
        # Check for explicit absence
        if re.search(r"no\s+se\s+otorgar[aá]\s+adelanto", text, re.IGNORECASE):
            fields["adelanto_directo_pct"] = 0

    # --- Advance payment for materials/supplies ---
    m = re.search(
        r"adelanto\s+(?:para\s+)?(?:materiales|insumos)[^\d]*(\d+)\s*%",
        text, re.IGNORECASE
    )
    if m:
        fields["adelanto_materiales_pct"] = int(m.group(1))

    # --- Late payment penalty: standard formula ---
    # F = 0.10 / F = (0.10 / N) * K → The coefficients vary depending on the law
    m = re.search(r"F\s*=\s*0[,\.](10|40|25|15)", text)
    if m:
        fields["penalidad_mora_formula"] = f"F = 0.{m.group(1)} / N * K"

    # --- Source of funding ---
    # Appears after the header "1.6" or "FINANCIAMIENTO"
    m = re.search(
        r"(?:1\.6|FINANCIAMIENTO)[^\n]*\n([^\n]{5,120})",
        text, re.IGNORECASE
    )
    if m:
        fuente = m.group(1).strip()
        if len(fuente) > 5:
            fields["fuente_financiamiento"] = fuente

    # --- Place of performance ---
    m = re.search(
        r"(?:lugar\s+de\s+ejecuci[oó]n|lugar\s+de\s+entrega)[^\n]*\n([^\n]{5,200})",
        text, re.IGNORECASE
    )
    if m:
        fields["lugar_ejecucion"] = m.group(1).strip()

    # --- Type of economic assessment (only in some documents) ---
    m = re.search(r"\b(EVALUACI[OÓ]N\s+LIMITADA|EVALUACI[OÓ]N\s+FIJA)\b", text, re.IGNORECASE)
    if m:
        fields["tipo_evaluacion_economica"] = m.group(1).upper()

    # --- Payment method / Acceptance ---
    m = re.search(
        r"(?:plazo\s+de\s+pago|pago\s+se\s+efectuar[aá])[^\n]*\n?([^\n]{10,200})",
        text, re.IGNORECASE
    )
    if m:
        fields["forma_pago_detalle"] = m.group(1).strip()
    
    # --- Otras penalidades (tabla 3.3.19) ---
    pen_matches = re.findall(
        r'\|\s*(\d{2})\s*\|([^|]+)\|\s*(\([^)]+UIT[^)]*\)[^|]*)\|',
        text, re.IGNORECASE
    )
    if pen_matches:
        fields["otras_penalidades"] = {
            "valor": [
                {"numero": int(n), "supuesto": s.strip()[:120], "calculo": c.strip()}
                for n, s, c in pen_matches[:6]
            ],
            "texto_original": f"Tabla sección 3.3.19 — {len(pen_matches)} penalidades"
        }
        
    # --- Equipamiento estratégico (tabla sección 3.4.2 B.3) ---
    equip_matches = re.findall(
        r'\|\s*([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ\s\d,./°]+?)\s*\|\s*(\d+)\s*\|',
        text
    )
    # Filtrar solo filas que sean equipos (excluir encabezados de tabla)
    EQUIPMENT_KEYWORDS = ['ESTACION', 'COMPACTADORA', 'RETROEXCAVADORA', 'MOTONIVELADORA',
                        'CAMION', 'VOLQUETE', 'MEZCLADORA', 'TRACTOR', 'EXCAVADORA',
                        'VIBRADOR', 'NIVEL', 'GPS', 'BOMBA']
    equip_filtrado = [
        {"nombre": nombre.strip(), "cantidad": int(cant)}
        for nombre, cant in equip_matches
        if any(kw in nombre.upper() for kw in EQUIPMENT_KEYWORDS)
    ]
    if equip_filtrado:
        fields["equipamiento_estrategico"] = {
            "valor": equip_filtrado,
            "texto_original": f"Tabla B.3 — {len(equip_filtrado)} equipos requeridos"
        }

    print(f"[extract] Regex extrajo {len(fields)} campos: {list(fields.keys())}")
    return fields
    
def extract_semantic_fields(markdown_text: str, already_extracted: dict) -> dict:
    """
    Claude Haiku extrae campos semánticos que regex no puede recuperar.

    Mantiene compatibilidad con tasks.py:
    - recibe `already_extracted`
    - calcula internamente los campos faltantes usando SEMANTIC_FIELDS

    Además:
    - hace una llamada general para todos los campos excepto factores_evaluacion
    - hace una llamada dedicada para factores_evaluacion
    """
    client = anthropic.Anthropic()

    missing_fields = [f for f in SEMANTIC_FIELDS if f not in already_extracted]
    if not missing_fields:
        print("[extract] All semantic fields already extracted by regex")
        return {}

    print(f"[extract] Haiku extracting {len(missing_fields)} fields: {missing_fields}")

    # --- Extraer sección de factores por separado ---
    # Buscar el CUADRO RESUMEN primero
    factores_match = re.search(
        r'(CUADRO\s+RESUMEN\s+FACTORES.*?PUNTAJE\s+TOTAL[^\n]*\n[^\n]*100)',
        markdown_text, re.DOTALL | re.I
    )

    # Fallback: encabezado real del Capítulo IV (con # de markdown)
    if not factores_match:
        factores_match = re.search(
            r'(#{1,2}\s*CAP[IÍ]TULO\s+IV\b.*)',
            markdown_text, re.DOTALL | re.I
        )

    factores_section = factores_match.group(0)[:12000] if factores_match else ""
    print(f"[extract] factores_section: {len(factores_section)} chars, preview: {factores_section[:200]!r}")

    text_truncated = markdown_text[:25000]
    if factores_section:
        text_truncated += "\n\n--- SECCIÓN FACTORES ---\n" + factores_section

    print(
        f"[extract] Contexto Haiku: {len(text_truncated)} chars "
        f"({'con' if factores_match else 'sin'} sección de factores)"
    )

    general_fields = [f for f in missing_fields if f != "factores_evaluacion"]
    results = {}

    def _clean_json_response(text: str) -> str:
        text = text.strip()
        if text.startswith("```json"):
            text = text[len("```json"):].strip()
        elif text.startswith("```"):
            text = text[len("```"):].strip()

        if text.endswith("```"):
            text = text[:-3].strip()

        return text

    # --- Llamada general ---
    if general_fields:
        prompt_general = f"""Eres un analista experto en contrataciones del Estado peruano (Ley N° 32069).
Analiza el siguiente documento de Bases Administrativas y extrae los campos indicados.

REGLAS:
- Devuelve SOLO JSON válido. Sin markdown, sin explicaciones.
- Para cada campo: incluye "valor" con el dato extraído y "texto_original" con la cita exacta (máximo 150 caracteres).
- Si no encuentras un campo → null.
- Montos: S/ 1'250,000.00 → 1250000.00 (número sin formato).
- proforma_contrato: extraer SOLO si hay cláusulas completas con texto real (no placeholders tipo [CONSIGNAR...]). Si solo hay plantilla vacía → null.

NOTA: El campo "otras_penalidades" es una tabla en la sección 3.3.19 con columnas: N°, Supuesto, Forma de cálculo, Procedimiento. Extrae los primeros 5 supuestos como array de objetos con campos: numero, supuesto, calculo.

CAMPOS A EXTRAER:
{json.dumps(general_fields, ensure_ascii=False, indent=2)}

DOCUMENTO:
{text_truncated}"""

        try:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt_general}]
            )
            raw = _clean_json_response(resp.content[0].text)
            parsed = json.loads(raw)
            results.update(parsed)
            print(f"[extract] Haiku extrajo {len(parsed)} campos generales")
        except json.JSONDecodeError as e:
            print(f"[extract] ERROR parseando JSON general de Haiku: {e}")
            print(f"[extract] Raw response: {raw[:500]}")
            return {
                "_haiku_general_parse_error": str(e),
                "_haiku_general_raw": raw[:1000],
                **results
            }
        except Exception as e:
            print(f"[extract] ERROR en extracción general: {e}")
            return {
                "_haiku_general_error": str(e),
                **results
            }

    # --- Llamada dedicada para factores_evaluacion ---
    if "factores_evaluacion" in missing_fields:
        if factores_section:
            prompt_factores = f"""Extrae los factores de evaluación técnica del siguiente texto de bases de licitación peruana.

Devuelve SOLO este JSON exacto, sin markdown ni explicaciones:
{{
  "factores_evaluacion": {{
    "valor": [
      {{"factor": "nombre del factor", "puntaje_maximo": 40, "criterio": "descripción breve"}}
    ],
    "puntaje_total": 100,
    "texto_original": "cita del cuadro resumen"
  }}
}}

Si hay un "CUADRO RESUMEN FACTORES DE EVALUACIÓN", úsalo como fuente principal.

TEXTO:
{factores_section}"""

            try:
                resp2 = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=2048,
                    messages=[{"role": "user", "content": prompt_factores}]
                )
                raw2 = _clean_json_response(resp2.content[0].text)
                parsed2 = json.loads(raw2)
                results.update(parsed2)
                print("[extract] Haiku extrajo factores_evaluacion")
            except json.JSONDecodeError as e:
                print(f"[extract] ERROR parseando JSON de factores_evaluacion: {e}")
                print(f"[extract] Raw response: {raw2[:500]}")
                results["_haiku_factores_parse_error"] = str(e)
                results["_haiku_factores_raw"] = raw2[:1000]
            except Exception as e:
                print(f"[extract] ERROR en extracción de factores_evaluacion: {e}")
                results["_haiku_factores_error"] = str(e)
        else:
            print("[extract] No se encontró sección de factores; devolviendo factores_evaluacion=None")
            results["factores_evaluacion"] = None

    return results
    