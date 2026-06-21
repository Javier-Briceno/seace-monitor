import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "pdf_extractor",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks"],
)

celery_app.conf.update(
    # No confirmar la tarea hasta que termine — evita pérdidas si el worker muere
    task_acks_late=True,
    # Un task a la vez por worker — distribución justa
    worker_prefetch_multiplier=1,
    # El timeout de visibilidad debe ser mayor que el tiempo máximo de una tarea
    # Un PDF grande puede tardar ~90s, ponemos 1h de margen
    broker_transport_options={"visibility_timeout": 3600},
    # Resultados persisten 24h en Redis
    result_expires=86400,
    # Serialización
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
)
