"""FastAPI application for the dental kiosk backend.

Endpoints:
- POST /api/session/start — Create a Tavus conversation
- POST /api/session/end — End a Tavus conversation
- POST /tools/{tool_name} — Tavus tool webhooks
- POST /api/manual/search — Staff sidebar patient search
- POST /api/manual/checkin — Staff sidebar check-in
- GET /health — Healthcheck
"""

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from db import init_pool, close_pool
from tavus import init_client, close_client, create_conversation, end_conversation
from models import (
    SessionStartRequest,
    SessionStartResponse,
    SessionEndRequest,
    ManualSearchRequest,
    CheckinRequest,
)
from tools import (
    verify_patient,
    get_balance,
    get_appointments,
    get_today_appointment,
    check_in_patient,
    book_appointment,
    send_sms_reminder,
    search_patient_today,
    checkin_appointment,
)
from audit import log_tool_call

# --- Logging: console + file ---
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

_log_format = "%(asctime)s %(name)s %(levelname)s %(message)s"
logging.basicConfig(level=logging.DEBUG, format=_log_format)

# File handler — always appends, DEBUG level for full detail
_file_handler = logging.FileHandler(os.path.join(LOG_DIR, "server.log"), encoding="utf-8")
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter(_log_format))
logging.getLogger().addHandler(_file_handler)

# Separate webhook log for easy debugging
_webhook_handler = logging.FileHandler(os.path.join(LOG_DIR, "webhooks.log"), encoding="utf-8")
_webhook_handler.setLevel(logging.DEBUG)
_webhook_handler.setFormatter(logging.Formatter(_log_format))
webhook_logger = logging.getLogger("webhooks")
webhook_logger.addHandler(_webhook_handler)
webhook_logger.setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Session state (in-memory, single kiosk)
# ---------------------------------------------------------------------------
active_sessions: dict[str, dict] = {}  # conversation_id → {patient_id, start_time, ...}


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

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
    logger.info("Backend ready.")
    yield
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:5173", "http://localhost:3000"],
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
    """Create a new Tavus conversation for this kiosk session."""
    language = req.language if req else "en"
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


@app.post("/tools/book_appointment")
async def tool_book_appointment(request: Request):
    """Tavus webhook: submit appointment booking request."""
    body = await request.json()
    webhook_logger.info("=== BOOK_APPOINTMENT webhook === Body: %s", json.dumps(body, indent=2, default=str))
    conversation_id = body.get("conversation_id", "")
    props = body.get("properties", body.get("parameters", {}))

    patient_id = props.get("patient_id")
    date_str = props.get("date", "")
    time_str = props.get("time", "")
    procedure = props.get("procedure", "")

    if not patient_id or not date_str or not time_str:
        return {"result": {"status": "error", "message": "Patient ID, date, and time are required."}}

    result = await book_appointment(conversation_id, int(patient_id), date_str, time_str, procedure)
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
