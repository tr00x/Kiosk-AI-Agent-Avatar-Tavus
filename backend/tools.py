"""Tool webhook handlers for the dental kiosk.

Each function handles a Tavus tool call webhook:
1. verify_patient — Identity verification via name + DOB
2. get_balance — Patient account balance
3. get_appointments — Upcoming appointments list
4. get_today_appointment — Today's appointment for check-in flow
5. check_in_patient — Mark patient as arrived
6. find_available_slots — Find open 30-min slots on a date
7. create_patient — Create new patient record
8. book_appointment — Book appointment in Open Dental
9. send_sms_reminder — Send SMS reminder via Twilio

All functions query the Open Dental MySQL database via db.py and
log every action to the audit table for HIPAA compliance.
"""

import logging
import re
from datetime import date, datetime, timedelta
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


# ---------------------------------------------------------------------------
# Booking procedure type → (ProcDescript, human label)
# ---------------------------------------------------------------------------
PROCEDURE_MAP = {
    "routine_exam_cleaning": ("Ex, Pro", "Routine exam and cleaning"),
    "cleaning": ("Ex, Pro", "Routine exam and cleaning"),
    "exam": ("Ex, Pro", "Routine exam and cleaning"),
    "routine": ("Ex, Pro", "Routine exam and cleaning"),
    "cosmetic": ("Consult", "Cosmetic consultation"),
    "root_canal": ("RCT", "Root canal evaluation"),
    "extraction": ("Ext", "Tooth extraction"),
    "tooth_replacement": ("Consult", "Tooth replacement evaluation"),
    "implant": ("Consult", "Tooth replacement evaluation"),
    "consult": ("Consult", "Consultation"),
    "consultation": ("Consult", "Consultation"),
}


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

    # Try common natural language formats
    _MONTHS = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    # "March 15 1985" or "March 15, 1985"
    m = re.match(r"^([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})$", s)
    if m:
        month_name = m.group(1).lower()
        if month_name in _MONTHS:
            return f"{int(m.group(3)):04d}-{_MONTHS[month_name]:02d}-{int(m.group(2)):02d}"
    # "15 March 1985"
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$", s)
    if m:
        month_name = m.group(2).lower()
        if month_name in _MONTHS:
            return f"{int(m.group(3)):04d}-{_MONTHS[month_name]:02d}-{int(m.group(1)):02d}"

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
        upper_parts = {p.upper() for p in name.split()}
        if upper_parts & _NON_PERSON:
            return "your dentist"  # generic — receptionist assigns real doctor
        return f"Dr. {name}"
    if abbr:
        upper_abbr = {p.upper() for p in abbr.split()}
        if upper_abbr & _NON_PERSON:
            return "your dentist"
        if abbr.lower().startswith("dr"):
            return abbr
        return f"Dr. {abbr}"
    return "your dentist"


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
            "searched_dob": dob,
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
            a.DateTimeArrived,
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

        dta = row.get("DateTimeArrived")
        already_checked_in = isinstance(dta, datetime) and dta > datetime(1, 1, 1) and (dta.hour != 0 or dta.minute != 0 or dta.second != 0)

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


# ---------------------------------------------------------------------------
# Exam sheet creation on check-in
# ---------------------------------------------------------------------------

EXAM_SHEETDEF_NUM = 175  # "Exam" template in Open Dental
EXAM_SHEET_TYPE = 13
# SheetFieldDefNum identifiers for fields we fill in
_FIELD_AC = 3635       # "A:\r\n\r\nC:" — appointment & check-in times
_FIELD_NAMEFL = 3383   # "Exam for [nameFL] [PatNum]"
_FIELD_DTS = 3409      # "sheet.DateTimeSheet"
_FIELD_TXNOTE = 3632   # "[treatmentNote]" — staff fills manually, clear placeholder

# Columns to copy from sheetfielddef → sheetfield
_COPY_COLS = (
    "FieldType", "FieldName", "FieldValue", "FontSize", "FontName",
    "FontIsBold", "XPos", "YPos", "Width", "Height", "GrowthBehavior",
    "RadioButtonValue", "RadioButtonGroup", "IsRequired", "TabOrder",
    "ReportableName", "TextAlign", "ItemColor", "IsLocked",
    "TabOrderMobile", "UiLabelMobile", "UiLabelMobileRadioButton",
    "CanElectronicallySign", "IsSigProvRestricted",
)


async def fill_or_create_exam_sheet(
    pat_num: int, apt_datetime: datetime, checkin_time: datetime
) -> Optional[int]:
    """Fill C: time in an existing exam sheet, or create a new one.

    Logic:
    1. Look for an existing exam sheet for this patient where C: is empty.
    2. If found — UPDATE the A:/C: field with the check-in time.
    3. If not found — CREATE a new exam sheet from template.

    Returns the SheetNum or None on failure.
    """
    try:
        checkin_time_str = checkin_time.strftime("%I:%M%p").lstrip("0").lower()
        apt_time_str = apt_datetime.strftime("%I:%M %p").lstrip("0")

        # 1) Look for existing exam sheet with empty C: (today only)
        existing = await execute_query(
            """
            SELECT sf.SheetFieldNum, sf.SheetNum, sf.FieldValue
            FROM sheetfield sf
            JOIN sheet s ON s.SheetNum = sf.SheetNum
            WHERE s.PatNum = %s
              AND s.SheetDefNum = %s
              AND s.IsDeleted = 0
              AND DATE(s.DateTimeSheet) = CURDATE()
              AND sf.SheetFieldDefNum = %s
              AND sf.FieldValue LIKE '%%C:%%'
              AND TRIM(SUBSTRING_INDEX(sf.FieldValue, 'C:', -1)) = ''
            ORDER BY s.DateTimeSheet DESC
            LIMIT 1
            """,
            (pat_num, EXAM_SHEETDEF_NUM, _FIELD_AC),
        )

        if existing:
            # Found a sheet with empty C: — update it
            row = existing[0]
            old_value = row["FieldValue"]
            # Replace the empty C: with the check-in time, keep original A: value
            new_value = old_value.rstrip() + " " + checkin_time_str
            await execute_update(
                "UPDATE sheetfield SET FieldValue = %s WHERE SheetFieldNum = %s",
                (new_value, row["SheetFieldNum"]),
            )
            logger.info(
                "fill_or_create_exam_sheet: updated SheetNum=%s for PatNum=%s (C: %s)",
                row["SheetNum"], pat_num, checkin_time_str,
            )
            return row["SheetNum"]

        # 2) No existing sheet — create new one
        return await _create_exam_sheet_new(pat_num, apt_datetime, checkin_time)

    except Exception:
        logger.exception("fill_or_create_exam_sheet failed for PatNum=%s", pat_num)
        return None


async def _create_exam_sheet_new(
    pat_num: int, apt_datetime: datetime, checkin_time: datetime
) -> Optional[int]:
    """Create a brand new Exam sheet from template with A: and C: filled in."""
    # Get patient name
    pat_rows = await execute_query(
        "SELECT FName, LName FROM patient WHERE PatNum = %s", (pat_num,)
    )
    if not pat_rows:
        logger.error("_create_exam_sheet_new: patient %s not found", pat_num)
        return None
    fname = pat_rows[0]["FName"]
    lname = pat_rows[0]["LName"]

    # Get template definition
    tpl_rows = await execute_query(
        "SELECT FontSize, FontName, Width, Height, IsLandscape, IsMultiPage, HasMobileLayout "
        "FROM sheetdef WHERE SheetDefNum = %s",
        (EXAM_SHEETDEF_NUM,),
    )
    if not tpl_rows:
        logger.error("_create_exam_sheet_new: sheetdef %s not found", EXAM_SHEETDEF_NUM)
        return None
    tpl = tpl_rows[0]

    now = datetime.now()
    apt_time_str = apt_datetime.strftime("%I:%M %p").lstrip("0")
    checkin_time_str = checkin_time.strftime("%I:%M%p").lstrip("0").lower()

    # 1) Insert sheet record
    sheet_num = await execute_insert(
        """INSERT INTO sheet
           (SheetType, PatNum, DateTimeSheet, FontSize, FontName, Width, Height,
            IsLandscape, InternalNote, Description, ShowInTerminal, IsWebForm,
            IsMultiPage, IsDeleted, SheetDefNum, DocNum, ClinicNum,
            DateTSheetEdited, HasMobileLayout, RevID, WebFormSheetID)
        VALUES (%s, %s, %s, %s, %s, %s, %s,
                %s, '', 'Exam', 0, 0,
                %s, 0, %s, 0, 0,
                %s, %s, 0, 0)""",
        (
            EXAM_SHEET_TYPE, pat_num, now,
            tpl["FontSize"], tpl["FontName"], tpl["Width"], tpl["Height"],
            tpl["IsLandscape"],
            tpl["IsMultiPage"], EXAM_SHEETDEF_NUM,
            now, tpl["HasMobileLayout"],
        ),
    )

    # 2) Copy all fields from template
    select_cols = ", ".join(_COPY_COLS)
    field_defs = await execute_query(
        f"SELECT SheetFieldDefNum, {select_cols} FROM sheetfielddef "
        f"WHERE SheetDefNum = %s ORDER BY SheetFieldDefNum",
        (EXAM_SHEETDEF_NUM,),
    )

    name_str = f"Exam for {fname} {lname} {pat_num}"
    dt_sheet_str = now.strftime("%m/%d/%Y %I:%M:%S %p")

    insert_cols = "SheetNum, SheetFieldDefNum, " + ", ".join(_COPY_COLS)
    placeholders = ", ".join(["%s"] * (2 + len(_COPY_COLS)))

    for fd in field_defs:
        def_num = fd["SheetFieldDefNum"]
        vals = [fd[c] for c in _COPY_COLS]

        # Substitute dynamic values
        if def_num == _FIELD_AC:
            vals[2] = f"A: {apt_time_str}\n\nC: {checkin_time_str}"
        elif def_num == _FIELD_NAMEFL:
            vals[2] = name_str
        elif def_num == _FIELD_DTS:
            vals[2] = dt_sheet_str
        elif def_num == _FIELD_TXNOTE:
            vals[2] = ""  # clear placeholder, staff fills manually

        await execute_insert(
            f"INSERT INTO sheetfield ({insert_cols}) VALUES ({placeholders})",
            (sheet_num, def_num, *vals),
        )

    logger.info(
        "_create_exam_sheet_new: created SheetNum=%s for PatNum=%s (A: %s, C: %s)",
        sheet_num, pat_num, apt_time_str, checkin_time_str,
    )
    return sheet_num


async def check_in_patient(conversation_id: str, appointment_id: int) -> dict:
    """Check in a patient for their appointment (AI agent tool).

    Sets DateTimeArrived = NOW() in Open Dental and logs for HIPAA audit.
    """
    # Verify the appointment exists and check its status
    rows = await execute_query(
        """
        SELECT a.AptNum, a.AptStatus, a.Confirmed, a.PatNum, a.DateTimeArrived
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

    # Already checked in?
    # Open Dental sets DateTimeArrived to the appointment date at midnight (00:00:00)
    # as default — that does NOT mean checked in.  Only a non-midnight time counts.
    dta = apt.get("DateTimeArrived")
    if isinstance(dta, datetime) and dta > datetime(1, 1, 1) and (dta.hour != 0 or dta.minute != 0 or dta.second != 0):
        arrived_time = dta.strftime("%I:%M %p").lstrip("0")
        await log_tool_call(conversation_id, "check_in_patient", patient_id, "already_checked_in", f"apt_id={appointment_id}")
        return {"status": "already_checked_in", "appointment_id": appointment_id, "checked_in_time": arrived_time, "message": "You're already checked in for this appointment!"}

    if apt["AptStatus"] != 1:
        await log_tool_call(conversation_id, "check_in_patient", patient_id, "invalid_status", f"apt_id={appointment_id}, status={apt['AptStatus']}")
        return {"status": "error", "message": "This appointment cannot be checked in."}

    # Get appointment time for exam sheet before updating
    apt_time_rows = await execute_query(
        "SELECT AptDateTime FROM appointment WHERE AptNum = %s", (appointment_id,),
    )
    apt_datetime = apt_time_rows[0]["AptDateTime"] if apt_time_rows else None

    # Set arrival time
    affected = await execute_update(
        "UPDATE appointment SET DateTimeArrived = NOW() WHERE AptNum = %s AND AptStatus = 1 AND (DateTimeArrived <= '0001-01-01' OR TIME(DateTimeArrived) = '00:00:00')",
        (appointment_id,),
    )

    if affected == 0:
        await log_tool_call(conversation_id, "check_in_patient", patient_id, "update_failed", f"apt_id={appointment_id}")
        return {"status": "error", "message": "Could not check in. Please see the front desk."}

    now = datetime.now()

    # Create exam sheet with A: and C: times
    if apt_datetime:
        sheet_num = await fill_or_create_exam_sheet(patient_id, apt_datetime, now)
        if sheet_num:
            logger.info("check_in_patient: exam sheet %s created for apt %s", sheet_num, appointment_id)

    await log_tool_call(conversation_id, "check_in_patient", patient_id, "checked_in", f"apt_id={appointment_id}")
    logger.info("check_in_patient: SET DateTimeArrived=NOW() on appointment %s", appointment_id)

    return {
        "status": "checked_in",
        "appointment_id": appointment_id,
        "checked_in_time": now.strftime("%I:%M %p").lstrip("0"),
        "message": "You're all checked in! Please have a seat and we'll call you shortly.",
    }


async def find_available_slots(
    conversation_id: str, date_str: str, procedure_type: str = ""
) -> dict:
    """Find available 30-minute appointment slots on a given date.

    Checks provider schedules in Open Dental, subtracts existing appointments,
    and returns up to 6 open slots.
    """
    # Parse the requested date
    try:
        target_date = datetime.strptime(_parse_dob(date_str), "%Y-%m-%d").date()
    except (ValueError, Exception) as e:
        await log_tool_call(conversation_id, "find_available_slots", None, "parse_date_failed", f"date={date_str}")
        return {"status": "error", "message": f"Could not understand the date: {date_str}. Please try again."}

    # Must be a future date (not today or in the past)
    today = date.today()
    if target_date <= today:
        await log_tool_call(conversation_id, "find_available_slots", None, "past_date", f"date={target_date}")
        return {"status": "error", "message": "Please choose a future date — I can only book appointments for tomorrow or later."}

    # Reject weekends
    if target_date.weekday() >= 5:
        await log_tool_call(conversation_id, "find_available_slots", None, "weekend", f"date={target_date}")
        return {"status": "no_slots", "message": f"The office is closed on weekends. Please choose a weekday."}

    # Get provider schedules for that date (BlockoutType=0 means actual provider schedule)
    schedules = await execute_query(
        """
        SELECT StartTime, StopTime
        FROM schedule
        WHERE SchedDate = %s
          AND BlockoutType = 0
          AND ProvNum > 0
        """,
        (target_date.isoformat(),),
    )

    # Fallback: if no provider schedules exist, use default office hours (9 AM – 5 PM)
    use_default_hours = False
    if not schedules:
        use_default_hours = True
        logger.info("find_available_slots: No schedules for %s, using default office hours 9am-5pm", target_date)

    # Determine the overall time window from schedules
    if use_default_hours:
        min_start = 9 * 3600   # 9 AM
        max_stop = 17 * 3600   # 5 PM
    else:
        # StartTime/StopTime are timedelta objects in MySQL
        min_start = None
        max_stop = None
        for sched in schedules:
            start = sched["StartTime"]
            stop = sched["StopTime"]
            if isinstance(start, timedelta):
                start_seconds = int(start.total_seconds())
            else:
                start_seconds = int(start) if start else 0
            if isinstance(stop, timedelta):
                stop_seconds = int(stop.total_seconds())
            else:
                stop_seconds = int(stop) if stop else 0

            if min_start is None or start_seconds < min_start:
                min_start = start_seconds
            if max_stop is None or stop_seconds > max_stop:
                max_stop = stop_seconds

        if min_start is None or max_stop is None or min_start >= max_stop:
            await log_tool_call(conversation_id, "find_available_slots", None, "invalid_schedule", f"date={target_date}")
            return {"status": "no_slots", "message": "No available times on that date."}

    # Get existing appointments for that date
    existing_apts = await execute_query(
        """
        SELECT AptDateTime
        FROM appointment
        WHERE DATE(AptDateTime) = %s
          AND AptStatus = 1
        """,
        (target_date.isoformat(),),
    )

    # Collect existing appointment start times as total seconds from midnight
    booked_seconds = set()
    for apt in existing_apts:
        dt = apt["AptDateTime"]
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)
        apt_seconds = dt.hour * 3600 + dt.minute * 60
        booked_seconds.add(apt_seconds)

    # Generate 30-min slots and exclude overlapping ones
    slot_duration = 1800  # 30 minutes in seconds
    available = []
    current = min_start
    while current + slot_duration <= max_stop:
        # Check if any existing appointment starts within 30 min of this slot
        conflict = False
        for booked in booked_seconds:
            if abs(booked - current) < slot_duration:
                conflict = True
                break
        if not conflict:
            hours = current // 3600
            minutes = (current % 3600) // 60
            slot_dt = datetime(target_date.year, target_date.month, target_date.day, hours, minutes)
            time_label = slot_dt.strftime("%I:%M %p").lstrip("0")
            available.append({"time": time_label})
        current += slot_duration

    if not available:
        await log_tool_call(conversation_id, "find_available_slots", None, "fully_booked", f"date={target_date}")
        return {"status": "no_slots", "message": f"No available times on {target_date.strftime('%B %d')}. Would you like to try a different date?"}

    # Limit to 6 slots to keep it conversational
    slots = available[:6]
    date_label = target_date.strftime("%B %d").replace(" 0", " ")

    await log_tool_call(
        conversation_id, "find_available_slots", None, "success",
        f"date={target_date}, slots={len(slots)}/{len(available)}, procedure={procedure_type}",
    )

    return {
        "status": "success",
        "date": date_label,
        "slots": slots,
        "total_available": len(available),
        "message": f"I found {len(slots)} available time{'s' if len(slots) != 1 else ''} on {date_label}.",
    }


async def create_patient(
    conversation_id: str, first_name: str, last_name: str, dob: str,
    phone: str = "", insurance: str = ""
) -> dict:
    """Create a minimal patient record in Open Dental for new patients."""
    # Parse DOB
    try:
        dob_iso = _parse_dob(dob)
    except ValueError:
        await log_tool_call(conversation_id, "create_patient", None, "parse_dob_failed", f"dob={dob}")
        return {"status": "error", "message": f"Could not understand the date of birth: {dob}. Please try again."}

    first_name = first_name.strip().title()
    last_name = last_name.strip().title()
    phone_clean = _extract_digits(phone) if phone else ""
    insurance_clean = insurance.strip() if insurance else ""

    # Note field stores insurance info for front desk reference
    note = f"Insurance: {insurance_clean}" if insurance_clean and insurance_clean.lower() != "none" else ""

    try:
        patient_id = await execute_insert(
            """
            INSERT INTO patient (LName, FName, Birthdate, WirelessPhone, PatStatus, PriProv, ClinicNum, AddrNote)
            VALUES (%s, %s, %s, %s, 0, 10, 1, %s)
            """,
            (last_name, first_name, dob_iso, phone_clean, note),
        )
    except Exception as e:
        logger.error("create_patient INSERT failed: %s", e)
        await log_tool_call(conversation_id, "create_patient", None, "insert_failed", str(e))
        return {"status": "error", "message": "Could not create patient record. Please see the front desk."}

    full_name = f"{first_name} {last_name}"
    await log_tool_call(
        conversation_id, "create_patient", patient_id, "created",
        f"name={full_name}, dob={dob_iso}, phone={phone_clean}, insurance={insurance_clean}",
    )

    return {
        "status": "success",
        "patient_id": patient_id,
        "name": full_name,
        "insurance": insurance_clean,
        "message": f"Patient record created for {full_name}.",
    }


async def book_appointment(
    conversation_id: str, patient_id: int, date_str: str, time_str: str,
    procedure_type: str = "", insurance_info: str = "", is_new_patient: bool = False
) -> dict:
    """Book an appointment by inserting directly into Open Dental."""
    # Parse date
    try:
        apt_date = datetime.strptime(_parse_dob(date_str), "%Y-%m-%d").date()
    except (ValueError, Exception):
        await log_tool_call(conversation_id, "book_appointment", patient_id, "parse_date_failed", f"date={date_str}")
        return {"status": "error", "message": f"Could not understand the date: {date_str}."}

    # Parse time (e.g. "10:00 AM", "2:30 PM", "14:00")
    try:
        t = time_str.strip().upper()
        is_pm = "PM" in t
        is_am = "AM" in t
        t = t.replace("AM", "").replace("PM", "").strip()
        parts = t.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        if is_pm and hour != 12:
            hour += 12
        elif is_am and hour == 12:
            hour = 0
        apt_datetime = datetime(apt_date.year, apt_date.month, apt_date.day, hour, minute)
    except Exception:
        await log_tool_call(conversation_id, "book_appointment", patient_id, "parse_time_failed", f"time={time_str}")
        return {"status": "error", "message": f"Could not understand the time: {time_str}."}

    # Look up procedure info
    proc_key = procedure_type.lower().strip() if procedure_type else ""
    proc_descript, proc_label = PROCEDURE_MAP.get(proc_key, ("Ex, Pro", "Dental Visit"))

    # Build note
    note_parts = ["Booked via AI kiosk"]
    if insurance_info:
        note_parts.append(f"Insurance: {insurance_info}")
    note = ". ".join(note_parts)

    is_new = 1 if is_new_patient else 0

    try:
        appointment_id = await execute_insert(
            """
            INSERT INTO appointment (
                PatNum, AptStatus, AptDateTime, Pattern, ProvNum, Op, Confirmed,
                ProvHyg, Assistant, ProcDescript, Note, ClinicNum, IsNewPatient
            ) VALUES (%s, 1, %s, '//////', 10, 10, 19, 0, 0, %s, %s, 1, %s)
            """,
            (patient_id, apt_datetime.strftime("%Y-%m-%d %H:%M:%S"),
             proc_descript, note, is_new),
        )
    except Exception as e:
        logger.error("book_appointment INSERT failed: %s", e)
        await log_tool_call(conversation_id, "book_appointment", patient_id, "insert_failed", str(e))
        return {"status": "error", "message": "Could not book the appointment. Please see the front desk."}

    date_label = apt_date.strftime("%B %d").replace(" 0", " ")
    time_label = apt_datetime.strftime("%I:%M %p").lstrip("0")

    await log_tool_call(
        conversation_id, "book_appointment", patient_id, "booked",
        f"apt_id={appointment_id}, date={date_label}, time={time_label}, proc={proc_descript}, new={is_new}",
    )

    return {
        "status": "success",
        "appointment_id": appointment_id,
        "date": date_label,
        "time": time_label,
        "procedure": proc_label,
        "message": f"Your {proc_label.lower()} is booked for {date_label} at {time_label}!",
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
    """Mark an appointment as arrived (DateTimeArrived=NOW() in Open Dental)."""
    # Get appointment info for exam sheet before updating
    apt_rows = await execute_query(
        "SELECT PatNum, AptDateTime FROM appointment WHERE AptNum = %s", (apt_num,),
    )

    affected = await execute_update(
        "UPDATE appointment SET DateTimeArrived = NOW() WHERE AptNum = %s AND AptStatus = 1 AND (DateTimeArrived <= '0001-01-01' OR TIME(DateTimeArrived) = '00:00:00')",
        (apt_num,),
    )
    if affected == 0:
        return {"status": "error", "message": "Appointment not found or already checked in."}

    now = datetime.now()

    # Create exam sheet with A: and C: times
    if apt_rows:
        pat_num = int(apt_rows[0]["PatNum"])
        apt_datetime = apt_rows[0]["AptDateTime"]
        sheet_num = await fill_or_create_exam_sheet(pat_num, apt_datetime, now)
        if sheet_num:
            logger.info("checkin_appointment: exam sheet %s created for apt %s", sheet_num, apt_num)

    logger.info("checkin_appointment: SET DateTimeArrived=NOW() on appointment %s", apt_num)
    return {"status": "ok", "message": "Checked in successfully."}
