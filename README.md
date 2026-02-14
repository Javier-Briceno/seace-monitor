# SEACE Data Acquisition & Alert Microservice

*English version below / Deutsche Version zuerst*

---

## 🇩🇪 Deutsche Version

> ⚠️ **Status: Work in Progress** – Kernfunktionalität implementiert. 
> Aktuell Optimierung des Detail-Extraktionsmoduls.

### Über das Projekt

Automatisierter REST-Microservice zur täglichen Überwachung und Extraktion 
von Ausschreibungsdaten aus dem peruanischen Beschaffungsportal SEACE 
(Sistema Electrónico de Contrataciones del Estado) mit intelligentem 
Benachrichtigungssystem.

**Hintergrund:** Dieses Projekt entstand aus einem praktischen Bedarf: 
Um neue öffentliche Ausschreibungen auf dem peruanischen SEACE-Portal 
zu finden, musste die Website täglich manuell überprüft werden. Dieser
repetitive und zeitaufwändige Prozess führte zur Entwicklung einer 
vollständig automatisierten Lösung.

**Projektziel:** Entwicklung eines **täglichen Monitoring-Systems**, das:
1. Neue Ausschreibungen automatisch täglich erkennt
2. Relevante Änderungen identifiziert (neue Verfahren/Projekte, Status-Updates)
3. Automatische Benachrichtigungen/Alerts mit allen Details zu jeder neuen Veröffentlichung versendet
4. Die manuelle Kontrolle vollständig überflüssig macht

**Technisches Ziel:** Demonstration von:
- Scheduled Task Automation (Cron-basierte Orchestrierung)
- Change Detection & Data Diffing
- Web Scraping at Scale
- Microservice-Architektur mit Alert-System
- Docker-Containerisierung
- RESTful API Design

---

### 🚀 Implementierte Features

#### Vollständig implementiert ✅
- **Automatisierte tägliche Extraktion** von 500+ Ausschreibungen pro Workflow-Durchlauf
- **Multi-Page-Verarbeitung** von Suchergebnissen mit intelligenter Paginierung
- **ETL-Pipeline** mit strukturierter JSON-Transformation und Datenspeicherung
- **Produktionsreife Infrastruktur:** Docker Compose + VPN-Networking (NordVPN)
- **Health-Check-Endpoints** und strukturiertes Logging für Monitoring
- **Token-basierte Authentifizierung** für API-Sicherheit
- **Change Detection Logic** zur Identifizierung neuer Ausschreibungen (Basis-Implementation)

#### In Bearbeitung 🔧
- Optimierung des Detail-Extraktionsmoduls (Debugging von Edge Cases in der 
  Seitenpaginierung)
- Integration des Alert/Notification-Systems (E-Mail oder Messaging-Integration geplant)
- Persistente Datenspeicherung mit PostgreSQL für historischen Datenvergleich

#### Geplant 📋
- Automatisches Scheduling (täglich um 08:00 Uhr Ortszeit Peru)
- E-Mail-Benachrichtigungen bei neuen relevanten Ausschreibungen
- Dashboard für Alert-Übersicht und Konfiguration
- Filterkriterien für relevante Ausschreibungen (Keywords, Kategorien, Budgetgrenzen)

---

### 🛠️ Tech Stack

**Backend & API:**
- **Runtime:** Node.js (Express)
- **Web Automation:** Playwright (headless browser automation)

**Infrastructure & DevOps:**
- **Containerization:** Docker, Docker Compose
- **Networking:** NordVPN-Integration (Geolokalisierung für peruanische Server)
- **Scheduled Execution:** Node-cron (geplant)

**Data & Storage:**
- **Database (geplant):** PostgreSQL (persistente Datenspeicherung & Änderungshistorie)
- **Data Processing:** ETL-Pipeline mit JSON-Transformation

**Architecture:**
- RESTful Microservice
- Event-driven alerts (geplant)

---

### 📁 Projektstruktur

```
seace-microservice/
├── src/
│   ├── routes/              # API-Endpoints
│   ├── services/            
│   │   ├── scraper.js      # Hauptextraktionslogik (Playwright)
│   │   ├── etl.js          # Datenverarbeitungs-Pipeline
│   │   ├── detector.js     # Change Detection Logic (in dev)
│   │   └── notifier.js     # Alert-System (geplant)
│   ├── utils/              # Helper-Funktionen
│   ├── config/             # Konfiguration & Umgebungsvariablen
│   └── models/             # Datenmodelle (geplant)
├── docker-compose.yml      # Container-Orchestrierung (App + VPN)
├── Dockerfile
├── .env.example            # Template für Umgebungsvariablen
└── README.md
```

---

### ⚙️ Installation & Nutzung

```bash
# Repository klonen
git clone https://github.com/Javier-Briceno/seace-microservice.git
cd seace-microservice

# Umgebungsvariablen konfigurieren
cp .env.example .env
# .env bearbeiten mit eigenen Credentials

# Dependencies installieren
npm install

# Mit Docker ausführen
docker-compose up -d

# API-Health-Check
curl http://localhost:3000/health

# Manuellen Scraping-Run triggern
curl -X POST http://localhost:3000/api/scrape \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

### 🎯 Technische Herausforderungen & Lösungen

**Herausforderung 1: Geo-Blocking**  
🔧 **Problem:** SEACE-Portal nur von peruanischen IP-Adressen erreichbar  
✅ **Lösung:** Integration von NordVPN-Container für peruanische IP-Lokalisierung

**Herausforderung 2: Dynamische Inhalte**  
🔧 **Problem:** JavaScript-basierte Rendering verzögert Datenextraktion  
✅ **Lösung:** Playwright statt einfacher HTTP-Requests für vollständiges DOM-Rendering

**Herausforderung 3: Skalierbarkeit & tägliche Ausführung**  
🔧 **Problem:** System muss zuverlässig jeden Tag ohne manuelle Intervention laufen  
✅ **Lösung:** Docker-basierte Architektur + Node-cron für automatisches Scheduling (in Implementation)

**Herausforderung 4: Change Detection**  
🔧 **Problem:** Identifizierung neuer Ausschreibungen erfordert historischen Datenvergleich  
✅ **Lösung:** PostgreSQL-Datenbank mit Timestamp-basiertem Tracking (in Planung)

**Bekannte Issues:**  
- Detail-Extraktionsmodul hat intermittierende Fehler bei bestimmten 
  Paginierungsmustern (aktiv in Bearbeitung)
- Alert-System noch nicht implementiert (nächster Meilenstein)

---

### 📊 Use Case & Business Value

**Problem (Ist-Zustand):**
- Manueller täglicher Check: **30-45 Minuten** pro Tag
- Hohe Fehleranfälligkeit durch manuelle Überprüfung
- Verzögerte Reaktion auf neue Ausschreibungen
- Keine strukturierte Datenspeicherung

**Lösung (Soll-Zustand):**
- **Vollautomatischer täglicher Scan**: 0 Minuten manuelle Arbeit
- **Sofortige Benachrichtigung** bei relevanten neuen Ausschreibungen
- **Historisches Tracking** aller Änderungen
- **Strukturierte Datenbank** für Analysen und Berichte

**ROI:** ~10-15 Stunden Zeitersparnis pro Monat + erhöhte Reaktionsgeschwindigkeit

---

### 📈 Projekthintergrund

Entwickelt im Rahmen meines **Data Engineering**-Portfolios während des 
B.Sc. Informatik-Studiums an der **Universität Siegen** (Dez 2025 - Feb 2026).

**Motivation:** Reales Problem meines Vaters lösen – tägliche manuelle 
Überwachung von Ausschreibungen durch automatisches Alert-System ersetzen.

**Gelerntes:**
- Production-ready Infrastructure-Setup mit Docker
- Umgang mit geografischen Einschränkungen (Geo-blocking)
- Robuste Error-Handling-Strategien für Web Scraping
- Containerisierung komplexer Multi-Service-Architekturen
- Change Detection & Data Diffing Patterns
- Scheduling & Automation Best Practices

---

### 📫 Kontakt

**Javier Briceño Ticona**  
🔗 [LinkedIn](https://linkedin.com/in/javier-briceno-ticona)  
💼 [Portfolio](https://github.com/Javier-Briceno)  
📧 javierbricenoticona@gmail.com

Informatik B.Sc. Student | Universität Siegen  
Schwerpunkt: Data Engineering & ETL-Pipelines

---

### 📝 Lizenz

MIT License – dieses Projekt kann als Referenz genutzt werden.

---
---

## 🇬🇧 English Version

> ⚠️ **Status: Work in Progress** – Core functionality operational. 
> Currently optimizing detail extraction module.

### About This Project

Automated REST API microservice for daily monitoring and extraction of 
procurement data from Peru's SEACE portal (Sistema Electrónico de 
Contrataciones del Estado) with intelligent alert system.

**Background:** This project emerged from a practical need:
To find new public tenders on Peru’s SEACE portal, the website had 
to be checked manually every day. This repetitive and time-consuming 
process led to the development of a fully automated solution.

**Project Goal:** Develop a **daily monitoring system** that:

1. Automatically detects new tender listings every day
2. Identifies relevant changes (new procedures/projects, status updates)
3. Sends automatic notifications/alerts with full details for each new publication
4. Completely eliminates the need for manual checking


**Technical Goal:** Demonstrate proficiency in:
- Scheduled task automation (cron-based orchestration)
- Change detection & data diffing
- Web scraping at scale
- Microservice architecture with alert system
- Docker containerization
- RESTful API design

---

### 🚀 Features

#### Fully Implemented ✅
- **Automated daily extraction** of 500+ procurement listings per workflow run
- **Multi-page processing** with intelligent pagination handling
- **ETL pipeline** with structured JSON transformation and data storage
- **Production infrastructure:** Docker Compose + VPN networking (NordVPN)
- **Health check endpoints** and structured logging for monitoring
- **Token-based authentication** for API security
- **Change detection logic** for identifying new listings (basic implementation)

#### In Progress 🔧
- Detail extraction module optimization (debugging edge cases in page 
  pagination logic)
- Alert/Notification system integration (email or messaging integration planned)
- Persistent data storage with PostgreSQL for historical data comparison

#### Planned 📋
- Automatic scheduling (daily at 08:00 Peru local time)
- Email notifications for new relevant tender listings
- Dashboard for alert overview and configuration
- Filter criteria for relevant listings (keywords, categories, budget thresholds)

---

### 🛠️ Tech Stack

**Backend & API:**
- **Runtime:** Node.js (Express)
- **Web Automation:** Playwright (headless browser automation)

**Infrastructure & DevOps:**
- **Containerization:** Docker, Docker Compose
- **Networking:** NordVPN integration (geolocation for Peruvian servers)
- **Scheduled Execution:** Node-cron (planned)

**Data & Storage:**
- **Database (planned):** PostgreSQL (persistent storage & change history)
- **Data Processing:** ETL pipeline with JSON transformation

**Architecture:**
- RESTful microservice
- Event-driven alerts (planned)

---

### 📁 Project Structure

```
seace-microservice/
├── src/
│   ├── routes/              # API endpoints
│   ├── services/            
│   │   ├── scraper.js      # Main extraction logic (Playwright)
│   │   ├── etl.js          # Data processing pipeline
│   │   ├── detector.js     # Change detection logic (in dev)
│   │   └── notifier.js     # Alert system (planned)
│   ├── utils/              # Helper functions
│   ├── config/             # Configuration & environment variables
│   └── models/             # Data models (planned)
├── docker-compose.yml      # Container orchestration (App + VPN)
├── Dockerfile
├── .env.example            # Environment variables template
└── README.md
```

---

### ⚙️ Installation & Usage

```bash
# Clone repository
git clone https://github.com/Javier-Briceno/seace-microservice.git
cd seace-microservice

# Configure environment variables
cp .env.example .env
# Edit .env with your credentials

# Install dependencies
npm install

# Run with Docker
docker-compose up -d

# API health check
curl http://localhost:3000/health

# Trigger manual scraping run
curl -X POST http://localhost:3000/api/scrape \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

### 🎯 Technical Challenges & Solutions

**Challenge 1: Geo-blocking**  
🔧 **Problem:** SEACE portal only accessible from Peruvian IP addresses  
✅ **Solution:** NordVPN container integration for Peruvian IP localization

**Challenge 2: Dynamic Content**  
🔧 **Problem:** JavaScript-based rendering delays data extraction  
✅ **Solution:** Playwright instead of simple HTTP requests for complete DOM rendering

**Challenge 3: Scalability & Daily Execution**  
🔧 **Problem:** System must run reliably every day without manual intervention  
✅ **Solution:** Docker-based architecture + Node-cron for automatic scheduling (in implementation)

**Challenge 4: Change Detection**  
🔧 **Problem:** Identifying new listings requires historical data comparison  
✅ **Solution:** PostgreSQL database with timestamp-based tracking (planned)

**Known Issues:**  
- Detail extraction module has intermittent errors with certain pagination 
  patterns (actively being addressed)
- Alert system not yet implemented (next milestone)

---

### 📊 Use Case & Business Value

**Problem (Current State):**
- Manual daily check: **30-45 minutes** per day
- High error rate from manual verification
- Delayed response to new tender opportunities
- No structured data storage

**Solution (Target State):**
- **Fully automated daily scan**: 0 minutes manual work
- **Immediate notification** for relevant new listings
- **Historical tracking** of all changes
- **Structured database** for analysis and reporting

**ROI:** ~10-15 hours time savings per month + increased response speed

---

### 📈 Project Context

Developed as part of my **Data Engineering** portfolio during B.Sc. 
Computer Science studies at **Universität Siegen** (Dec 2025 - Feb 2026).

**Motivation:** Solve my father's real problem – replace daily manual 
monitoring of procurement listings with an automated alert system.

**Key Learnings:**
- Production-ready infrastructure setup with Docker
- Handling geographic restrictions (geo-blocking)
- Robust error handling strategies for web scraping
- Containerization of complex multi-service architectures
- Change detection & data diffing patterns
- Scheduling & automation best practices

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
