"""FastAPI application for the dental kiosk backend.

Endpoints:
- POST /api/session/start — Create a Tavus conversation
- POST /api/session/end — End a Tavus conversation
- POST /tools/{tool_name} — Tavus tool webhooks
- POST /api/manual/search — Staff sidebar patient search
- POST /api/manual/checkin — Staff sidebar check-in
- GET /health — Healthcheck
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings
from db import init_pool, close_pool, execute_query, execute_insert, execute_ddl
from tavus import init_client, close_client, create_conversation, end_conversation
from models import (
    SessionStartRequest,
    SessionStartResponse,
    SessionEndRequest,
    ManualSearchRequest,
    CheckinRequest,
    StaffBalanceRequest,
    StaffAppointmentsRequest,
    StaffSlotsRequest,
    StaffBookRequest,
    StaffRegisterRequest,
    StaffNoteRequest,
    StaffNotesQuery,
)
from tools import (
    verify_patient,
    get_balance,
    get_appointments,
    get_today_appointment,
    check_in_patient,
    find_available_slots,
    create_patient,
    book_appointment,
    send_sms_reminder,
    search_patient_today,
    checkin_appointment,
)
from audit import log_tool_call

# --- Logging: console + file ---
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
_log_format = "%(asctime)s %(name)s %(levelname)s %(message)s"
logging.basicConfig(level=_log_level, format=_log_format)

_file_handler = logging.FileHandler(os.path.join(LOG_DIR, "server.log"), encoding="utf-8")
_file_handler.setLevel(_log_level)
_file_handler.setFormatter(logging.Formatter(_log_format))
logging.getLogger().addHandler(_file_handler)

_webhook_handler = logging.FileHandler(os.path.join(LOG_DIR, "webhooks.log"), encoding="utf-8")
_webhook_handler.setLevel(_log_level)
_webhook_handler.setFormatter(logging.Formatter(_log_format))
webhook_logger = logging.getLogger("webhooks")
webhook_logger.addHandler(_webhook_handler)
webhook_logger.setLevel(_log_level)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Session state (in-memory, single kiosk)
# ---------------------------------------------------------------------------
active_sessions: dict[str, dict] = {}  # conversation_id → {patient_id, start_time, ...}


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

async def _cleanup_orphaned_sessions():
    """On startup, kill any active conversations in Tavus from previous runs."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://tavusapi.com/v2/conversations",
                params={"limit": 50, "status": "active"},
                headers={"x-api-key": settings.tavus_api_key},
            )
            if resp.status_code != 200:
                logger.warning("Could not fetch active conversations for cleanup: %s", resp.status_code)
                return
            data = resp.json()
            convs = data if isinstance(data, list) else data.get("data", data.get("conversations", []))
            if convs:
                logger.warning("Found %d orphaned active session(s) on startup, killing them", len(convs))
                for c in convs:
                    cid = c.get("conversation_id", "")
                    try:
                        await end_conversation(cid)
                        logger.info("Killed orphaned session: %s", cid)
                    except Exception as e:
                        logger.warning("Failed to kill orphaned session %s: %s", cid, e)
            else:
                logger.info("No orphaned sessions found on startup")
    except Exception as e:
        logger.warning("Startup session cleanup failed: %s", e)


async def _reap_stale_sessions():
    """Kill sessions older than max_call_duration + buffer. Runs every 60s."""
    max_age = settings.max_call_duration + 30  # reap shortly after Tavus hard cap
    while True:
        await asyncio.sleep(60)
        now = datetime.utcnow()
        stale = []
        for cid, info in list(active_sessions.items()):
            started = datetime.fromisoformat(info["start_time"])
            if (now - started).total_seconds() > max_age:
                stale.append(cid)
        for cid in stale:
            logger.warning("Reaping stale session: %s", cid)
            try:
                await end_conversation(cid)
            except Exception as e:
                logger.error("Failed to reap session %s: %s", cid, e)
            active_sessions.pop(cid, None)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle."""
    logger.info("Starting dental kiosk backend...")
    try:
        await init_pool()
        logger.info("MySQL connection pool ready.")
    except Exception as e:
        logger.warning("MySQL not available: %s — running without DB (tool calls will fail)", e)
    init_client()
    await _cleanup_orphaned_sessions()
    reaper = asyncio.create_task(_reap_stale_sessions())
    logger.info("Backend ready.")
    yield
    reaper.cancel()
    logger.info("Shutting down...")
    await close_pool()
    await close_client()
    logger.info("Shutdown complete.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Dental Kiosk AI",
    version="1.0.0",
    lifespan=lifespan,
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled errors in tool endpoints — return clean JSON, never 500 HTML."""
    if request.url.path.startswith("/tools/"):
        logger.error("Tool endpoint error [%s]: %s", request.url.path, exc)
        return JSONResponse(
            status_code=200,  # 200 so frontend doesn't treat it as HTTP error
            content={"result": {"status": "error", "message": "Something went wrong. Please see the front desk."}},
        )
    # Re-raise for non-tool endpoints
    raise exc


_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", settings.frontend_url).split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

@app.post("/api/session/start", response_model=SessionStartResponse)
async def session_start(req: Optional[SessionStartRequest] = None):
    """Create a new Tavus conversation for this kiosk session.

    Safety: kills any existing active sessions first (kiosk = single session).
    """
    language = req.language if req else "en"

    # Kill ALL existing tracked sessions before creating a new one
    if active_sessions:
        stale_ids = list(active_sessions.keys())
        logger.warning("Cleaning %d existing session(s) before starting new one: %s", len(stale_ids), stale_ids)
        for cid in stale_ids:
            try:
                await end_conversation(cid)
            except Exception as e:
                logger.warning("Failed to end stale session %s: %s", cid, e)
            active_sessions.pop(cid, None)

    try:
        result = await create_conversation(language=language)
        conversation_id = result["conversation_id"]
        conversation_url = result["conversation_url"]

        # Track session
        active_sessions[conversation_id] = {
            "start_time": datetime.utcnow().isoformat(),
            "patient_id": None,
            "language": language,
        }

        logger.info("Session started: %s", conversation_id)

        return SessionStartResponse(
            conversation_id=conversation_id,
            conversation_url=conversation_url,
        )

    except Exception as e:
        logger.error("Failed to start session: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to create conversation: {e}")


@app.post("/api/session/end")
async def session_end(req: SessionEndRequest):
    """End an active Tavus conversation."""
    try:
        await end_conversation(req.conversation_id)
        active_sessions.pop(req.conversation_id, None)
        logger.info("Session ended: %s", req.conversation_id)
        return {"status": "ok"}
    except Exception as e:
        logger.error("Failed to end session: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to end conversation: {e}")


# ---------------------------------------------------------------------------
# Tool webhooks (called by Tavus)
# ---------------------------------------------------------------------------

@app.post("/tools/verify_patient")
async def tool_verify_patient(request: Request):
    """Tavus webhook: verify patient identity by name + DOB."""
    body = await request.json()
    webhook_logger.info("=== VERIFY_PATIENT webhook ===")
    webhook_logger.info("Raw body: %s", json.dumps(body, indent=2, default=str))

    conversation_id = body.get("conversation_id", "")
    props = body.get("properties", body.get("parameters", {}))
    webhook_logger.info("Extracted props: %s", json.dumps(props, default=str))

    name = props.get("name", "")
    dob = props.get("dob", "")
    phone_last4 = props.get("phone_last4", "")
    webhook_logger.info("name=%r, dob=%r, phone_last4=%r", name, dob, phone_last4)

    if not name or not dob:
        webhook_logger.warning("Missing name or DOB!")
        return {"result": {"verified": False, "message": "Name and date of birth are required."}}

    result = await verify_patient(conversation_id, name, dob, phone_last4=phone_last4)
    webhook_logger.info("Result: %s", json.dumps(result, default=str))

    # Update session state if verified
    if result.get("verified") and conversation_id in active_sessions:
        active_sessions[conversation_id]["patient_id"] = result.get("patient_id")

    return {"result": result}


@app.post("/tools/get_today_appointment")
async def tool_get_today_appointment(request: Request):
    """Tavus webhook: get patient's appointment for today."""
    body = await request.json()
    webhook_logger.info("=== GET_TODAY_APPOINTMENT webhook === Body: %s", json.dumps(body, indent=2, default=str))
    conversation_id = body.get("conversation_id", "")
    props = body.get("properties", body.get("parameters", {}))

    patient_id = props.get("patient_id")
    if not patient_id:
        return {"result": {"status": "error", "message": "Patient ID is required."}}

    result = await get_today_appointment(conversation_id, int(patient_id))
    webhook_logger.info("GET_TODAY_APPOINTMENT result: %s", json.dumps(result, default=str))
    return {"result": result}


@app.post("/tools/check_in_patient")
async def tool_check_in_patient(request: Request):
    """Tavus webhook: check in patient for their appointment."""
    body = await request.json()
    webhook_logger.info("=== CHECK_IN_PATIENT webhook === Body: %s", json.dumps(body, indent=2, default=str))
    conversation_id = body.get("conversation_id", "")
    props = body.get("properties", body.get("parameters", {}))

    appointment_id = props.get("appointment_id")
    if not appointment_id:
        return {"result": {"status": "error", "message": "Appointment ID is required."}}

    result = await check_in_patient(conversation_id, int(appointment_id))
    webhook_logger.info("CHECK_IN_PATIENT result: %s", json.dumps(result, default=str))
    return {"result": result}


@app.post("/tools/get_balance")
async def tool_get_balance(request: Request):
    """Tavus webhook: get patient account balance."""
    body = await request.json()
    webhook_logger.info("=== GET_BALANCE webhook === Body: %s", json.dumps(body, indent=2, default=str))
    conversation_id = body.get("conversation_id", "")
    props = body.get("properties", body.get("parameters", {}))

    patient_id = props.get("patient_id")
    if not patient_id:
        return {"result": {"status": "error", "message": "Patient ID is required."}}

    result = await get_balance(conversation_id, int(patient_id))
    webhook_logger.info("GET_BALANCE result: %s", json.dumps(result, default=str))
    return {"result": result}


@app.post("/tools/get_appointments")
async def tool_get_appointments(request: Request):
    """Tavus webhook: get upcoming appointments."""
    body = await request.json()
    webhook_logger.info("=== GET_APPOINTMENTS webhook === Body: %s", json.dumps(body, indent=2, default=str))
    conversation_id = body.get("conversation_id", "")
    props = body.get("properties", body.get("parameters", {}))

    patient_id = props.get("patient_id")
    if not patient_id:
        return {"result": {"status": "error", "message": "Patient ID is required."}}

    result = await get_appointments(conversation_id, int(patient_id))
    webhook_logger.info("GET_APPOINTMENTS result: %s", json.dumps(result, default=str))
    return {"result": result}


@app.post("/tools/find_available_slots")
async def tool_find_available_slots(request: Request):
    """Tavus webhook: find available appointment slots on a date."""
    body = await request.json()
    webhook_logger.info("=== FIND_AVAILABLE_SLOTS webhook === Body: %s", json.dumps(body, indent=2, default=str))
    conversation_id = body.get("conversation_id", "")
    props = body.get("properties", body.get("parameters", {}))

    date_str = props.get("date", "")
    procedure_type = props.get("procedure_type", "")

    if not date_str:
        return {"result": {"status": "error", "message": "Date is required."}}

    try:
        result = await find_available_slots(conversation_id, date_str, procedure_type)
    except Exception as e:
        logger.error("find_available_slots error: %s", e)
        result = {"status": "error", "message": "Could not check available slots. Please see the front desk."}

    webhook_logger.info("FIND_AVAILABLE_SLOTS result: %s", json.dumps(result, default=str))
    return {"result": result}


@app.post("/tools/create_patient")
async def tool_create_patient(request: Request):
    """Tavus webhook: create a new patient record."""
    body = await request.json()
    webhook_logger.info("=== CREATE_PATIENT webhook === Body: %s", json.dumps(body, indent=2, default=str))
    conversation_id = body.get("conversation_id", "")
    props = body.get("properties", body.get("parameters", {}))

    first_name = props.get("first_name", "")
    last_name = props.get("last_name", "")
    dob = props.get("dob", "")
    phone = props.get("phone", "")
    insurance = props.get("insurance", "")

    if not first_name or not last_name or not dob:
        return {"result": {"status": "error", "message": "First name, last name, and date of birth are required."}}

    try:
        result = await create_patient(conversation_id, first_name, last_name, dob, phone, insurance)
    except Exception as e:
        logger.error("create_patient error: %s", e)
        result = {"status": "error", "message": "Could not create patient record. Please see the front desk."}

    webhook_logger.info("CREATE_PATIENT result: %s", json.dumps(result, default=str))
    return {"result": result}


@app.post("/tools/book_appointment")
async def tool_book_appointment(request: Request):
    """Tavus webhook: book an appointment in Open Dental."""
    body = await request.json()
    webhook_logger.info("=== BOOK_APPOINTMENT webhook === Body: %s", json.dumps(body, indent=2, default=str))
    conversation_id = body.get("conversation_id", "")
    props = body.get("properties", body.get("parameters", {}))

    patient_id = props.get("patient_id")
    date_str = props.get("date", "")
    time_str = props.get("time", "")
    procedure_type = props.get("procedure_type", "")
    insurance_info = props.get("insurance_info", "")
    is_new_patient = props.get("is_new_patient", False)

    if not patient_id or not date_str or not time_str:
        return {"result": {"status": "error", "message": "Patient ID, date, and time are required."}}

    try:
        result = await book_appointment(
            conversation_id, int(patient_id), date_str, time_str,
            procedure_type, insurance_info, bool(is_new_patient),
        )
    except Exception as e:
        logger.error("book_appointment error: %s", e)
        result = {"status": "error", "message": "Could not book the appointment. Please see the front desk."}

    webhook_logger.info("BOOK_APPOINTMENT result: %s", json.dumps(result, default=str))
    return {"result": result}


@app.post("/tools/send_sms_reminder")
async def tool_send_sms_reminder(request: Request):
    """Tavus webhook: send SMS appointment reminder."""
    body = await request.json()
    webhook_logger.info("=== SEND_SMS_REMINDER webhook === Body: %s", json.dumps(body, indent=2, default=str))
    conversation_id = body.get("conversation_id", "")
    props = body.get("properties", body.get("parameters", {}))

    patient_id = props.get("patient_id")
    appointment_id = props.get("appointment_id")

    if not patient_id:
        return {"result": {"status": "error", "message": "Patient ID is required."}}

    result = await send_sms_reminder(conversation_id, int(patient_id), int(appointment_id) if appointment_id else None)
    webhook_logger.info("SEND_SMS_REMINDER result: %s", json.dumps(result, default=str))
    return {"result": result}


# ---------------------------------------------------------------------------
# Debug / Log viewer endpoints
# ---------------------------------------------------------------------------

@app.get("/api/logs/webhooks")
async def get_webhook_logs(lines: int = 100):
    """View last N lines of webhook logs."""
    log_path = os.path.join(LOG_DIR, "webhooks.log")
    if not os.path.exists(log_path):
        return {"logs": [], "message": "No webhook logs yet."}
    with open(log_path, "r", encoding="utf-8") as f:
        all_lines = f.readlines()
    return {"logs": all_lines[-lines:], "count": len(all_lines)}


@app.get("/api/logs/server")
async def get_server_logs(lines: int = 100):
    """View last N lines of server logs."""
    log_path = os.path.join(LOG_DIR, "server.log")
    if not os.path.exists(log_path):
        return {"logs": [], "message": "No server logs yet."}
    with open(log_path, "r", encoding="utf-8") as f:
        all_lines = f.readlines()
    return {"logs": all_lines[-lines:], "count": len(all_lines)}


@app.post("/tools/{tool_name_catch}")
async def tool_catch_all(tool_name_catch: str, request: Request):
    """Catch-all for unrecognized tool webhooks — logs for debugging."""
    body = await request.json()
    webhook_logger.warning("=== UNKNOWN TOOL: %s === Body: %s", tool_name_catch, json.dumps(body, indent=2, default=str))
    return {"result": {"status": "error", "message": f"Unknown tool: {tool_name_catch}"}}


# ---------------------------------------------------------------------------
# Manual check-in endpoints (staff sidebar)
# ---------------------------------------------------------------------------

@app.post("/api/manual/search")
async def manual_search(req: ManualSearchRequest):
    """Staff sidebar: search today's appointments by last name and/or DOB."""
    result = await search_patient_today(req.last_name, req.dob)
    return result


@app.post("/api/manual/checkin")
async def manual_checkin(req: CheckinRequest):
    """Staff sidebar: mark appointment as arrived."""
    result = await checkin_appointment(req.appointment_id)
    return result


# ---------------------------------------------------------------------------
# Staff panel — full manual mode (same operations as voice, REST API)
# ---------------------------------------------------------------------------

STAFF_CID = "staff_manual"


@app.post("/api/staff/balance")
async def staff_balance(req: StaffBalanceRequest):
    """Staff panel: get patient balance."""
    result = await get_balance(STAFF_CID, req.patient_id)
    return {"result": result}


@app.post("/api/staff/appointments")
async def staff_appointments(req: StaffAppointmentsRequest):
    """Staff panel: get upcoming appointments."""
    result = await get_appointments(STAFF_CID, req.patient_id)
    return {"result": result}


@app.post("/api/staff/slots")
async def staff_slots(req: StaffSlotsRequest):
    """Staff panel: find available time slots."""
    result = await find_available_slots(STAFF_CID, req.date, req.procedure_type or "")
    return {"result": result}


@app.post("/api/staff/book")
async def staff_book(req: StaffBookRequest):
    """Staff panel: book an appointment."""
    result = await book_appointment(
        STAFF_CID, req.patient_id, req.date, req.time,
        req.procedure_type or "routine_exam_cleaning", "", False,
    )
    return {"result": result}


@app.post("/api/staff/register")
async def staff_register(req: StaffRegisterRequest):
    """Staff panel: register new patient."""
    result = await create_patient(
        STAFF_CID, req.first_name, req.last_name, req.dob,
        req.phone or "", req.insurance or "",
    )
    return {"result": result}


@app.get("/api/staff/sessions")
async def staff_sessions():
    """Staff panel: list active sessions."""
    sessions = []
    for cid, info in active_sessions.items():
        sessions.append({
            "conversation_id": cid,
            "start_time": info.get("start_time"),
            "patient_id": info.get("patient_id"),
            "language": info.get("language", "en"),
        })
    return {"sessions": sessions}


@app.post("/api/staff/sessions/end-all")
async def staff_end_all_sessions():
    """Staff panel: end all active sessions."""
    ended = []
    for cid in list(active_sessions.keys()):
        try:
            await end_conversation(cid)
            active_sessions.pop(cid, None)
            ended.append(cid)
            logger.info("Staff ended session: %s", cid)
        except Exception as e:
            logger.error("Failed to end session %s: %s", cid, e)
    return {"status": "ok", "ended": ended, "count": len(ended)}


# ---------------------------------------------------------------------------
# Patient Notes
# ---------------------------------------------------------------------------

_NOTES_TABLE_CREATED = False


async def _ensure_notes_table():
    """Create kiosk_patient_notes table if it doesn't exist."""
    global _NOTES_TABLE_CREATED
    if _NOTES_TABLE_CREATED:
        return
    try:
        await execute_ddl("""
            CREATE TABLE IF NOT EXISTS kiosk_patient_notes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                patient_id INT NOT NULL,
                staff_pin VARCHAR(10) DEFAULT 'staff',
                text TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_patient (patient_id)
            )
        """)
        _NOTES_TABLE_CREATED = True
    except Exception as e:
        logger.warning("Failed to create notes table: %s", e)


@app.post("/api/staff/notes")
async def staff_add_note(req: StaffNoteRequest):
    """Staff panel: add a note to a patient."""
    await _ensure_notes_table()
    note_id = await execute_insert(
        "INSERT INTO kiosk_patient_notes (patient_id, text) VALUES (%s, %s)",
        (req.patient_id, req.text),
    )
    await log_tool_call(STAFF_CID, "add_note", req.patient_id, "note_added", req.text[:100])
    return {"status": "ok", "note_id": note_id}


@app.post("/api/staff/notes/list")
async def staff_get_notes(req: StaffNotesQuery):
    """Staff panel: get notes for a patient."""
    await _ensure_notes_table()
    rows = await execute_query(
        "SELECT id, text, created_at FROM kiosk_patient_notes WHERE patient_id = %s ORDER BY created_at DESC LIMIT 50",
        (req.patient_id,),
    )
    notes = []
    for r in rows:
        notes.append({
            "id": r["id"],
            "text": r["text"],
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        })
    return {"notes": notes}


# ---------------------------------------------------------------------------
# Waiting Queue — checked-in patients awaiting their appointment
# ---------------------------------------------------------------------------

@app.get("/api/staff/queue")
async def staff_queue():
    """Staff panel: today's appointments not yet checked in, ordered by time."""
    rows = await execute_query("""
        SELECT
            a.AptNum, a.PatNum, a.AptDateTime, a.DateTimeArrived,
            a.ProcDescript, a.Confirmed,
            p.FName, p.LName,
            pv.Abbr AS provider
        FROM appointment a
        JOIN patient p ON p.PatNum = a.PatNum
        LEFT JOIN provider pv ON pv.ProvNum = a.ProvNum
        WHERE DATE(a.AptDateTime) = CURDATE()
          AND a.AptStatus = 1
          AND (a.DateTimeArrived <= '0001-01-01' OR TIME(a.DateTimeArrived) = '00:00:00')
        ORDER BY a.AptDateTime ASC
    """)
    queue = []
    for r in rows:
        apt_time = r.get("AptDateTime")
        queue.append({
            "apt_num": r["AptNum"],
            "pat_num": r["PatNum"],
            "name": f"{r['FName']} {r['LName']}",
            "appointment_time": apt_time.strftime("%I:%M %p").lstrip("0") if apt_time else "",
            "procedure": r.get("ProcDescript") or "General",
            "provider": r.get("provider") or "",
        })
    return {"queue": queue, "count": len(queue)}
