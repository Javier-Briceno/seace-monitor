# SEACE Monitor — Database Target & Network Topology

## Database Target

| Property | Value |
|---|---|
| Container name | `postgres` |
| Network | `server_network` (`172.19.0.0/16`) |
| Container IP | `172.19.0.3` |
| Database | `seace` |
| User | `javier` |
| Port | `5432` |

The shared `postgres:16` container lives **outside** the seace-monitor `docker-compose.yml`.
It is managed independently and attached to `server_network`.

n8n (at `172.19.0.4`) is on the same `server_network` and reaches Postgres via hostname
`postgres` (container name DNS resolution within the network).

## Schema

The schema lives in [`schema.sql`](schema.sql) (extracted verbatim from the
`CREATE TABLES` node in `n8n-workflow/seace-workflow.json`).

All tables are in the `public` schema of the `seace` database.

### Tables

| Table | Purpose |
|---|---|
| `licitaciones` | One row per procurement listing scraped from SEACE |
| `cronograma` | Schedule stages for a licitacion |
| `documentos` | Attached document files |
| `convocatoria` | Call/announcement detail |
| `entidad_contratante` | Contracting entity detail |
| `extracciones` | AI extraction results for documents |

### Key constraints

- `licitaciones`: `UNIQUE (nomenclatura, entidad, fecha_publicacion)`
- `extracciones`: `UNIQUE (licitacion_id)` named `uq_extracciones_licitacion`
- `extracciones` columns: `estado` (VARCHAR 30), `validation_issues` (JSONB)

## n8n Credential (action required)

The workflow uses a credential named **"Postgres account"** (id `FXEG0dQzOuAcjlhc`).

**You must verify/update it in the n8n UI** at `https://n8n.javierbriceno.com`:

1. Go to **Credentials → Postgres account**.
2. Confirm (or set) these values:
   - **Host**: `postgres`
   - **Database**: `seace`
   - **User**: `javier`
   - **Port**: `5432`
3. Test the connection and save.

## Docker Network Topology

```
server_network (172.19.0.0/16) — external, pre-existing
  ├── postgres          172.19.0.3   ← shared DB
  ├── n8n               172.19.0.4   ← workflow engine
  ├── bearing_app_1     172.19.0.2
  └── f5bot_pipeline    172.19.0.5

seace-monitor internal (bridge, defined in docker-compose.yml)
  ├── vpn (nordvpn)                  ← routes seace-runner traffic
  ├── redis                          ← Celery broker
  ├── pdf-extractor     :8000        ← FastAPI (host-exposed)
  └── celery-worker                  ← Celery worker
  (seace-runner uses network_mode: service:vpn)
```

### Implication for n8n → pdf-extractor calls

n8n is on `server_network`; `pdf-extractor` is on the `internal` bridge.
They **cannot reach each other by container name** today.

Two options (decision deferred to TASK-2):
- **Option A (recommended)**: Declare `server_network` as an external network in
  `docker-compose.yml` and add `pdf-extractor` (and optionally `seace-runner`) to it.
  n8n would then call `http://pdf-extractor:8000`.
- **Option B**: n8n calls `pdf-extractor` via the Docker host gateway IP
  (`172.19.0.1:8000`). Works today since port 8000 is host-bound, but fragile.

No networking changes are made in TASK-1.
