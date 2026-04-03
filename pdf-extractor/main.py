import os, base64, uuid, threading, sys
import fitz, pymupdf4llm, anthropic
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import time

app = FastAPI()

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

DOWNLOADS_BASE = "/app/downloads"

jobs: dict = {} # jobId -> {status, result, error}

class ExtractRequest(BaseModel):
    filePath: str # relative filePath: "downloads/uuid_filename.pdf"
    
# CLASSIFY
def classify_page(page: fitz.Page) -> str:
    blocks = page.get_text("blocks")
    total_chars = sum(len(b[4]) for b in blocks if b[6] == 0)
    if total_chars >= 80:
        return "text"
    images = page.get_images(full=True)
    if not images:
        return "text" # empty page without image -> treat as text
    page_area = page.rect.width * page.rect.height
    for img in images:
        try:
            bbox = page.get_image_bbox(img)
            if bbox.get_area() / page_area > 0.80:
                return "scanned"
        except Exception:
            pass
    return "text" if total_chars > 0 else "scanned"

# TEXT EXTRACTION
def extract_text_pages(abs_path: str, page_numbers: list[int]) -> str:
    if not page_numbers:
        return ""
    return pymupdf4llm.to_markdown(
        abs_path,
        pages=page_numbers,
        page_chunks=False,
        show_progress=False,
    )

# SCANNED EXTRACTION
def extract_scanned_page(page: fitz.Page, retries=3) -> str:
    mat = fitz.Matrix(150 / 72, 150 / 72) # # 150 DPI — enough for printed text
    pix = page.get_pixmap(matrix=mat)
    img_base64 = base64.standard_b64encode(pix.tobytes("jpeg", jpg_quality=85)).decode()
    
    for attempt in range(retries):
        try:
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=2000,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/jpeg", "data": img_base64},
                        },
                        {
                            "type": "text",
                            "text": (
                                "Transcribe el texto de esta página exactamente como aparece. "
                                "Preserva estructura, tablas y formato. "
                                "Solo el texto, sin comentarios ni explicaciones."   
                            ),
                        },
                    ],    
                }],
            )
            return resp.content[0].text
        except Exception as e:
            if attempt < retries -1:
                time.sleep(10 * (attempt + 1)) # backoff: 10s, 20s
                continue
            return f"[Error on page: {str(e)}]"

# WORKER
def run_extraction(job_id: str, file_path: str):
    try:
        # Validate path transversal
        abs_path = os.path.realpath(f"/app/{file_path}")
        if not abs_path.startswith(os.path.realpath(DOWNLOADS_BASE)):
            jobs[job_id] = {"status": "error", "error": "Access denied"}
            return
        if not os.path.exists(abs_path):
            jobs[job_id] = {"status": "error", "error": f"File not found: {file_path}"}
            return
        
        doc = fitz.open(abs_path)
        text_pages, scanned_pages = [], []
        
        for i in range(len(doc)):
            # temp log to check classify_page accuracy
            page_type = classify_page(doc[i])
            print(f"[{job_id[:8]}] Pagina {i+1}/{len(doc)}: {page_type}", flush=True)
            if page_type == "text":
                text_pages.append(i)
            else:
                scanned_pages.append(i)
        
        # Text pages - bulk with PyMuPDF4LLM
        print(f"[{job_id[:8]}] Extracting {len(text_pages)} text pages...", flush=True)
        text_content = extract_text_pages(abs_path, text_pages)
        
        # Scanned pages - 1 Claude call per page
        scanned_parts = []
        for idx, page_num in enumerate(scanned_pages):
            print(f"[{job_id[:8]}] Scan {idx + 1} / {len(scanned_pages)} (page {page_num + 1})...", flush=True)
            page_text = extract_scanned_page(doc[page_num])
            scanned_parts.append(f"\n\n--- Page {page_num + 1} (scanned) ---\n{page_text}")
        scanned_content = "".join(scanned_parts)
        
        combined = text_content + scanned_content
        total_pages = len(doc)
        doc.close()
        
        jobs[job_id] = {
            "status": "done",
            "result": {
                "text": combined,
                "filePath": file_path,
                "stats": {
                    "total_pages": total_pages,
                    "text_pages": len(text_pages),
                    "scanned_pages": len(scanned_pages),
                    "char_count": len(combined)  
                },
            },
        }
        print(f"[{job_id[:8]}] Completed. {total_pages} pages, {len(combined)} chars.", flush=True)
    except Exception as e:
        print(f"[{job_id[:8]}] ERROR: {e}", flush=True)
        jobs[job_id] = {"status": "error", "error": str(e)}
        
# ENDPOINTS
@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/extract")
def extract(body: ExtractRequest):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "running"}
    thread = threading.Thread(target=run_extraction, args=(job_id, body.filePath), daemon=True)
    thread.start()
    return {"jobId": job_id}

@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job