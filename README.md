# AI Kiosk — Dental Clinic Receptionist with Conversational Video Avatar

An AI-powered self-service kiosk for dental clinics. Patients interact with a **real-time video avatar** that verifies identity, shows appointments, balances, and answers questions — all by voice on a touchscreen.

Powered by [Tavus CVI](https://www.tavus.io/) + [Daily.co](https://www.daily.co/) WebRTC + [Open Dental](https://opendental.com/) integration.

![React](https://img.shields.io/badge/React-18.3-61DAFB?logo=react) ![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi) ![Tavus](https://img.shields.io/badge/Tavus-CVI-blueviolet) ![Daily.co](https://img.shields.io/badge/Daily.co-WebRTC-orange) ![MySQL](https://img.shields.io/badge/MySQL-Open_Dental-4479A1?logo=mysql) ![PWA](https://img.shields.io/badge/PWA-Installable-5A0FC8)

---

## How It Works

```
┌─────────────┐     WebRTC (Daily.co)     ┌──────────────┐
│   Patient    │◄────── Video/Audio ──────►│  Tavus CVI   │
│   (Kiosk)   │                            │  AI Avatar   │
└──────┬──────┘                            └──────┬───────┘
       │                                          │
       │  React PWA                    Tool calls │
       │  (transcript, dashboard)                 │
       │                                          │
       ▼                                          ▼
┌──────────────┐     REST API          ┌──────────────────┐
│   Frontend   │◄────────────────────►│     Backend       │
│   React/Vite │                       │  FastAPI + MySQL  │
└──────────────┘                       └────────┬─────────┘
                                                │
                                                ▼
                                       ┌──────────────────┐
                                       │   Open Dental    │
                                       │    MySQL DB      │
                                       └──────────────────┘
```

**Patient flow:**
1. Tap "Start" on the kiosk → AI avatar (Jenny) appears and greets the patient
2. Jenny asks for name + date of birth
3. Backend runs **3-tier fuzzy matching** against Open Dental DB
4. Dashboard card appears with appointment, balance, upcoming visits
5. Jenny narrates key info from screen, answers questions, then says goodbye
6. Session auto-ends — kiosk returns to idle screen

---

## Features

- **Conversational AI Avatar** — Tavus CVI replica with natural video, lip-sync, real-time voice
- **Read-Only Information Mode** — Verifies identity, shows info, answers questions. Check-in/booking handled by front desk
- **Fuzzy Name Matching** — 3-tier verification (exact SQL → SOUNDEX → difflib) handles misheard names
- **Multilingual** — English, Spanish, Russian (voice + UI)
- **Patient Dashboard** — Real-time card with appointment details, balance breakdown, upcoming visits
- **Screen-Aware AI** — Avatar knows what's on screen, narrates key info briefly
- **Staff Manual Check-in** — Hidden sidebar for front desk override (search by name + DOB)
- **Open Dental Integration** — Direct MySQL queries for patients, appointments, balances
- **HIPAA Audit Logging** — Every tool call logged with timestamps
- **PWA** — Installable fullscreen app for kiosk touchscreens
- **Inactivity Guard** — Auto-nudge after 15s silence, auto-end after 30s, goodbye detection
- **Session Hard Cap** — 3 min max on Tavus side + backend reaper for stale sessions
- **Auto-Reconnect** — Retry on network errors, DB health checks, background reconnect

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **AI Avatar** | [Tavus CVI](https://www.tavus.io/) (Conversational Video Interface) |
| **Video/Audio** | [Daily.co](https://www.daily.co/) WebRTC SDK |
| **Frontend** | React 18 + Vite (PWA) |
| **Backend** | FastAPI (Python, async) |
| **Database** | MySQL ([Open Dental](https://opendental.com/)) via aiomysql |
| **Process Manager** | PM2 |
| **Styling** | CSS glassmorphic dark theme |

---

## Project Structure

```
├── backend/
│   ├── main.py              # FastAPI app, routes, session management, stale session reaper
│   ├── tools.py             # Tool handlers (verify, balance, appointments)
│   ├── setup_persona.py     # Tavus persona creation (prompt, objectives, guardrails)
│   ├── tavus.py             # Tavus CVI API client
│   ├── db.py                # Async MySQL pool with background reconnect
│   ├── audit.py             # HIPAA compliance logging
│   ├── config.py            # Environment settings
│   ├── models.py            # Pydantic request/response schemas
│   └── requirements.txt
│
├── frontend/
│   ├── index.html               # PWA entry point with service worker
│   ├── public/
│   │   ├── manifest.json        # PWA manifest (fullscreen, dark theme)
│   │   ├── sw.js                # Service worker (cache static assets)
│   │   ├── jenny-idle.mp4       # Idle video placeholder
│   │   ├── clinic-logo.jpg
│   │   └── favicon.svg
│   ├── src/
│   │   ├── App.jsx              # Root state machine + inactivity guard
│   │   ├── index.css            # Glassmorphic dark theme
│   │   ├── components/
│   │   │   ├── Avatar.jsx           # Video stream + idle placeholder with blur
│   │   │   ├── PatientDashboard.jsx # Verified patient info card (read-only)
│   │   │   ├── IdleScreen.jsx       # Welcome screen + language selector
│   │   │   ├── ManualCheckin.jsx    # Staff sidebar
│   │   │   ├── Transcript.jsx       # Live speech captions
│   │   │   ├── Controls.jsx         # End session (double-tap confirm)
│   │   │   ├── StatusDot.jsx        # Connection status indicator
│   │   │   └── ActivityBar.jsx      # Tool execution progress
│   │   └── hooks/
│   │       ├── useSession.js        # Backend session lifecycle (retry + timeout)
│   │       └── useTavusCall.js      # Daily.co + Tavus tool orchestration
│   ├── package.json
│   └── vite.config.js
│
├── ecosystem.config.cjs     # PM2 process config
├── start.sh                 # One-command production start (auto-detects LAN IP)
├── stop.sh                  # Stop all services
├── .gitignore
└── README.md
```

---

## Quick Start (Production / Kiosk)

### Prerequisites

- **Node.js** 18+
- **Python** 3.10+
- **MySQL** (Open Dental instance on local network)
- **Tavus** API key + Replica ID — [tavus.io](https://www.tavus.io/)

### 1. Install dependencies

```bash
# Root (PM2)
npm install

# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
```

### 2. Configure environment

```bash
cp backend/.env.example backend/.env
# Edit backend/.env with your credentials (see Environment Variables below)
```

### 3. Create AI persona (one-time)

```bash
cd backend
source venv/bin/activate
python3 setup_persona.py
# Copy the printed persona_id into .env → TAVUS_PERSONA_ID
```

### 4. Launch

```bash
./start.sh
```

This will:
- Auto-detect your LAN IP
- Build frontend with correct API URL
- Start backend (port 8000) + frontend (port 5173) via PM2
- Print the kiosk URL

Open the URL on the kiosk tablet/screen. Install as PWA for fullscreen mode.

### Stop

```bash
./stop.sh
```

---

## Development

```bash
# Backend (with hot reload)
cd backend
source venv/bin/activate
LOG_LEVEL=DEBUG uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Frontend (with Vite dev server + proxy)
cd frontend
npm run dev
```

---

## Environment Variables

### `backend/.env`

```env
# Tavus CVI
TAVUS_API_KEY=your_api_key
TAVUS_PERSONA_ID=p_xxx          # from setup_persona.py
TAVUS_REPLICA_ID=r_xxx          # from Tavus dashboard

# Open Dental MySQL
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=
DB_NAME=opendental

# Backend URL (for webhook context)
BACKEND_URL=http://localhost:8000

# CORS (auto-set by start.sh, or set manually)
CORS_ORIGINS=http://localhost:5173

# Logging
LOG_LEVEL=INFO

# Session limits
MAX_CALL_DURATION=180
PARTICIPANT_LEFT_TIMEOUT=10
```

---

## API Endpoints

### Session

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/session/start` | Create Tavus conversation |
| POST | `/api/session/end` | End active conversation |

### Tool Webhooks (frontend-orchestrated)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/tools/verify_patient` | Identity verification (fuzzy matching) |
| POST | `/tools/get_today_appointment` | Today's appointment |
| POST | `/tools/get_balance` | Account balance |
| POST | `/tools/get_appointments` | Upcoming appointments |

### Staff

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/manual/search` | Search today's patients |
| POST | `/api/manual/checkin` | Manual check-in |

---

## Architecture Notes

### Tool Call Flow

Tavus webhooks are one-way — results must be injected back. The frontend orchestrates:

```
Avatar decides to call tool → Tavus event → Daily.co app-message → Frontend
→ Frontend calls Backend REST → gets result → formats text
→ Frontend injects via conversation.respond → Tavus LLM → Avatar speaks
```

### Session Protection

| Layer | Mechanism | Timing |
|-------|-----------|--------|
| Frontend | Inactivity nudge | 15s silence |
| Frontend | Auto-end call | 30s silence |
| Frontend | Goodbye detection | 4s after farewell phrase |
| Tavus | `max_call_duration` | 3 min |
| Tavus | `participant_left_timeout` | 10s |
| Backend | Stale session reaper | Every 60s, kills sessions > 3.5 min |

### Fuzzy Name Matching

| Tier | Method | Example |
|------|--------|---------|
| 1 | Exact SQL match + DOB | "Ramirez" → "Ramirez" |
| 2 | SOUNDEX phonetic + DOB | "Ramiris" → "Ramirez" |
| 3 | difflib ratio > 0.6 + DOB | "Ramires" → "Ramirez" |

---

## License

MIT
