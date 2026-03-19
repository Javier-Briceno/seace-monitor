# SEACE Monitor

*English version below / Deutsche Version zuerst*

---

## 🇩🇪 Deutsche Version

> ⚠️ **Status: Work in Progress** – Kern-Scraping-Pipeline vollständig implementiert.
> Aktuell: n8n-Workflow-Integration und PDF-Analyse in Entwicklung.

### Über das Projekt

Automatisiertes System zur täglichen Überwachung und Extraktion von Ausschreibungsdaten
aus dem peruanischen Beschaffungsportal SEACE (Sistema Electrónico de Contrataciones del Estado).
Bestehend aus einem REST-Microservice (`seace-runner`) und einem n8n-Orchestrierungs-Workflow.

**Hintergrund:** Das SEACE-Portal musste täglich manuell auf neue Ausschreibungen
überprüft werden — ein repetitiver, zeitaufwändiger Prozess. Dieses Projekt automatisiert
die vollständige Pipeline: von der Extraktion bis zur Benachrichtigung.

**Projektziel:** Entwicklung eines **täglichen Monitoring-Systems**, das:
1. Neue Ausschreibungen automatisch täglich erkennt (inkrementelles Scraping via `fecha_desde`)
2. Vollständige Ficha-Daten extrahiert (Convocatoria, Cronograma, Dokumente)
3. Zugehörige PDF/DOCX-Dokumente herunterlädt
4. Daten strukturiert in PostgreSQL speichert
5. Automatische Benachrichtigungen mit allen relevanten Details versendet

---

### 🚀 Implementierte Features

#### Vollständig implementiert ✅

**seace-runner (REST Microservice):**
- `POST /seace/export` – Startet Scraping-Run mit Filtern (Departamento, Objeto, Año, fecha_desde)
- `GET /health` – Health-Check-Endpoint
- Token-basierte Authentifizierung (Bearer Token)
- Inkrementelles Scraping: stoppt automatisch bei Einträgen vor `fecha_desde`
- Multi-Page-Pagination mit PrimeFaces DataTable Widget
- Vollständige Ficha-Extraktion pro Licitación:
  - **Convocatoria** (Nomenclatura, Entidad, Monto, Normativa, etc.)
  - **Cronograma** (Etapas mit Fecha Inicio/Fin und Lugar)
  - **Documentos** (Metadaten + automatischer Download von PDF/DOCX/ZIP)
  - **Entidad Contratante** (RUC, Name)
  - **Acuerdos Comerciales**
- Automatischer Dokumenten-Download über Browser-Session (Alfresco ECM)
- Strukturiertes Logging mit Timestamps
- Debug-Screenshots pro Ficha
- NordVPN-Integration (peruanische IP für Geo-Blocking-Umgehung)
- Docker Compose Setup

**n8n Workflow:**
- HTTP Request zu seace-runner `/export`
- Split & Insert in PostgreSQL:
  - Tabelle `licitaciones` (mit UNIQUE auf `nomenclatura` für Deduplizierung)
  - Tabelle `cronograma`
  - Tabelle `documentos`
  - Tabelle `convocatoria`
  - Tabelle `entidad_contratante`
- If-Node verhindert doppelte Inserts für bereits bekannte Licitaciones
- Volumen-Sharing zwischen seace-runner und n8n für PDF-Zugriff

#### In Bearbeitung 🔧
- PDF-Analyse mit Claude API (Anforderungen, Erfahrungsnachweise, Fristen)
- Benachrichtigungssystem (E-Mail / Telegram)
- Async Job-System für lange Scraping-Runs (Job-ID + Polling)

#### Geplant 📋
- Tägliches automatisches Scheduling (Cron in n8n)
- Deploy auf Hetzner VPS (24/7 Betrieb)
- Dashboard für Licitacion-Übersicht

---

### 🛠️ Tech Stack

**Backend & API:**
- **Runtime:** Node.js 22 (ESM)
- **Framework:** Express.js
- **Web Automation:** Playwright 1.47 (Headless Chromium)
- **Portal:** SEACE mit PrimeFaces 5.x (Legacy JSF)

**Infrastructure & DevOps:**
- **Containerization:** Docker, Docker Compose
- **Networking:** NordVPN-Container (Peru-Geolokalisierung)
- **Orchestrierung:** n8n (Self-hosted)

**Data & Storage:**
- **Database:** PostgreSQL 14 mit pgvector
- **Dokumente:** Bind-Mount Volume (seace_downloads)
- **Data Processing:** ETL-Pipeline via n8n-Workflow

---

### 📁 Projektstruktur

```
seace-monitor/
├── seace-runner/
│   ├── src/
│   │   ├── server.js              # Express Entry Point
│   │   ├── middleware/
│   │   │   └── auth.js            # Bearer Token Auth
│   │   ├── routes/
│   │   │   └── seace.js           # /seace/export endpoint
│   │   ├── scraper/
│   │   │   ├── browser.js         # Playwright Browser Management
│   │   │   ├── filters.js         # SEACE Navigation & Filter
│   │   │   ├── results.js         # Pagination & Row Scraping
│   │   │   └── ficha.js           # Ficha Detail Scraping + Downloads
│   │   └── logger.js              # Structured Logging
│   ├── Dockerfile
│   └── package.json
├── seace_downloads/               # Heruntergeladene Dokumente (PDF/DOCX)
├── docker-compose.yml             # seace-runner + NordVPN
├── .env.example
└── README.md
```

---

### ⚙️ Installation & Nutzung

```bash
# Repository klonen
git clone https://github.com/Javier-Briceno/seace-monitor.git
cd seace-monitor

# Umgebungsvariablen konfigurieren
cp .env.example .env
# .env bearbeiten: NORDVPN_TOKEN, SEACE_AUTH_TOKEN, PORT

# Mit Docker ausführen
docker compose up -d

# Health-Check
curl http://localhost:3000/health

# Manuellen Scraping-Run triggern
curl -X POST http://localhost:3000/seace/export \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "departamento": "CUSCO",
    "objeto": "Obra",
    "anio": "2026",
    "fecha_desde": "2026-03-15"
  }'
```

**Beispiel-Response:**
```json
{
  "total": 6,
  "meta": {
    "fuente": "SEACE",
    "scraped_at": "2026-03-16T20:38:41.000Z",
    "filtros_aplicados": {
      "departamento": "CUSCO",
      "objeto": "Obra",
      "anio": "2026"
    }
  },
  "items": [
    {
      "numero": "1",
      "entidad": "MUNICIPALIDAD DISTRITAL DE CHAMACA",
      "nomenclatura": "LP-ABR-1-2026-MDCH-1",
      "monto": "---",
      "moneda": "Soles",
      "ficha": {
        "convocatoria": { "..." : "..." },
        "cronograma": [ { "Etapa": "Convocatoria", "Fecha Inicio": "02/02/2026" } ],
        "documentos": [
          {
            "Nro": "1",
            "Etapa": "Convocatoria",
            "Documento": "Bases Administrativas",
            "Archivo": {
              "uuid": "a462a02b-...",
              "filename": "bases.docx",
              "local_path": "downloads/a462a02b-..._bases.docx"
            }
          }
        ]
      }
    }
  ]
}
```

---

### 🎯 Technische Herausforderungen & Lösungen

**Geo-Blocking**
- Problem: SEACE nur von peruanischen IPs erreichbar
- Lösung: NordVPN-Container mit `CONNECT=Peru`

**PrimeFaces Legacy Portal**
- Problem: Altes JSF-Portal ohne stabile Widget-IDs, reCAPTCHA-Token, AJAX-Queues
- Lösung: Widget-Zugriff via `window[widgetVar]`-Pattern, `PrimeFaces.ajax.Queue.isEmpty()` als AJAX-Waiter, dynamische Selektor-Suche für instabile IDs

**Ficha-Navigation**
- Problem: Ficha öffnet als vollständige Seitennavigation (nicht neuer Tab), Rückkehr muss DataTable-Widget-Reinitialisierung abwarten
- Lösung: `waitForNavigation` + `waitForSelector('#tbFicha:idFormFichaSeleccion')`, nach Rückkehr `waitForFunction(() => window.widget_tbBuscador_... !== undefined)`

**Dokument-Downloads**
- Problem: Alfresco ECM-Downloads erfordern Session-Cookie von `alfprod.seace.gob.pe`, CORS blockiert direkte Requests, `alf_ticket` in URLs verfällt schnell
- Lösung: Download via `page.evaluate(() => jsCmsSeaceUtil.descargaPriv(uuid))` + `page.waitForEvent('download')` innerhalb der aktiven Browser-Session

**Inkrementelles Scraping**
- Problem: Tägliches Vollscraping aller Seiten ineffizient
- Lösung: `fecha_desde`-Parameter, Scraping stoppt bei erstem Item vor dem Datum

---

### 📊 Use Case & Business Value

| | Vorher (manuell) | Nachher (automatisch) |
|---|---|---|
| Täglicher Aufwand | 30-45 Min | 0 Min |
| Reaktionszeit | Stunden/Tage | Minuten |
| Datenspeicherung | Keine | PostgreSQL |
| Dokumentenzugriff | Manuell | Automatisch heruntergeladen |

---

### 📈 Projekthintergrund

Entwickelt als Teil meines **Data Engineering**-Portfolios während des
B.Sc. Informatik-Studiums an der **Universität Siegen**.

**Motivation:** Reales Problem lösen – tägliche manuelle Überwachung von
Ausschreibungen durch ein vollautomatisches System ersetzen.

---

### 📫 Kontakt

**Javier Briceño Ticona**
🔗 [LinkedIn](https://linkedin.com/in/javier-briceno-ticona)
💼 [Portfolio](https://github.com/Javier-Briceno)
📧 javierbricenoticona@gmail.com

---

---

## 🇬🇧 English Version

> ⚠️ **Status: Work in Progress** – Core scraping pipeline fully implemented.
> Currently: n8n workflow integration and PDF analysis in development.

### About This Project

Automated system for daily monitoring and extraction of procurement data
from Peru's SEACE portal (Sistema Electrónico de Contrataciones del Estado).
Consists of a REST microservice (`seace-runner`) and an n8n orchestration workflow.

**Background:** Peru's SEACE portal required manual daily checking for new
tender listings — a repetitive, time-consuming process. This project automates
the full pipeline: from extraction to notification.

**Project Goal:** Build a **daily monitoring system** that:
1. Automatically detects new listings daily (incremental scraping via `fecha_desde`)
2. Extracts complete ficha data (Convocatoria, Cronograma, Documents)
3. Downloads associated PDF/DOCX documents
4. Stores structured data in PostgreSQL
5. Sends automatic notifications with all relevant details

---

### 🚀 Features

#### Fully Implemented ✅

**seace-runner (REST Microservice):**
- `POST /seace/export` – Triggers scraping run with filters (Departamento, Objeto, Año, fecha_desde)
- `GET /health` – Health check endpoint
- Token-based authentication (Bearer Token)
- Incremental scraping: automatically stops at entries before `fecha_desde`
- Multi-page pagination with PrimeFaces DataTable Widget
- Complete ficha extraction per licitación:
  - **Convocatoria** (Nomenclatura, Entidad, Monto, Normativa, etc.)
  - **Cronograma** (Stages with Fecha Inicio/Fin and Lugar)
  - **Documentos** (Metadata + automatic download of PDF/DOCX/ZIP)
  - **Entidad Contratante** (RUC, Name)
  - **Acuerdos Comerciales**
- Automatic document download via browser session (Alfresco ECM)
- Structured logging with timestamps
- Debug screenshots per ficha
- NordVPN integration (Peruvian IP for geo-blocking bypass)
- Docker Compose setup

**n8n Workflow:**
- HTTP Request to seace-runner `/export`
- Split & Insert into PostgreSQL:
  - `licitaciones` table (UNIQUE on `nomenclatura` for deduplication)
  - `cronograma` table
  - `documentos` table
  - `convocatoria` table
  - `entidad_contratante` table
- If-node prevents duplicate inserts for already known licitaciones
- Volume sharing between seace-runner and n8n for PDF access

#### In Progress 🔧
- PDF analysis with Claude API (requirements, experience proofs, deadlines)
- Notification system (Email / Telegram)
- Async job system for long scraping runs (job ID + polling)

#### Planned 📋
- Daily automatic scheduling (Cron in n8n)
- Deploy to Hetzner VPS (24/7 operation)
- Dashboard for licitación overview

---

### 🛠️ Tech Stack

**Backend & API:**
- **Runtime:** Node.js 22 (ESM)
- **Framework:** Express.js
- **Web Automation:** Playwright 1.47 (Headless Chromium)
- **Portal:** SEACE with PrimeFaces 5.x (Legacy JSF)

**Infrastructure & DevOps:**
- **Containerization:** Docker, Docker Compose
- **Networking:** NordVPN container (Peru geolocation)
- **Orchestration:** n8n (Self-hosted)

**Data & Storage:**
- **Database:** PostgreSQL 14 with pgvector
- **Documents:** Bind-mount volume (seace_downloads)
- **Data Processing:** ETL pipeline via n8n workflow

---

### 📁 Project Structure

```
seace-monitor/
├── seace-runner/
│   ├── src/
│   │   ├── server.js              # Express entry point
│   │   ├── middleware/
│   │   │   └── auth.js            # Bearer token auth
│   │   ├── routes/
│   │   │   └── seace.js           # /seace/export endpoint
│   │   ├── scraper/
│   │   │   ├── browser.js         # Playwright browser management
│   │   │   ├── filters.js         # SEACE navigation & filters
│   │   │   ├── results.js         # Pagination & row scraping
│   │   │   └── ficha.js           # Ficha detail scraping + downloads
│   │   └── logger.js              # Structured logging
│   ├── Dockerfile
│   └── package.json
├── seace_downloads/               # Downloaded documents (PDF/DOCX)
├── docker-compose.yml             # seace-runner + NordVPN
├── .env.example
└── README.md
```

---

### ⚙️ Installation & Usage

```bash
# Clone repository
git clone https://github.com/Javier-Briceno/seace-monitor.git
cd seace-monitor

# Configure environment variables
cp .env.example .env
# Edit .env: NORDVPN_TOKEN, SEACE_AUTH_TOKEN, PORT

# Run with Docker
docker compose up -d

# Health check
curl http://localhost:3000/health

# Trigger manual scraping run
curl -X POST http://localhost:3000/seace/export \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "departamento": "CUSCO",
    "objeto": "Obra",
    "anio": "2026",
    "fecha_desde": "2026-03-15"
  }'
```

---

### 🎯 Technical Challenges & Solutions

**Geo-blocking**
- Problem: SEACE only accessible from Peruvian IPs
- Solution: NordVPN container with `CONNECT=Peru`

**PrimeFaces Legacy Portal**
- Problem: Old JSF portal with unstable widget IDs, reCAPTCHA tokens, AJAX queues
- Solution: Widget access via `window[widgetVar]` pattern, `PrimeFaces.ajax.Queue.isEmpty()` as AJAX waiter, dynamic selector search for unstable IDs

**Ficha Navigation**
- Problem: Ficha opens as full page navigation (not new tab), return must await DataTable widget reinitialization
- Solution: `waitForNavigation` + `waitForSelector('#tbFicha:idFormFichaSeleccion')`, after return `waitForFunction(() => window.widget_tbBuscador_... !== undefined)`

**Document Downloads**
- Problem: Alfresco ECM downloads require session cookie from `alfprod.seace.gob.pe`, CORS blocks direct requests, `alf_ticket` in URLs expires quickly
- Solution: Download via `page.evaluate(() => jsCmsSeaceUtil.descargaPriv(uuid))` + `page.waitForEvent('download')` within active browser session

**Incremental Scraping**
- Problem: Daily full scraping of all pages is inefficient
- Solution: `fecha_desde` parameter, scraping stops at first item before the date

---

### 📊 Use Case & Business Value

| | Before (manual) | After (automated) |
|---|---|---|
| Daily effort | 30-45 min | 0 min |
| Response time | Hours/days | Minutes |
| Data storage | None | PostgreSQL |
| Document access | Manual | Auto-downloaded |

---

### 📈 Project Context

Developed as part of my **Data Engineering** portfolio during
B.Sc. Computer Science studies at **Universität Siegen**.

**Motivation:** Solve a real problem — replace daily manual monitoring
of procurement listings with a fully automated system.

---

### 📫 Contact

**Javier Briceño Ticona**
🔗 [LinkedIn](https://linkedin.com/in/javier-briceno-ticona)
💼 [Portfolio](https://github.com/Javier-Briceno)
📧 javierbricenoticona@gmail.com

B.Sc. Computer Science Student | Universität Siegen
Focus: Data Engineering & ETL Pipelines

---

### 📝 License

MIT License – feel free to use this project as reference.
