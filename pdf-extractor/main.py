"""
main.py — FastAPI: only coordinates, does not process.
POST /extract  → queues the job in Celery, returns jobId in <100ms
GET  /jobs/:id → reads the status from Redis (written by the Celery worker)
GET  /health   → health check
The extraction logic is in tasks.py (Celery worker).
The job status is stored in Redis with a 24-hour TTL.
"""

import uuid
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from worker import celery_app
from tasks import process_document, get_job_status

app = FastAPI(title="pdf-extractor", version="2.0.0")

class ExtractRequest(BaseModel):
    filePath: str # relative filePath: "downloads/uuid_filename.pdf"
    
    
@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}

@app.post("/extract")
def extract(body: ExtractRequest):
    """
    Pipe the extraction job into Celery and return the job ID immediately.
    n8n polls GET /jobs/{jobId} every 30 seconds.
    """
    job_id = str(uuid.uuid4())
    
    # Write the initial state to Redis before queuing
    # (so that n8n can find the job if it polls immediately)
    from tasks import update_job
    update_job(job_id, "queued", 0)
    
    # Queueing to the “extraction” queue — processed by celery-worker
    process_document.apply_async(
        args=[job_id, body.filePath],
        queue="extraction",
    )
    
    return {"jobId": job_id}

@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    """
    Returns the current status of the job.

    Possible statuses:
      queued    → in the queue, not yet started
      detecting_annex → searching for ANNEX No. 1
      building_subset → cropping sub-PDF
      ocr       → Mistral OCR in progress
      regex_extraction → extracting fields with regex
      semantic_extraction → Claude Haiku processing
      done      → completed, result available
      error     → failed, see “error” field
    """
    job = get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job