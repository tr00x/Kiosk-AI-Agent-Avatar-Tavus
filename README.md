# AI Dental Kiosk — Tavus CVI + Open Dental

An AI-powered patient check-in kiosk for dental clinics. Patients interact with **Emma**, a conversational video avatar powered by [Tavus CVI](https://www.tavus.io/), to verify identity, check in for appointments, view balances, and more — all by speaking naturally.

Built for **All Nassau Dental** (Hempstead, NY) and integrated directly with **Open Dental** practice management software via MySQL.

![Kiosk Screenshot](https://img.shields.io/badge/status-production-brightgreen) ![React](https://img.shields.io/badge/React-18.3-61DAFB?logo=react) ![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi) ![Tavus](https://img.shields.io/badge/Tavus-CVI-blueviolet) ![Daily.co](https://img.shields.io/badge/Daily.co-WebRTC-orange)

---

## How It Works

```
┌─────────────┐     WebRTC (Daily.co)     ┌──────────────┐
│   Patient    │◄────── Video/Audio ──────►│  Tavus CVI   │
│   (Kiosk)   │                            │  AI Avatar   │
│             │                            │   "Emma"     │
└──────┬──────┘                            └──────┬───────┘
       │                                          │
       │  React UI                     Tool calls │
       │  (transcript, dashboard)      (webhooks) │
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

**Key flow:**
1. Patient taps "Start Check-in" on the kiosk touchscreen
2. Emma (AI avatar) greets them and asks for name + date of birth
3. Backend verifies identity against Open Dental DB with **fuzzy matching** (exact → SOUNDEX → difflib)
4. Patient dashboard appears on screen with appointment details, balance, and a check-in button
5. Emma confirms verbally while the patient can also interact via the touchscreen

---

## Features

- **Conversational AI Avatar** — Tavus CVI replica with natural speech, lip-sync, and real-time responses
- **Fuzzy Name Matching** — 3-tier verification (exact → SOUNDEX → SequenceMatcher) handles misheard names
- **Multilingual** — English, Spanish, and Russian (voice + UI)
- **Patient Dashboard** — Real-time display of appointment, balance, and upcoming visits
- **One-Tap Check-In** — Both voice-driven and touchscreen check-in
- **Staff Sidebar** — Manual check-in tool for front desk staff
- **Open Dental Integration** — Direct MySQL queries for patients, appointments, balances, procedures
- **HIPAA Audit Logging** — Every tool call logged with timestamps
- **SMS Reminders** — Twilio integration for appointment reminders
- **Appointment Booking** — Voice-driven appointment requests

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **AI Avatar** | [Tavus CVI](https://www.tavus.io/) (Conversational Video Interface) |
| **Video/Audio** | [Daily.co](https://www.daily.co/) WebRTC SDK |
| **Frontend** | React 18 + Vite |
| **Backend** | FastAPI (Python, async) |
| **Database** | MySQL (Open Dental) via aiomysql |
| **SMS** | Twilio |
| **Styling** | CSS with glassmorphic dark theme |

---

## Project Structure

```
├── backend/
│   ├── main.py              # FastAPI app, routes, session management
│   ├── tools.py             # Tool handlers (verify, check-in, balance, book, SMS)
│   ├── setup_persona.py     # Tavus persona creation (prompt, objectives, guardrails)
│   ├── tavus.py             # Tavus CVI API client
│   ├── db.py                # Async MySQL connection pool
│   ├── audit.py             # HIPAA compliance logging
│   ├── config.py            # Environment settings
│   ├── models.py            # Pydantic request/response schemas
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Root state machine (idle → active → ended)
│   │   ├── index.css            # Global styles (glassmorphic theme)
│   │   ├── components/
│   │   │   ├── Avatar.jsx           # Tavus video stream container
│   │   │   ├── PatientDashboard.jsx # Verified patient info card
│   │   │   ├── IdleScreen.jsx       # Welcome screen + language selector
│   │   │   ├── ManualCheckin.jsx    # Staff sidebar for manual lookup
│   │   │   ├── Transcript.jsx      # Live speech captions
│   │   │   ├── Controls.jsx        # Session controls
│   │   │   ├── StatusDot.jsx       # Connection status indicator
│   │   │   └── ActivityBar.jsx     # Tool execution progress
│   │   └── hooks/
│   │       ├── useSession.js        # Backend session lifecycle
│   │       └── useTavusCall.js      # Daily.co + Tavus integration
│   ├── package.json
│   ├── vite.config.js
│   └── .env.example
│
├── .gitignore
└── README.md
```

---

## Setup

### Prerequisites

- **Node.js** 18+
- **Python** 3.10+
- **MySQL** (Open Dental instance)
- **Tavus** API key + Replica ID ([tavus.io](https://www.tavus.io/))
- **ngrok** or similar tunnel (Tavus webhooks need a public URL)

### 1. Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials (see below)

# Create Tavus persona (one-time)
python setup_persona.py
# Copy the persona ID to .env → TAVUS_PERSONA_ID

# Start server
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install

# Configure environment
cp .env.example .env

# Development (with hot reload + API proxy)
npm run dev
# → http://localhost:5173

# Production build
npm run build
```

### 3. Expose Backend for Tavus Webhooks

Tavus needs to reach your backend for tool call webhooks:

```bash
ngrok http 8000
# Copy the https URL → backend/.env → BACKEND_URL
```

---

## Environment Variables

### `backend/.env`

```env
# Tavus CVI
TAVUS_API_KEY=tvs_xxx
TAVUS_PERSONA_ID=p_xxx          # from setup_persona.py
TAVUS_REPLICA_ID=r_xxx          # from Tavus dashboard

# Open Dental MySQL
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=
DB_NAME=opendental

# Public URL for Tavus webhooks
BACKEND_URL=https://your-backend.ngrok.io

# Twilio (optional — for SMS reminders)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=+1xxxxxxxxxx

# CORS
FRONTEND_URL=http://localhost:5173

# Session limits
MAX_CALL_DURATION=300
PARTICIPANT_LEFT_TIMEOUT=30
```

### `frontend/.env`

```env
VITE_API_URL=http://localhost:8000
```

---

## API Endpoints

### Session Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/session/start` | Create Tavus conversation (returns `conversation_url`) |
| POST | `/api/session/end` | End active conversation |

### Tool Webhooks (called by Tavus → injected back via Daily.co)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/tools/verify_patient` | Identity verification (name + DOB, fuzzy matching) |
| POST | `/tools/get_today_appointment` | Fetch today's appointment |
| POST | `/tools/check_in_patient` | Mark patient as checked in |
| POST | `/tools/get_balance` | Account balance breakdown |
| POST | `/tools/get_appointments` | Upcoming appointments list |
| POST | `/tools/book_appointment` | Request appointment booking |
| POST | `/tools/send_sms_reminder` | Send SMS reminder via Twilio |

### Staff Manual Check-in

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/manual/search` | Search patients by last name + DOB |
| POST | `/api/manual/checkin` | Check in appointment by ID |

---

## Fuzzy Name Matching

Patients speaking to an AI avatar often have their names misheard. The verification system uses 3 tiers:

| Tier | Method | Example |
|------|--------|---------|
| 1 | **Exact match** (SQL `LOWER()`) | "Ramirez" → finds "Ramirez" |
| 2 | **SOUNDEX** (MySQL built-in) | "Ramiris" → finds "Ramirez" |
| 3 | **difflib** (Python `SequenceMatcher > 0.6`) | "Ramires" → finds "Ramirez" |

Each tier only runs if the previous returned zero results. DOB is always required as a second factor.

---

## How Tavus Tool Calls Work

Tavus CVI webhooks are **one-way** — they notify your backend but don't automatically feed results back to the LLM. This project handles the full loop:

```
1. Emma decides to call verify_patient(name, dob)
2. Tavus sends webhook → Backend /tools/verify_patient
3. Frontend receives tool_call event via Daily.co app-message
4. Frontend calls Backend API → gets result
5. Frontend formats result as text message
6. Frontend injects via Daily.co conversation.respond
7. Emma receives result and responds to patient
```

This means the frontend acts as the **orchestrator** between Tavus and the backend.

---

## Persona Configuration

The AI persona is defined in `backend/setup_persona.py` and includes:

- **System prompt** — Emma's personality, clinic context, screen awareness
- **Objectives** — Structured conversation flow (greet → verify → check-in → help)
- **Tools** — Function definitions for all 7 tools
- **Guardrails** — Stay in scope, protect patient data, be concise
- **STT hotwords** — Common patient surnames for better speech recognition
- **Multilingual greetings** — Custom greetings in EN/ES/RU

To update the persona after changes:
```bash
cd backend
python setup_persona.py
# Update TAVUS_PERSONA_ID in .env with the new ID
```

---

## License

This project is proprietary to All Nassau Dental. Not licensed for redistribution.
