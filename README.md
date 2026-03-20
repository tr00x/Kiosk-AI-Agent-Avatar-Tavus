# AI Kiosk — Dental Clinic Receptionist with Conversational Video Avatar

An AI-powered self-service kiosk for dental clinics. Patients interact with a **real-time video avatar** that verifies identity, checks in, books appointments, shows balances, and registers new patients — all by voice and touch on a kiosk screen.

Powered by [Tavus CVI](https://www.tavus.io/) + [Daily.co](https://www.daily.co/) WebRTC + [Open Dental](https://opendental.com/) integration.

![React](https://img.shields.io/badge/React-18.3-61DAFB?logo=react) ![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi) ![Tavus](https://img.shields.io/badge/Tavus-CVI-blueviolet) ![Daily.co](https://img.shields.io/badge/Daily.co-WebRTC-orange) ![MySQL](https://img.shields.io/badge/MySQL-Open_Dental-4479A1?logo=mysql) ![PWA](https://img.shields.io/badge/PWA-Installable-5A0FC8)

<p align="center">
  <img src="docs/screenshot-idle.jpg" alt="Idle Screen" width="400" />
  <img src="docs/screenshot-session.jpg" alt="Active Session" width="400" />
</p>

---

## How It Works

```
┌─────────────┐     WebRTC (Daily.co)     ┌──────────────┐
│   Patient    │◄────── Video/Audio ──────►│  Tavus CVI   │
│   (Kiosk)    │                           │  AI Avatar   │
└──────┬──────┘                            └──────┬───────┘
       │                                          │
       │  React PWA                    Tool calls │
       │  (touch + voice UI)                      │
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
2. Jenny asks for name + date of birth → backend runs **3-tier fuzzy matching**
3. Dashboard card appears with appointment, balance, upcoming visits
4. Patient can **check in** (voice or tap), **book new appointment**, or ask questions
5. New patients get registered with name, DOB, phone, insurance — all conversational
6. Session auto-ends after goodbye — kiosk returns to idle screen

---

## Features

### Patient-Facing
- **Conversational AI Avatar** — Tavus CVI replica with natural video, lip-sync, real-time voice
- **Hybrid Voice + Touch UI** — Patients can speak or tap (procedure cards, time slots, check-in button)
- **Patient Verification** — 3-tier fuzzy matching (exact SQL → SOUNDEX → difflib)
- **Check-In** — Records arrival time + creates/fills Exam Sheet in Open Dental (A: scheduled time, C: check-in time)
- **Appointment Booking** — Procedure picker → date/time slots → confirmation
- **New Patient Registration** — Collects name, DOB, phone, insurance conversationally
- **Patient Dashboard** — Real-time card with appointment, balance, upcoming visits
- **Multilingual** — English, Spanish, Russian (voice + UI)
- **Screen-Aware AI** — Avatar knows what's on screen via SYSTEM_NOTE injections

### Staff Panel (PIN-protected sidebar)
- **Patient Search** — Search by name + DOB, view details
- **Manual Check-In** — Override check-in for any patient (also creates/fills Exam Sheet)
- **Booking** — Search patient by name, book appointments
- **Waiting Queue** — Today's checked-in patients sorted by wait time
- **Patient Notes** — Add/view notes per patient (stored in kiosk_patient_notes table)

### Production Hardening
- **Error Boundary** — React crash recovery with restart button
- **WebRTC Reconnect** — Auto-rejoin on network blips (3 attempts)
- **Touch Target Enforcement** — All buttons minimum 48×48px for kiosk touchscreen
- **Tap Debouncing** — Prevents double-booking from rapid taps (800ms cooldown)
- **Tool Call Timeout** — 15s timeout with user-facing error if backend hangs
- **Session Persistence** — sessionStorage survives page refresh (10min expiry)
- **Inactivity Guard** — Nudge after 15s, auto-end after 30s (tracks speech + taps)
- **Goodbye Detection** — Auto-ends session 10s after farewell phrase
- **Session Hard Cap** — 5 min max on Tavus side + backend reaper for stale sessions
- **Speech Queue** — Tool results queued while avatar speaks, flushed after 1.5s silence
- **HIPAA Audit Logging** — Every tool call logged with timestamps

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
| **Tunnel** | Cloudflare Tunnel (for Tavus webhooks + remote access) |
| **Styling** | CSS glassmorphic dark theme |

---

## Project Structure

```
├── backend/
│   ├── main.py              # FastAPI app, routes, session management, staff endpoints
│   ├── tools.py             # Tool handlers (verify, check-in, balance, book, slots, create_patient)
│   ├── setup_persona.py     # Tavus persona creation (prompt, objectives, tools, STT config)
│   ├── tavus.py             # Tavus CVI API client
│   ├── db.py                # Async MySQL pool with background reconnect
│   ├── audit.py             # HIPAA compliance logging
│   ├── config.py            # Environment settings
│   ├── models.py            # Pydantic request/response schemas
│   └── requirements.txt
│
├── frontend/
│   ├── index.html               # PWA entry point
│   ├── public/
│   │   ├── manifest.json        # PWA manifest (fullscreen, dark theme)
│   │   ├── sw.js                # Service worker
│   │   ├── jenny-idle.mp4       # Idle video placeholder
│   │   └── clinic-logo.jpg
│   ├── src/
│   │   ├── App.jsx              # Root state machine + panel switching + inactivity guard
│   │   ├── main.jsx             # Entry point with ErrorBoundary wrapper
│   │   ├── index.css            # Glassmorphic dark theme + touch targets
│   │   ├── components/
│   │   │   ├── Avatar.jsx           # Video stream + idle placeholder with blur
│   │   │   ├── BookingFlow.jsx      # Hybrid voice+touch booking (slots, procedures, registration)
│   │   │   ├── PatientDashboard.jsx # Verified patient info card (auto-minimizes)
│   │   │   ├── ManualCheckin.jsx    # Staff sidebar (search, queue, notes, booking)
│   │   │   ├── ErrorBoundary.jsx    # React crash recovery screen
│   │   │   ├── IdleScreen.jsx       # Welcome screen + language selector
│   │   │   ├── Transcript.jsx       # Live speech captions (dynamic positioning)
│   │   │   ├── Controls.jsx         # End session (double-tap confirm)
│   │   │   ├── StatusDot.jsx        # Connection status indicator
│   │   │   └── ActivityBar.jsx      # Tool execution progress with enter/exit animation
│   │   └── hooks/
│   │       ├── useSession.js        # Backend session lifecycle + sessionStorage persistence
│   │       └── useTavusCall.js      # Daily.co + Tavus tool orchestration + reconnect
│   ├── package.json
│   └── vite.config.js
│
├── ecosystem.config.cjs     # PM2 process config
├── start.sh                 # One-command production start
├── stop.sh                  # Stop all services
└── README.md
```

---

## Deployment

### Prerequisites

- **Node.js** 18+
- **Python** 3.10+
- **MySQL** (Open Dental instance accessible on the network)
- **Tavus** API key + Replica ID — [tavus.io](https://www.tavus.io/)
- **Cloudflare Tunnel** (or ngrok) for Tavus webhook callbacks

### 1. Clone & install

```bash
git clone https://github.com/your-org/tavuskiosk.git
cd tavuskiosk

# PM2 (process manager)
npm install -g pm2

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
```

Edit `backend/.env`:

```env
# Tavus CVI
TAVUS_API_KEY=tvs_xxx
TAVUS_PERSONA_ID=p_xxx          # from setup_persona.py
TAVUS_REPLICA_ID=r_xxx          # from Tavus dashboard

# Open Dental MySQL
DB_HOST=10.0.0.83               # your Open Dental server IP
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=opendental

# Public URLs (Cloudflare tunnel)
BACKEND_URL=https://kiosk.your-domain.com
FRONTEND_URL=https://kiosk.your-domain.com

# Twilio (optional — SMS confirmations)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=

# Session limits
MAX_CALL_DURATION=300
PARTICIPANT_LEFT_TIMEOUT=30
```

### 3. Create AI persona (one-time)

```bash
cd backend
source venv/bin/activate
python3 setup_persona.py
# Copy the printed persona_id into .env → TAVUS_PERSONA_ID
```

### 4. Cloudflare Tunnel

The tunnel is needed so Tavus servers can reach your backend (webhook callbacks) and so the kiosk browser can reach the app from anywhere.

```bash
# Install cloudflared
# Ubuntu/WSL:
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared

# Create a named tunnel (one-time)
cloudflared tunnel login
cloudflared tunnel create kiosk

# Configure tunnel (create ~/.cloudflared/config.yml)
cat > ~/.cloudflared/config.yml << 'EOF'
tunnel: <YOUR_TUNNEL_ID>
credentials-file: /root/.cloudflared/<YOUR_TUNNEL_ID>.json

ingress:
  - hostname: kiosk.your-domain.com
    service: http://localhost:5173
  - hostname: kiosk-api.your-domain.com
    service: http://localhost:8000
  - service: http_status:404
EOF

# Or single domain with nginx reverse proxy (recommended)
```

### 5. Nginx reverse proxy (recommended for single domain)

```nginx
server {
    listen 80;
    server_name localhost;

    # Frontend (static files)
    location / {
        root /path/to/tavuskiosk/frontend/dist;
        try_files $uri $uri/ /index.html;
    }

    # Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /tools/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Then tunnel points to `http://localhost:80`.

### 6. Build & Launch

```bash
# Build frontend
cd frontend
npm run build
cd ..

# Start with PM2
pm2 start ecosystem.config.cjs
pm2 save
pm2 startup  # auto-start on reboot

# Start tunnel
cloudflared tunnel run kiosk
```

### 7. Kiosk browser

On the kiosk device (tablet/touchscreen), open Chrome in kiosk mode:

```bash
# Windows
chrome.exe --kiosk --disable-pinch --overscroll-history-navigation=0 https://kiosk.your-domain.com

# Linux
google-chrome --kiosk --disable-pinch --overscroll-history-navigation=0 https://kiosk.your-domain.com
```

Or install as PWA: open the URL → Chrome menu → "Install app".

---

## Development

```bash
# Backend (with hot reload)
cd backend
source venv/bin/activate
LOG_LEVEL=DEBUG uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Frontend (Vite dev server with proxy to backend)
cd frontend
npm run dev

# Tunnel for Tavus webhooks (dev)
cloudflared tunnel --url http://localhost:8000
# Update BACKEND_URL in .env with the tunnel URL
```

---

## Environment Variables

### `backend/.env`

| Variable | Required | Description |
|----------|----------|-------------|
| `TAVUS_API_KEY` | Yes | Tavus API key |
| `TAVUS_PERSONA_ID` | Yes | Persona ID from setup_persona.py |
| `TAVUS_REPLICA_ID` | Yes | Replica ID from Tavus dashboard |
| `DB_HOST` | Yes | Open Dental MySQL host |
| `DB_PORT` | No | MySQL port (default: 3306) |
| `DB_USER` | Yes | MySQL user |
| `DB_PASSWORD` | Yes | MySQL password |
| `DB_NAME` | Yes | Database name (default: opendental) |
| `BACKEND_URL` | Yes | Public URL for Tavus webhooks |
| `FRONTEND_URL` | Yes | Frontend URL for CORS |
| `TWILIO_ACCOUNT_SID` | No | Twilio SMS (optional) |
| `TWILIO_AUTH_TOKEN` | No | Twilio SMS (optional) |
| `TWILIO_FROM_NUMBER` | No | Twilio SMS (optional) |
| `MAX_CALL_DURATION` | No | Max session seconds (default: 300) |
| `PARTICIPANT_LEFT_TIMEOUT` | No | Tavus timeout after user leaves (default: 30) |

---

## API Endpoints

### Session

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/session/start` | Create Tavus conversation |
| POST | `/api/session/end` | End active conversation |

### Tool Endpoints (frontend-orchestrated)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/tools/verify_patient` | Identity verification (3-tier fuzzy matching) |
| POST | `/tools/get_today_appointment` | Today's appointment lookup |
| POST | `/tools/get_balance` | Account balance breakdown |
| POST | `/tools/get_appointments` | Upcoming appointments |
| POST | `/tools/check_in_patient` | Record patient arrival + create/fill Exam Sheet |
| POST | `/tools/find_available_slots` | Find open appointment slots |
| POST | `/tools/book_appointment` | Book a new appointment |
| POST | `/tools/create_patient` | Register new patient |

### Staff Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/manual/search` | Search patients by name + DOB |
| POST | `/api/manual/checkin` | Manual check-in + create/fill Exam Sheet |
| GET | `/api/staff/queue` | Today's waiting queue |
| POST | `/api/staff/notes` | Add patient note |
| POST | `/api/staff/notes/list` | Get patient notes |

### Exam Sheet Auto-Fill

On check-in (AI or staff), the system creates or fills an Open Dental Exam Sheet with appointment time (`A:`) and check-in time (`C:`).

**Two modes** controlled via browser console:

```js
examsheet()          // show current mode
examsheet("create")  // always create a new sheet (default)
examsheet("fill")    // find today's existing sheet with empty C: first, else create new
```

Or via API:
```bash
curl /api/config                                                          # GET current mode
curl -X POST /api/config -H "Content-Type: application/json" -d '{"exam_sheet_mode":"fill"}'  # change mode
```

All settings persist to `.env` — survive restarts.

### Auto-Print to Network Printer

On every check-in, the exam sheet is automatically printed to a network printer via IPP.

```js
printer()                // show current printer IP
printer("10.0.0.127")   // set printer IP
printer("off")           // disable printing
```

The system generates a PDF matching the Open Dental exam sheet layout (A:/C: times, patient name, tooth charts, PT NEEDS, RX, DR/DA/DH fields) and sends it directly to the printer. Staff fills in remaining fields by hand.

Requires a network printer with IPP support (port 631) — most modern network printers support this.

### Audio & Noise Isolation

The kiosk uses a **Jabra Speak 410** USB speakerphone (4-mic array + speaker with hardware noise isolation) for lobby environments.

**Software-side audio stack:**
- **Daily.co Krisp noise cancellation** — AI-powered noise filtering before audio reaches Tavus STT
- **Jabra auto-detection** — on call join, the system finds and selects the Jabra device (mic + speaker) by name; falls back to system default if unplugged
- **WebRTC constraints** — `echoCancellation`, `noiseSuppression`, `autoGainControl` explicitly enabled
- **Fast turn-taking** — `participant_pause_sensitivity: "high"` for immediate responses; `participant_interrupt_sensitivity: "low"` to ignore background noise

Console logs to verify:
```
[Audio] Jabra mic selected: Jabra SPEAK 410 USB
[Audio] Jabra speaker selected: Jabra SPEAK 410 USB
```

If Jabra is not connected:
```
[Audio] Jabra not found, using system default
```

---

## Architecture Notes

### Tool Call Flow

Tavus webhooks are one-way — results must be injected back. The frontend orchestrates:

```
Avatar decides to call tool → Tavus event → Daily.co app-message → Frontend
→ Frontend calls Backend REST → gets result → formats text
→ Frontend injects via conversation.respond → Tavus LLM → Avatar speaks
```

Tool results are queued if the avatar is still speaking, then flushed 1.5s after she stops (prevents self-interruption).

### Panel Switching

Only one main panel visible at a time:
- **PatientDashboard** auto-minimizes to a pill when BookingFlow is active
- **BookingFlow** shows contextual cards: procedure picker → time slots → confirmation
- **Transcript** dynamically repositions above whichever panel is visible (MutationObserver)

### Session Protection

| Layer | Mechanism | Timing |
|-------|-----------|--------|
| Frontend | Inactivity nudge | 15s silence (speech + taps) |
| Frontend | Auto-end call | 30s silence |
| Frontend | Goodbye detection | 10s after farewell phrase |
| Frontend | Tool timeout | 15s per tool call |
| Tavus | `max_call_duration` | 5 min |
| Tavus | `participant_left_timeout` | 30s |
| Backend | Stale session reaper | Every 60s |

### Fuzzy Name Matching

| Tier | Method | Example |
|------|--------|---------|
| 1 | Exact SQL match + DOB | "Ramirez" → "Ramirez" |
| 2 | SOUNDEX phonetic + DOB | "Ramiris" → "Ramirez" |
| 3 | difflib ratio > 0.6 + DOB | "Ramires" → "Ramirez" |

If multiple matches are found, asks for last 4 digits of phone to disambiguate.

---

## License

MIT
