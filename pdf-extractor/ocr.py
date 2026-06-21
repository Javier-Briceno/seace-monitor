"""
ocr.py — Detección de rango útil y extracción OCR con Mistral.

Etapa 1: find_anexo_page()
    Header-only OCR (top 18% de cada página) con Tesseract a 150 DPI.
    Busca "ANEXO Nº 1" desde la página 50 en adelante.
    Examina ~50-80 páginas en el peor caso, ~0.05s/página → máx 4s.

Etapa 2: extract_with_mistral()
    Recorta el sub-PDF (páginas 17 → ANEXO, omitiendo Sección General págs 1-18).
    Envía a Mistral OCR API. Retorna Markdown estructurado.
    Costo: ~$0.03 por documento (30 páginas × $0.001/pág).
"""

import os
import re
import base64
import pymupdf
import pytesseract
from PIL import Image
import httpx

MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
MISTRAL_OCR_URL = "https://api.mistral.ai/v1/ocr"

# Regex para detectar ANEXO Nº 1 con variaciones comunes de OCR
# Cubre: "ANEXO N° 1", "ANEXO Nº 1", "ANEXO No 1", "ANEXO N.1", "ANEXO N 1"
ANEXO_RE = re.compile(r"ANEXO\s*N[°ºoO\.]?\s*1(?!\d)", re.IGNORECASE)

# Páginas 1-18 son Sección General (texto legal idéntico en todos los docs).
# Siempre se omiten.
SECCION_GENERAL_PAGES = 18


def find_anexo_page(doc: pymupdf.Document) -> int | None:
    """
    Busca la primera página que contiene 'ANEXO Nº 1' usando header-only OCR.

    Estrategia: escaneo lineal desde página 50 (o mitad del doc si es corto).
    Solo renderiza el 18% superior de cada página a 150 DPI en escala de grises.
    Esto es ~1240×260 píxeles por página — muy rápido para Tesseract.

    Retorna el índice 0-based de la página de ANEXO, o None si no se encuentra.
    """
    n = len(doc)
    start = min(50, n // 2)

    for page_num in range(start, n):
        page = doc[page_num]
        rect = page.rect

        # Clip: solo el 18% superior de la página
        clip = pymupdf.Rect(
            rect.x0,
            rect.y0,
            rect.x1,
            rect.y0 + rect.height * 0.18,
        )

        # Renderizar solo el clip a 150 DPI en escala de grises
        pix = page.get_pixmap(dpi=150, clip=clip, colorspace=pymupdf.csGRAY)
        img = Image.frombytes("L", [pix.width, pix.height], pix.samples)

        # OCR con Tesseract — modo 6 (bloque uniforme), oem 3 (LSTM)
        text = pytesseract.image_to_string(
            img, config="--psm 6 --oem 3 -l spa", timeout=10
        )

        if ANEXO_RE.search(text):
            print(f"[ocr] ANEXO Nº 1 encontrado en página {page_num + 1} (0-idx: {page_num})")
            return page_num

    print("[ocr] ANEXO Nº 1 no encontrado — se procesará hasta la página 80 o fin del doc")
    return None


def build_subset_pdf(doc: pymupdf.Document, anexo_page: int | None) -> bytes:
    """
    Recorta el PDF al rango útil: páginas 18 → ANEXO (0-indexed: 17 → anexo_page).
    Omite la Sección General (págs 1-18) y los anexos (formularios vacíos).

    Si anexo_page es None, procesa hasta página 80 o el fin del documento.
    """
    n = len(doc)
    start_idx = SECCION_GENERAL_PAGES  # pág 19 en términos humanos (0-indexed: 18)

    if start_idx >= n:
        # Documento muy corto — procesar todo
        start_idx = 0

    end_idx = anexo_page if anexo_page is not None else min(80, n)

    # Asegurar que el rango tenga al menos 1 página
    if end_idx <= start_idx:
        end_idx = min(start_idx + 40, n)

    useful_pages = list(range(start_idx, end_idx))
    print(f"[ocr] Rango útil: páginas {start_idx + 1}–{end_idx} ({len(useful_pages)} páginas)")

    # Crear sub-PDF con solo las páginas útiles
    sub_doc = pymupdf.open()
    sub_doc.insert_pdf(doc, from_page=start_idx, to_page=end_idx - 1)

    pdf_bytes = sub_doc.tobytes(garbage=4, deflate=True)
    sub_doc.close()

    size_mb = len(pdf_bytes) / (1024 * 1024)
    print(f"[ocr] Sub-PDF generado: {len(useful_pages)} págs, {size_mb:.1f} MB")
    return pdf_bytes


async def extract_with_mistral(pdf_bytes: bytes) -> str:
    """
    Envía el sub-PDF a Mistral OCR y retorna el Markdown estructurado.

    Mistral OCR preserva tablas, encabezados y estructura de columnas.
    Accuracy en español: 99.54%. Costo: $0.001 por página.
    """
    if not MISTRAL_API_KEY:
        raise ValueError("MISTRAL_API_KEY no configurada")

    b64 = base64.b64encode(pdf_bytes).decode()
    payload = {
        "model": "mistral-ocr-latest",
        "document": {
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{b64}",
        },
        "include_image_base64": False,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            MISTRAL_OCR_URL,
            headers={
                "Authorization": f"Bearer {MISTRAL_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    pages = data.get("pages", [])
    markdown = "\n\n".join(p.get("markdown", "") for p in pages)
    print(f"[ocr] Mistral OCR completado: {len(pages)} páginas, {len(markdown)} chars")
    return markdown
