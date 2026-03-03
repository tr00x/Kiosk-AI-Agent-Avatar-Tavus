"""Tool webhook handlers for the dental kiosk.

Each function handles a Tavus tool call webhook:
1. verify_patient — Identity verification via name + DOB
2. get_balance — Patient account balance
3. get_appointments — Upcoming appointments list
4. book_appointment — Submit appointment request
5. send_sms_reminder — Send SMS reminder via Twilio

All functions query the Open Dental MySQL database via db.py and
log every action to the audit table for HIPAA compliance.
"""

import logging
import re
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Optional

from db import execute_query, execute_insert, execute_update, execute_ddl
from audit import log_tool_call
from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Procedure code → plain-English mapping (from Open Dental)
# ---------------------------------------------------------------------------
_PROC_MAP = [
    ("ImpCrPrep",   "Implant Crown Prep"),
    ("ImpCr",       "Implant Crown"),
    ("PFMSeat",     "Crown Placement"),
    ("PFMPrep",     "Crown Preparation"),
    ("PFM",         "Crown"),
    ("SRPMaxSext",  "Deep Cleaning"),
    ("SRPMandSext", "Deep Cleaning"),
    ("SRP",         "Deep Cleaning"),
    ("RCT",         "Root Canal"),
    ("Perio",       "Gum Treatment"),
    ("BWX",         "X-Rays"),
    ("FMX",         "Full X-Rays"),
    ("PA",          "X-Ray"),
    ("CompF",       "Filling"),
    ("CompA",       "Filling"),
    ("Comp",        "Filling"),
    ("Ext",         "Extraction"),
    ("Pre-fab",     "Post Placement"),
    ("Core",        "Build-Up"),
    ("Seat",        "Crown Seating"),
    ("Post",        "Post Placement"),
    ("Pro",         "Cleaning"),
    ("Ex",          "Exam"),
    ("Bl",          "Whitening"),
    ("Ven",         "Veneer"),
]


def _simplify_proc(raw: str) -> str:
    """Map Open Dental ProcDescript to human-readable label."""
    if not raw:
        return "Dental Visit"
    seen: set[str] = set()
    labels: list[str] = []
    for part in [p.strip().lstrip("#") for p in raw.split(",")]:
        code = part.split("-", 1)[-1] if "-" in part else part
        mapped = next((v for k, v in _PROC_MAP if k.lower() in code.lower()), None)
        label = mapped or "Dental Visit"
        if label not in seen:
            seen.add(label)
            labels.append(label)
    return ", ".join(labels) or "Dental Visit"


# ---------------------------------------------------------------------------
# Date parsing helpers
# ---------------------------------------------------------------------------

def _parse_dob(dob_str: str) -> str:
    """Parse various DOB formats into 'YYYY-MM-DD'.

    Handles: "March 15 1985", "03/15/1985", "1985-03-15", "3-15-1985", etc.
    """
    s = dob_str.strip()

    # Already ISO format
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s

    # MM/DD/YYYY or MM-DD-YYYY
    m = re.match(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$", s)
    if m:
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}"

    # Try natural language: "March 15 1985", "15 March 1985", etc.
    try:
        from dateutil.parser import parse as dateutil_parse
        dt = dateutil_parse(s)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass

    raise ValueError(f"Cannot parse date: {dob_str}")


def _extract_last_name(full_name: str) -> str:
    """Extract the last name from a full name string."""
    parts = full_name.strip().split()
    if len(parts) >= 2:
        return parts[-1]
    return parts[0] if parts else full_name


def _extract_digits(phone: str) -> str:
    """Extract only digits from a phone number string."""
    return re.sub(r"\D", "", phone)


def _fuzzy_name_score(a: str, b: str) -> float:
    """Fuzzy string similarity (0.0–1.0) using SequenceMatcher."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# ---------------------------------------------------------------------------
# Provider name helper
# ---------------------------------------------------------------------------
_NON_PERSON = {"PC", "LLC", "INC", "GROUP", "DENTAL", "ASSOCIATES", "CARE"}


def _format_provider(row: dict) -> str:
    """Format provider name from query result."""
    name = (row.get("provider_name") or "").strip()
    abbr = (row.get("provider_abbr") or "").strip()
    if name:
        parts = name.split()
        if not any(tok in (p.upper() for p in parts) for tok in _NON_PERSON):
            return f"Dr. {name}"
    if abbr:
        if abbr.lower().startswith("dr"):
            return abbr
        return f"Dr. {abbr}"
    return "our dental team"


# ---------------------------------------------------------------------------
# Tool functions (called from webhook endpoints in main.py)
# ---------------------------------------------------------------------------

async def verify_patient(conversation_id: str, name: str, dob: str, phone_last4: str = "") -> dict:
    """Verify patient by last name + DOB against Open Dental.

    Uses 3-tier matching:
      Tier 1: Exact last name + DOB
      Tier 2: SOUNDEX(last name) + DOB  (phonetic / sounds-like)
      Tier 3: DOB only → fuzzy Python match (ratio > 0.6)

    If multiple matches found with different phones, requires phone_last4 for disambiguation.
    """
    last_name = _extract_last_name(name)

    try:
        dob_iso = _parse_dob(dob)
    except ValueError:
        await log_tool_call(conversation_id, "verify_patient", None, "parse_dob_failed", f"dob={dob}")
        return {"verified": False, "reason": "invalid_dob", "message": f"Could not understand the date: {dob}. Please try again."}

    match_method = "exact"

    # --- Tier 1: Exact last name match ---
    rows = await execute_query(
        """
        SELECT
            p.PatNum,
            CONCAT(p.FName, ' ', p.LName) AS full_name,
            p.FName, p.LName, p.Birthdate,
            p.WirelessPhone, p.HmPhone
        FROM patient p
        WHERE LOWER(p.LName) = LOWER(%s)
          AND DATE(p.Birthdate) = %s
          AND p.PatStatus = 0
        ORDER BY p.PatNum ASC
        LIMIT 5
        """,
        (last_name, dob_iso),
    )

    # --- Tier 2: SOUNDEX match (if Tier 1 found nothing) ---
    if not rows:
        match_method = "soundex"
        rows = await execute_query(
            """
            SELECT
                p.PatNum,
                CONCAT(p.FName, ' ', p.LName) AS full_name,
                p.FName, p.LName, p.Birthdate,
                p.WirelessPhone, p.HmPhone
            FROM patient p
            WHERE SOUNDEX(p.LName) = SOUNDEX(%s)
              AND DATE(p.Birthdate) = %s
              AND p.PatStatus = 0
            ORDER BY p.PatNum ASC
            LIMIT 10
            """,
            (last_name, dob_iso),
        )

    # --- Tier 3: DOB only → fuzzy Python match (if Tier 2 found nothing) ---
    if not rows:
        match_method = "fuzzy"
        dob_rows = await execute_query(
            """
            SELECT
                p.PatNum,
                CONCAT(p.FName, ' ', p.LName) AS full_name,
                p.FName, p.LName, p.Birthdate,
                p.WirelessPhone, p.HmPhone
            FROM patient p
            WHERE DATE(p.Birthdate) = %s
              AND p.PatStatus = 0
            ORDER BY p.PatNum ASC
            LIMIT 50
            """,
            (dob_iso,),
        )
        # Filter by fuzzy name similarity > 0.6
        rows = [
            r for r in dob_rows
            if _fuzzy_name_score(last_name, r.get("LName", "")) > 0.6
        ]
        # Sort by best match
        rows.sort(key=lambda r: _fuzzy_name_score(last_name, r.get("LName", "")), reverse=True)

    # --- Resolve match ---
    patient = None

    if len(rows) == 1:
        patient = rows[0]
    elif len(rows) > 1:
        # Multiple matches — check if true duplicate (same phone) or different people
        phones = set()
        for r in rows:
            phone = _extract_digits(r.get("WirelessPhone") or r.get("HmPhone") or "")
            if phone:
                phones.add(phone[-4:])  # last 4 digits

        if len(phones) <= 1:
            # Same person, multiple records (new case in Open Dental).
            # Pick the one with the NEAREST upcoming appointment.
            best = rows[0]
            best_date = None
            for r in rows:
                nearest = await execute_query(
                    "SELECT MIN(AptDateTime) AS next_apt FROM appointment "
                    "WHERE PatNum = %s AND AptStatus = 1 AND AptDateTime >= CURDATE()",
                    (r["PatNum"],),
                )
                if nearest and nearest[0].get("next_apt"):
                    apt_date = nearest[0]["next_apt"]
                    if best_date is None or apt_date < best_date:
                        best_date = apt_date
                        best = r
            patient = best
            await log_tool_call(conversation_id, "verify_patient", None, "duplicate_resolved",
                                f"last_name={last_name}, picked PatNum={best['PatNum']} from {len(rows)} dupes")
        elif phone_last4:
            # Caller provided phone digits — try to disambiguate
            for r in rows:
                phone = _extract_digits(r.get("WirelessPhone") or r.get("HmPhone") or "")
                if phone and phone[-4:] == phone_last4:
                    patient = r
                    break
            if not patient:
                await log_tool_call(conversation_id, "verify_patient", None, "phone_mismatch",
                                    f"last_name={last_name}, phone_last4={phone_last4}")
                return {
                    "verified": False,
                    "reason": "phone_mismatch",
                    "message": "Those last four digits don't match our records. Please see the front desk.",
                }
        else:
            # Different people, no phone provided — ask for disambiguation
            await log_tool_call(conversation_id, "verify_patient", None, "need_phone",
                                f"last_name={last_name}, {len(rows)} matches")
            return {
                "verified": False,
                "reason": "need_phone",
                "message": "I found a few records with that name and date of birth. Can you tell me the last four digits of your phone number?",
            }

    if patient:
        patient_id = int(patient["PatNum"])
        full_name = patient["full_name"]
        await log_tool_call(conversation_id, "verify_patient", patient_id, "verified",
                            f"name={full_name}, searched={name}, method={match_method}")

        # Auto-fetch today's appointment (Tavus CVI can't chain tool calls)
        today_data = await get_today_appointment(conversation_id, patient_id)

        # Build result — includes searched_name and match_method for frontend pill-banner
        base = {
            "verified": True,
            "patient_id": patient_id,
            "name": full_name,
            "searched_name": name,
            "match_method": match_method,
        }

        if today_data.get("status") == "found":
            apts = today_data.get("appointments", [])
            apt = apts[0] if apts else {}
            return {
                **base,
                "result": "VERIFIED_HAS_APPOINTMENT",
                "appointment_type": apt.get("type", "appointment"),
                "appointment_time": apt.get("time", ""),
                "appointment_provider": apt.get("provider", "the doctor"),
                "appointment_id": apt.get("appointment_id"),
                "say_this": f"Found you, {full_name}! You have a {apt.get('type', 'appointment')} at {apt.get('time', '')} with {apt.get('provider', 'the doctor')}. Want me to check you in?",
            }
        else:
            return {
                **base,
                "result": "VERIFIED_NO_APPOINTMENT",
                "say_this": f"Found you, {full_name}! I don't see any appointments for you today though.",
            }
    else:
        await log_tool_call(conversation_id, "verify_patient", None, "not_found",
                            f"last_name={last_name}, dob={dob}, method={match_method}")
        return {
            "verified": False,
            "reason": "not_found",
            "searched_name": name,
            "message": "No patient found with that name and date of birth.",
        }


async def get_balance(conversation_id: str, patient_id: int) -> dict:
    """Get patient balance from Open Dental.

    Uses BalTotal (current charges) + EstBalance (includes planned treatment).
    Also fetches fee for the next scheduled appointment.
    """
    rows = await execute_query(
        """
        SELECT
            p.BalTotal,
            p.EstBalance,
            p.InsEst,
            p.Bal_0_30, p.Bal_31_60, p.Bal_61_90, p.BalOver90
        FROM patient p
        WHERE p.PatNum = %s
        """,
        (patient_id,),
    )

    if not rows:
        await log_tool_call(conversation_id, "get_balance", patient_id, "patient_not_found", "")
        return {"status": "error", "message": "Patient not found."}

    row = rows[0]
    bal_total = float(row.get("BalTotal") or 0)
    est_balance = float(row.get("EstBalance") or 0)
    ins_est = float(row.get("InsEst") or 0)

    # Current outstanding balance (what patient owes NOW)
    current_owed = max(0, bal_total)

    # Estimated patient portion from planned treatment
    # EstBalance is negative when patient will owe money for planned procedures
    estimated_upcoming = abs(est_balance) if est_balance < 0 else 0

    # Fetch next appointment fee (planned procedures linked to upcoming appointment)
    next_fee = 0.0
    fee_rows = await execute_query(
        """
        SELECT COALESCE(SUM(pl.ProcFee), 0) AS total_fee
        FROM procedurelog pl
        JOIN appointment a ON pl.AptNum = a.AptNum
        WHERE pl.PatNum = %s
          AND pl.ProcStatus = 1
          AND a.AptStatus = 1
          AND DATE(a.AptDateTime) >= CURDATE()
        ORDER BY a.AptDateTime ASC
        LIMIT 1
        """,
        (patient_id,),
    )
    if fee_rows and fee_rows[0].get("total_fee"):
        next_fee = float(fee_rows[0]["total_fee"])

    # Determine what to show the patient
    total_relevant = current_owed + estimated_upcoming
    # If we have a next appointment fee but no estimated balance, use that
    if total_relevant == 0 and next_fee > 0:
        total_relevant = next_fee

    await log_tool_call(
        conversation_id, "get_balance", patient_id, "success",
        f"current={current_owed:.2f} estimated={estimated_upcoming:.2f} next_fee={next_fee:.2f}",
    )

    if total_relevant == 0:
        return {
            "status": "success",
            "balance": 0.00,
            "insurance_pending": round(ins_est, 2),
            "message": "Great news! You have no outstanding balance.",
        }

    # Build a clear message
    parts = []
    if current_owed > 0:
        parts.append(f"outstanding balance of ${current_owed:.0f}")
    if estimated_upcoming > 0 and estimated_upcoming != current_owed:
        parts.append(f"estimated charges of ${estimated_upcoming:.0f} for planned treatment")
    if next_fee > 0 and next_fee != estimated_upcoming:
        parts.append(f"next visit fee of ${next_fee:.0f}")

    msg = "You have " + " and ".join(parts) + "." if parts else f"Your balance is ${total_relevant:.0f}."

    return {
        "status": "success",
        "balance": round(total_relevant, 2),
        "insurance_pending": round(ins_est, 2),
        "current_owed": round(current_owed, 2),
        "estimated_upcoming": round(estimated_upcoming, 2),
        "next_appointment_fee": round(next_fee, 2),
        "message": msg,
    }


async def get_appointments(conversation_id: str, patient_id: int) -> dict:
    """Get upcoming appointments for a patient."""
    rows = await execute_query(
        """
        SELECT
            a.AptNum,
            a.AptDateTime,
            a.ProcDescript,
            a.AptStatus,
            CONCAT(pr.FName, ' ', pr.LName) AS provider_name,
            pr.Abbr AS provider_abbr,
            o.OpName AS room
        FROM appointment a
        JOIN provider pr ON a.ProvNum = pr.ProvNum
        LEFT JOIN operatory o ON a.Op = o.OperatoryNum
        WHERE a.PatNum = %s
          AND DATE(a.AptDateTime) >= CURDATE()
          AND a.AptStatus = 1
        ORDER BY a.AptDateTime
        LIMIT 5
        """,
        (patient_id,),
    )

    await log_tool_call(conversation_id, "get_appointments", patient_id, "success", f"count={len(rows)}")

    appointments = []
    for row in rows:
        dt = row["AptDateTime"]
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)
        date_str = dt.strftime("%A, %B %d").replace(" 0", " ")
        time_str = dt.strftime("%I:%M %p").lstrip("0")

        appointments.append({
            "id": int(row["AptNum"]),
            "date": date_str,
            "time": time_str,
            "type": _simplify_proc(row.get("ProcDescript", "")),
            "provider": _format_provider(row),
            "room": row.get("room") or "",
        })

    if not appointments:
        return {
            "status": "success",
            "appointments": [],
            "message": "You have no upcoming appointments.",
        }
    return {
        "status": "success",
        "appointments": appointments,
        "message": f"You have {len(appointments)} upcoming appointment(s).",
    }


async def get_today_appointment(conversation_id: str, patient_id: int) -> dict:
    """Get today's appointment(s) for a patient.

    Returns appointment details including whether already checked in.
    This is the key tool for the kiosk check-in flow.
    """
    rows = await execute_query(
        """
        SELECT
            a.AptNum,
            a.AptDateTime,
            a.ProcDescript,
            a.AptStatus,
            a.Confirmed,
            CONCAT(pr.FName, ' ', pr.LName) AS provider_name,
            pr.Abbr AS provider_abbr,
            o.OpName AS room
        FROM appointment a
        JOIN provider pr ON a.ProvNum = pr.ProvNum
        LEFT JOIN operatory o ON a.Op = o.OperatoryNum
        WHERE a.PatNum = %s
          AND DATE(a.AptDateTime) = CURDATE()
          AND a.AptStatus = 1
        ORDER BY a.AptDateTime
        LIMIT 5
        """,
        (patient_id,),
    )

    await log_tool_call(
        conversation_id, "get_today_appointment", patient_id,
        "success", f"count={len(rows)}",
    )

    appointments = []
    for row in rows:
        dt = row["AptDateTime"]
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)
        time_str = dt.strftime("%I:%M %p").lstrip("0")

        already_checked_in = row.get("Confirmed") == 5

        appointments.append({
            "appointment_id": int(row["AptNum"]),
            "time": time_str,
            "type": _simplify_proc(row.get("ProcDescript", "")),
            "provider": _format_provider(row),
            "room": row.get("room") or "",
            "already_checked_in": already_checked_in,
        })

    if not appointments:
        return {
            "status": "no_appointment",
            "appointments": [],
            "message": "No appointment found for today.",
        }
    return {
        "status": "found",
        "appointments": appointments,
        "count": len(appointments),
        "message": f"Found {len(appointments)} appointment(s) for today.",
    }


async def check_in_patient(conversation_id: str, appointment_id: int) -> dict:
    """Check in a patient for their appointment (AI agent tool).

    Marks the appointment as arrived (Confirmed = 5 in Open Dental)
    and logs the action for HIPAA audit.
    """
    # Verify the appointment exists and check its status (READ ONLY)
    rows = await execute_query(
        """
        SELECT a.AptNum, a.AptStatus, a.Confirmed, a.PatNum
        FROM appointment a
        WHERE a.AptNum = %s
        """,
        (appointment_id,),
    )

    if not rows:
        await log_tool_call(conversation_id, "check_in_patient", None, "not_found", f"apt_id={appointment_id}")
        return {"status": "error", "message": "Appointment not found."}

    apt = rows[0]
    patient_id = int(apt["PatNum"])

    if apt["Confirmed"] == 5:
        await log_tool_call(conversation_id, "check_in_patient", patient_id, "already_checked_in", f"apt_id={appointment_id}")
        return {"status": "already_checked_in", "message": "You're already checked in for this appointment!"}

    if apt["AptStatus"] != 1:
        await log_tool_call(conversation_id, "check_in_patient", patient_id, "invalid_status", f"apt_id={appointment_id}, status={apt['AptStatus']}")
        return {"status": "error", "message": "This appointment cannot be checked in."}

    # ---- TEMPORARILY DISABLED: DB write to Open Dental ----
    # affected = await execute_update(
    #     "UPDATE appointment SET Confirmed = 5 WHERE AptNum = %s AND AptStatus = 1",
    #     (appointment_id,),
    # )
    #
    # if affected == 0:
    #     await log_tool_call(conversation_id, "check_in_patient", patient_id, "update_failed", f"apt_id={appointment_id}")
    #     return {"status": "error", "message": "Could not check in. Please see the front desk."}
    # ---- END DISABLED ----

    await log_tool_call(conversation_id, "check_in_patient", patient_id, "checked_in (DRY RUN)", f"apt_id={appointment_id}")
    logger.info("[DRY RUN] check_in_patient: would UPDATE appointment %s SET Confirmed=5", appointment_id)

    return {
        "status": "checked_in",
        "message": "You're all checked in! Please have a seat and we'll call you shortly.",
    }


async def book_appointment(
    conversation_id: str, patient_id: int, date_str: str, time_str: str, procedure: str = ""
) -> dict:
    """Submit an appointment request (does NOT write directly to Open Dental schedule)."""

    # ---- TEMPORARILY DISABLED: DB write ----
    # await execute_ddl("""
    #     CREATE TABLE IF NOT EXISTS kiosk_appointment_requests (
    #         id INT AUTO_INCREMENT PRIMARY KEY,
    #         PatNum INT NOT NULL,
    #         requested_date DATE,
    #         requested_time VARCHAR(20),
    #         reason TEXT,
    #         status VARCHAR(20) DEFAULT 'pending',
    #         created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    #     )
    # """)
    #
    # request_id = await execute_insert(
    #     """
    #     INSERT INTO kiosk_appointment_requests
    #         (PatNum, requested_date, requested_time, reason)
    #     VALUES (%s, %s, %s, %s)
    #     """,
    #     (patient_id, date_str, time_str, procedure),
    # )
    #
    # confirmation = f"REQ-{request_id:04d}"
    # ---- END DISABLED ----

    confirmation = f"REQ-DRY-{patient_id}"
    logger.info("[DRY RUN] book_appointment: would INSERT for patient %s, date=%s, time=%s", patient_id, date_str, time_str)

    await log_tool_call(
        conversation_id, "book_appointment", patient_id,
        "submitted (DRY RUN)", f"date={date_str}, time={time_str}, ref={confirmation}",
    )

    return {
        "status": "success",
        "confirmation_number": confirmation,
        "date": date_str,
        "time": time_str,
        "procedure": procedure,
        "message": f"Appointment request submitted! Reference: {confirmation}. Staff will confirm shortly.",
    }


async def send_sms_reminder(conversation_id: str, patient_id: int, appointment_id: Optional[int] = None) -> dict:
    """Send SMS reminder to patient for an appointment."""
    # Get patient phone number
    rows = await execute_query(
        "SELECT WirelessPhone, HmPhone, FName, LName FROM patient WHERE PatNum = %s",
        (patient_id,),
    )

    if not rows:
        return {"status": "error", "message": "Patient not found."}

    patient = rows[0]
    phone = (patient.get("WirelessPhone") or "").strip()
    if not phone:
        phone = (patient.get("HmPhone") or "").strip()
    if not phone:
        return {"status": "error", "message": "No phone number on file for this patient."}

    # Mask phone — show last 4 digits
    digits = re.sub(r"\D", "", phone)
    masked = f"+1***{digits[-4:]}" if len(digits) >= 4 else phone

    # Fetch appointment details if ID provided
    apt_info = "your upcoming appointment"
    if appointment_id:
        apt_rows = await execute_query(
            """
            SELECT a.AptDateTime, a.ProcDescript,
                   CONCAT(pr.FName, ' ', pr.LName) AS provider_name
            FROM appointment a
            JOIN provider pr ON a.ProvNum = pr.ProvNum
            WHERE a.AptNum = %s
            """,
            (appointment_id,),
        )
        if apt_rows:
            apt = apt_rows[0]
            dt = apt["AptDateTime"]
            if isinstance(dt, str):
                dt = datetime.fromisoformat(dt)
            proc = _simplify_proc(apt.get("ProcDescript", ""))
            provider = apt.get("provider_name", "your provider")
            apt_info = f"{proc} on {dt.strftime('%B %d')} at {dt.strftime('%I:%M %p').lstrip('0')} with {provider}"

    # Try Twilio if configured, otherwise log to file
    sms_sent = False
    if settings.twilio_account_sid and settings.twilio_auth_token:
        try:
            from twilio.rest import Client
            client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
            message = client.messages.create(
                body=f"Reminder: You have {apt_info}. - All Nassau Dental",
                from_=settings.twilio_from_number,
                to=phone,
            )
            sms_sent = True
            logger.info("SMS sent: sid=%s", message.sid)
        except Exception as e:
            logger.warning("Twilio SMS failed: %s", e)

    if not sms_sent:
        # Fallback: log to file
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] Patient: {patient['FName']} {patient['LName']} | Phone: {phone} | Appointment: {apt_info}\n"
        with open("sms_log.txt", "a") as f:
            f.write(log_line)

    await log_tool_call(conversation_id, "send_sms_reminder", patient_id, "sent", f"phone={masked}")

    return {
        "status": "success",
        "phone": masked,
        "message": f"SMS reminder sent to {masked} for {apt_info}.",
    }


# ---------------------------------------------------------------------------
# Manual check-in helpers (for staff sidebar)
# ---------------------------------------------------------------------------

async def search_patient_today(last_name: Optional[str] = None, dob_str: Optional[str] = None) -> dict:
    """Search today's scheduled appointments by last name and/or DOB.

    HIPAA: If multiple different patients match, requires additional info.
    """
    all_apts = await execute_query(
        """
        SELECT
            a.AptNum,
            a.AptDateTime,
            a.PatNum,
            a.ProcDescript,
            p.FName  AS PatFName,
            p.LName  AS PatLName,
            p.Birthdate,
            CONCAT(pr.FName, ' ', pr.LName) AS provider_name,
            pr.Abbr  AS provider_abbr,
            o.OpName AS room
        FROM appointment a
        LEFT JOIN patient   p  ON a.PatNum  = p.PatNum
        LEFT JOIN provider  pr ON a.ProvNum = pr.ProvNum
        LEFT JOIN operatory o  ON a.Op      = o.OperatoryNum
        WHERE DATE(a.AptDateTime) = CURDATE()
          AND a.AptStatus = 1
        ORDER BY a.AptDateTime ASC
        """,
    )

    matches = list(all_apts)
    has_name = last_name and last_name.strip()
    has_dob = dob_str and dob_str.strip()

    if not has_name and not has_dob:
        return {"results": [], "status": "no_input"}

    # Filter by last name
    if has_name:
        q = last_name.strip().lower()
        matches = [a for a in matches if (a.get("PatLName") or "").lower().startswith(q)]

    # Filter by DOB
    if has_dob:
        dob_date = None
        try:
            d = dob_str.strip()
            if "/" in d:
                parts = d.split("/")
                dob_date = date(int(parts[2]), int(parts[0]), int(parts[1]))
            else:
                dob_date = date.fromisoformat(d)
        except (ValueError, IndexError):
            dob_date = None

        if dob_date:
            filtered = []
            for a in matches:
                bd = a.get("Birthdate")
                if bd is None:
                    continue
                if hasattr(bd, "date"):
                    bd = bd.date()
                if bd == dob_date:
                    filtered.append(a)
            matches = filtered

    # HIPAA: check unique patients
    unique_patients = {m.get("PatNum") for m in matches}

    if len(unique_patients) > 1:
        if has_name and not has_dob:
            return {
                "results": [],
                "status": "need_dob",
                "message": "Multiple patients found. Please also enter date of birth.",
                "count": len(unique_patients),
            }
        elif has_dob and not has_name:
            return {
                "results": [],
                "status": "need_name",
                "message": "Multiple patients found. Please also enter last name.",
                "count": len(unique_patients),
            }
        else:
            return {
                "results": [],
                "status": "ambiguous",
                "message": "Could not uniquely identify patient. Please see receptionist.",
            }

    # Build result cards (0 or 1 unique patient)
    results = []
    for apt in matches:
        dt = apt.get("AptDateTime")
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)
        time_str = dt.strftime("%I:%M %p").lstrip("0") if dt else ""

        results.append({
            "pat_num": apt.get("PatNum"),
            "apt_num": apt.get("AptNum"),
            "first_name": apt.get("PatFName", ""),
            "last_name": apt.get("PatLName", ""),
            "time": time_str,
            "provider": _format_provider(apt),
            "room": apt.get("room") or "",
            "procedure": _simplify_proc(apt.get("ProcDescript", "")),
        })

    return {"results": results, "status": "ok"}


async def checkin_appointment(apt_num: int) -> dict:
    """Mark an appointment as arrived (Confirmed=5 in Open Dental)."""
    # ---- TEMPORARILY DISABLED: DB write to Open Dental ----
    # affected = await execute_update(
    #     "UPDATE appointment SET Confirmed = 5 WHERE AptNum = %s AND AptStatus = 1",
    #     (apt_num,),
    # )
    # if affected == 0:
    #     return {"status": "error", "message": "Appointment not found or already checked in."}
    # ---- END DISABLED ----
    logger.info("[DRY RUN] checkin_appointment: would UPDATE appointment %s SET Confirmed=5", apt_num)
    return {"status": "ok", "message": "Checked in successfully (dry run)."}
