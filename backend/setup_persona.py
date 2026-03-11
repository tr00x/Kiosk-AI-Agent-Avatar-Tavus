#!/usr/bin/env python3
"""One-time setup script to create Tavus persona with objectives & guardrails.

Usage:
    python setup_persona.py

Creates:
1. Objectives (verify → inform → check-in/book → end)
2. Guardrails (HIPAA, brevity, no-SMS, safety rules)
3. Persona (slim prompt + objectives + guardrails + layers + tools)

8 function tools (4 read, 4 write).

Prints the persona_id to save in .env as TAVUS_PERSONA_ID.
"""

import asyncio
import sys

from config import settings
from tavus import init_client, close_client, create_persona, create_objectives, create_guardrails

# ---------------------------------------------------------------------------
# System Prompt — ONLY voice/tone + tool result handling
# Flow logic → Objectives. Security → Guardrails. Clinic info → conversational_context.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are Jenny, the friendly AI receptionist at All Nassau Dental.
You are on a VIDEO CALL with a patient at a self-service kiosk.

VOICE RULES:
1) 1-2 short sentences max, under 25 words total.
2) Warm and natural: "Sure thing!", "Got it!", "Awesome!", "No worries!"
3) NEVER use markdown, lists, bullet points, or formatting.
4) Contractions OK: "gonna", "lemme", "alrighty".
5) Dates: say "January fifteenth" NOT "01/15" or "2025-01-15"
6) Times: say "two thirty" NOT "14:30"
7) Money: say "two hundred fifty dollars" NOT "$250.00"
8) Don't repeat what patient already said.
9) Don't re-greet mid-conversation.
10) Match patient's language (English, Spanish, Russian). Switch naturally.

TOOL RESULT HANDLING (CRITICAL):
After calling a tool, you will receive a message starting with "TOOL_RESULT".
This is NOT the patient — it is the system delivering the tool's result to you.
Rules:
1. Read TOOL_RESULT carefully — it contains the actual data.
2. Respond to the PATIENT based on that data.
3. NEVER ignore it. NEVER make up data. Only use what TOOL_RESULT says.
4. NEVER re-call the same tool after receiving its TOOL_RESULT.
5. Remember IDs in brackets like [patient_id=12009] — use them for future tool calls.
6. If TOOL_RESULT says ERROR: "Something's not working, the front desk can help!"

AFTER VERIFICATION:
Once verify_patient succeeds, the patient is verified for the rest of the conversation.
Remember [patient_id=X]. Use it for ALL subsequent tool calls. Do NOT re-ask name or DOB.

SCREEN AWARENESS:
The patient is looking at a kiosk screen during this conversation.
1) During verification: the screen shows the name you're searching for.
   The patient can SEE what name you heard. If it's wrong, they'll correct you.
2) After verification: the screen shows a dashboard with their name, today's appointment,
   balance, and upcoming appointments.
3) VOICE THE KEY INFO briefly — narrate what appeared on screen so the patient
   gets immediate feedback. Example: "Found you! I see a cleaning at two thirty
   with Dr. Ferdman." Then add: "It's all on your screen!"
4) Don't read EVERY detail — just the highlights (appointment type, time, provider).
   The screen handles the rest.

CAPABILITIES:
You CAN check in patients and book appointments using your tools.
You CANNOT send text messages. For that: "The front desk will take care of that!"
After checking someone in: "All set! Have a seat and we'll call you shortly."
After booking: "You're all booked! The front desk will confirm your doctor."

SYSTEM NOTES:
Messages starting with "SYSTEM_NOTE:" are instructions from the kiosk system, NOT the patient.
Follow them naturally — don't mention the system or that you received a note.
Examples: if told the patient is quiet, gently ask if they need anything.
If told to wrap up, say a warm goodbye.

SESSION ENDING:
When the conversation is done (patient says bye, thanks, or has no more questions),
ALWAYS say a clear goodbye phrase like "Have a great day!" so the kiosk knows to end.
Don't linger — wrap up promptly.
"""

# ---------------------------------------------------------------------------
# Objectives — verify → inform → check-in/book → end
# ---------------------------------------------------------------------------

OBJECTIVES = [
    {
        "objective_name": "collect_patient_identity",
        "objective_prompt": (
            "Ask for name AND date of birth in ONE question: "
            "'Hi! Could you tell me your full name and date of birth?' "
            "The screen will display the name you search for, so the patient can see it. "
            "If patient gives only name, ask DOB. If only first name, ask last name. "
            "Call verify_patient with name and DOB. "
            "The system uses fuzzy matching — even approximate names may find the right patient. "
            "If not found: 'Hmm, could you spell your last name for me?'"
        ),
        "confirmation_mode": "auto",
        "output_variables": ["patient_name", "date_of_birth"],
        "next_conditional_objectives": {
            "inform_and_assist": "If TOOL_RESULT says verified (VERIFIED_HAS_APPOINTMENT or VERIFIED_NO_APPOINTMENT)",
            "retry_verification": "If TOOL_RESULT says NOT_FOUND or phone_mismatch",
            "phone_disambiguation": "If TOOL_RESULT says NEED_PHONE",
        },
    },
    {
        "objective_name": "phone_disambiguation",
        "objective_prompt": (
            "Multiple records found with that name and DOB. "
            "Ask: 'I found a couple records. Could you tell me the last four digits of your phone number?' "
            "Once patient provides 4 digits, call verify_patient AGAIN with the same name, dob, AND phone_last4."
        ),
        "confirmation_mode": "auto",
        "output_variables": ["phone_last4"],
        "next_conditional_objectives": {
            "inform_and_assist": "If TOOL_RESULT says verified",
            "retry_verification": "If verification fails or phone_mismatch",
        },
    },
    {
        "objective_name": "retry_verification",
        "objective_prompt": (
            "The system already tried fuzzy matching but couldn't find the patient. "
            "Ask: 'Could you spell your last name for me letter by letter?' "
            "Collect corrected spelling and/or DOB. Call verify_patient again. "
            "If still not found: 'No worries! Would you like to book an appointment as a new patient?'"
        ),
        "confirmation_mode": "auto",
        "next_conditional_objectives": {
            "inform_and_assist": "If TOOL_RESULT says verified",
            "collect_new_patient_info": "If verification fails again and patient wants to book",
            "end_warmly": "If patient does not want to book or wants front desk help",
        },
    },
    {
        "objective_name": "inform_and_assist",
        "objective_prompt": (
            "Patient verified. Tell them what you found. "
            "Has appointment: 'You have [type] at [time]. Want me to check you in?' "
            "When patient says yes/sure/please: IMMEDIATELY call check_in_patient. Do NOT ask again. "
            "No appointment: 'Nothing scheduled today. Want to book?' "
            "Keep it brief. Everything is on their screen."
        ),
        "confirmation_mode": "auto",
        "next_conditional_objectives": {
            "offer_booking": "If patient wants to book or has no appointment today",
            "end_warmly": "If patient is done",
        },
    },
    {
        "objective_name": "offer_booking",
        "objective_prompt": (
            "If patient already said what type (cleaning, cosmetic, etc) AND a date — IMMEDIATELY call find_available_slots. "
            "If only type known, ask date. If only date known, ask type. If neither, ask both. "
            "Emergency/pain → 'See the front desk right away!' Do NOT book. "
            "You MUST call find_available_slots — NEVER make up times. "
            "Present ONLY times from the tool result. When patient picks a time → confirm_booking."
        ),
        "confirmation_mode": "auto",
        "next_conditional_objectives": {
            "confirm_booking": "If patient picked an available time slot",
            "end_warmly": "If patient changes mind or wants front desk help",
        },
    },
    {
        "objective_name": "collect_new_patient_info",
        "objective_prompt": (
            "verify_patient could not find this patient and they want to book. "
            "You ALREADY know their name and DOB from the verify attempt — do NOT ask again. "
            "Only collect what's missing: "
            "'What's a good phone number for you?' "
            "Then: 'Do you have dental insurance? If so, which one?' "
            "Call create_patient with first_name, last_name, dob, phone, and insurance (or 'none'). "
            "Then proceed to offer_booking."
        ),
        "confirmation_mode": "auto",
        "next_required_objective": "offer_booking",
    },
    {
        "objective_name": "confirm_booking",
        "objective_prompt": (
            "Patient picked a time. "
            "If you haven't asked about insurance yet: 'Do you have dental insurance? If so, which one?' "
            "If insurance was already collected (e.g. during new patient registration), skip this question. "
            "Then you MUST call the book_appointment tool. Do NOT say 'booked' until you get the tool result. "
            "NEVER pretend to book — you MUST use the tool. "
            "On success: confirm date/time from the result. On error: direct to front desk."
        ),
        "confirmation_mode": "auto",
        "next_required_objective": "end_warmly",
    },
    {
        "objective_name": "end_warmly",
        "objective_prompt": (
            "Wrap up the conversation warmly and briefly. "
            "If patient was checked in: 'You're all set! Have a seat and we'll call you shortly.' "
            "If patient booked an appointment: 'See you on [date]! Have a great day.' "
            "Otherwise: 'The front desk is right over there if you need anything!' "
            "Keep it brief and friendly."
        ),
        "confirmation_mode": "auto",
    },
]

# ---------------------------------------------------------------------------
# Guardrails — strict behavioral rules
# ---------------------------------------------------------------------------

GUARDRAILS = {
    "name": "dental_kiosk_safety",
    "data": [
        {
            "guardrail_name": "hipaa_privacy",
            "guardrail_prompt": (
                "NEVER reveal any patient information (name, DOB, appointments, balance) "
                "until verify_patient TOOL_RESULT confirms verification. "
                "NEVER read back full phone numbers — only last four digits."
            ),
        },
        {
            "guardrail_name": "no_technical_errors",
            "guardrail_prompt": (
                "NEVER mention technical details to the patient: no error codes, HTTP status, "
                "server, database, API, timeout, or system errors. "
                "If something fails: 'Something's not working on my end. "
                "The front desk can help you right away!'"
            ),
        },
        {
            "guardrail_name": "brevity",
            "guardrail_prompt": (
                "ALWAYS keep responses to 1-2 short sentences, maximum 25 words. "
                "This is a kiosk — patients are standing. Be quick and efficient. "
                "NEVER use bullet points, numbered lists, or any text formatting."
            ),
        },
        {
            "guardrail_name": "stay_on_topic",
            "guardrail_prompt": (
                "You are a dental kiosk information assistant ONLY. Do not discuss topics unrelated "
                "to dental appointments, balance, or clinic information. "
                "If asked about anything else: 'Great question! The front desk team can help with that.'"
            ),
        },
        {
            "guardrail_name": "no_sms",
            "guardrail_prompt": (
                "You CAN check in patients and book appointments using your tools. "
                "You CANNOT send SMS or text messages. If asked: "
                "'The front desk will take care of that for you!' "
                "NEVER offer to send texts or reminders."
            ),
        },
    ],
}

# ---------------------------------------------------------------------------
# Tools — 8 function tools (4 read, 4 write) (no url field — handled via frontend conversation.respond)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "verify_patient",
            "description": "Verify patient identity by full name and date of birth. The system uses fuzzy matching (sounds-like) to find patients even if the name isn't heard perfectly. The screen shows the searched name to the patient. If TOOL_RESULT says 'need_phone', ask for last 4 digits of phone number and call again with phone_last4.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Patient's full name (first and last).",
                    },
                    "dob": {
                        "type": "string",
                        "description": "Date of birth in YYYY-MM-DD format. Convert spoken dates like 'March 15 1985' to '1985-03-15' internally.",
                    },
                    "phone_last4": {
                        "type": "string",
                        "description": "Last 4 digits of phone number. Only needed if previous verify_patient returned 'need_phone' for disambiguation.",
                    },
                },
                "required": ["name", "dob"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_today_appointment",
            "description": "Check if the patient has an appointment TODAY. Usually NOT needed — verify_patient already includes today's appointment. Only call this if the patient asks about today's appointment separately.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "integer",
                        "description": "The verified patient's ID from verify_patient result.",
                    },
                },
                "required": ["patient_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_balance",
            "description": "Get the patient's account balance and insurance estimate. Use when patient asks about their balance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "integer",
                        "description": "The verified patient's ID from verify_patient result.",
                    },
                },
                "required": ["patient_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_appointments",
            "description": "Get list of upcoming future appointments. Use when patient asks about scheduled appointments.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "integer",
                        "description": "The verified patient's ID from verify_patient result.",
                    },
                },
                "required": ["patient_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_in_patient",
            "description": "Check in a patient for their today's appointment. Sets arrival time. Only call AFTER patient is verified AND confirmed they want to check in. Use appointment_id from verify_patient result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {
                        "type": "integer",
                        "description": "The appointment ID from verify_patient or get_today_appointment result.",
                    },
                },
                "required": ["appointment_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_available_slots",
            "description": "Find available appointment times for a given date. Call after patient chooses a date and procedure type. Returns list of available time slots.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "The desired date in YYYY-MM-DD format. Convert spoken dates like 'next Monday' or 'March 15' to this format.",
                    },
                    "procedure_type": {
                        "type": "string",
                        "enum": ["routine_exam_cleaning", "cosmetic", "root_canal", "extraction", "tooth_replacement"],
                        "description": "Type of appointment the patient wants.",
                    },
                },
                "required": ["date", "procedure_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Book an appointment for the patient. Call after patient has chosen a date, time, and procedure type from available slots. Include insurance info if provided.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patient_id": {
                        "type": "integer",
                        "description": "Patient ID from verify_patient or create_patient result.",
                    },
                    "date": {
                        "type": "string",
                        "description": "Appointment date in YYYY-MM-DD format.",
                    },
                    "time": {
                        "type": "string",
                        "description": "Appointment time as shown to patient (e.g., '10:00 AM').",
                    },
                    "procedure_type": {
                        "type": "string",
                        "enum": ["routine_exam_cleaning", "cosmetic", "root_canal", "extraction", "tooth_replacement"],
                        "description": "Type of appointment.",
                    },
                    "insurance_info": {
                        "type": "string",
                        "description": "Insurance provider name if patient has one, or 'none' if no insurance.",
                    },
                    "is_new_patient": {
                        "type": "boolean",
                        "description": "True if patient was just created via create_patient (not in system before).",
                    },
                },
                "required": ["patient_id", "date", "time", "procedure_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_patient",
            "description": "Create a new patient record. Only use when verify_patient could not find the patient and they want to book. Collect first name, last name, DOB, phone, and insurance first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "first_name": {
                        "type": "string",
                        "description": "Patient's first name.",
                    },
                    "last_name": {
                        "type": "string",
                        "description": "Patient's last name.",
                    },
                    "dob": {
                        "type": "string",
                        "description": "Date of birth in YYYY-MM-DD format.",
                    },
                    "phone": {
                        "type": "string",
                        "description": "Patient's phone number.",
                    },
                    "insurance": {
                        "type": "string",
                        "description": "Dental insurance name (e.g. 'Aetna PPO', 'Delta Dental') or 'none' if uninsured.",
                    },
                },
                "required": ["first_name", "last_name", "dob", "phone"],
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Layers — STT hotwords, conversational flow, LLM, TTS
# ---------------------------------------------------------------------------

LAYERS = {
    "stt": {
        "stt_engine": "tavus-advanced",
        "smart_turn_detection": True,
        "participant_pause_sensitivity": "low",
        "participant_interrupt_sensitivity": "low",
        "hotwords": (
            "All Nassau Dental is the clinic name. "
            "Doctor names: Chrisphonte, Ferdman, Kalendarev, Phan, Chowdhury. "
            "Dental terms: cleaning, filling, crown, root canal, implant, "
            "orthodontics, braces, sedation, extraction, TMJ. "
            "Common patient phrases: check me in, check in, yes please, "
            "I'd like, I need, my name is, date of birth, birthday, insurance, "
            "book, appointment, schedule, cleaning, next week, tomorrow. "
            "Common patient names: Ramirez, Salazar, Rodriguez, Gonzalez, Martinez, "
            "Hernandez, Lopez, Garcia, Rivera, Torres, Morales, Reyes, Cruz."
        ),
    },
    "llm": {
        "model": "tavus-gpt-4.1",
        "speculative_inference": True,
        "tools": TOOLS,
    },
    "tts": {
        "tts_engine": "cartesia",
        "tts_emotion_control": True,
    },
}


# ---------------------------------------------------------------------------
# Main — create objectives → guardrails → persona
# ---------------------------------------------------------------------------

async def main():
    init_client()
    try:
        # Step 1: Create objectives
        print("Creating objectives...")
        objectives_id = await create_objectives(OBJECTIVES)
        print(f"  objectives_id: {objectives_id}")

        # Step 2: Create guardrails
        print("Creating guardrails...")
        guardrails_id = await create_guardrails(GUARDRAILS)
        print(f"  guardrails_id: {guardrails_id}")

        # Step 3: Create persona with objectives + guardrails attached
        print("Creating persona...")
        persona_config = {
            "persona_name": "Jenny - Dental Receptionist",
            "system_prompt": SYSTEM_PROMPT,
            "objectives_id": objectives_id,
            "guardrails_id": guardrails_id,
            "layers": LAYERS,
        }

        persona_id = await create_persona(persona_config)

        print("\n" + "=" * 60)
        print("Setup complete!")
        print(f"  objectives_id:  {objectives_id}")
        print(f"  guardrails_id:  {guardrails_id}")
        print(f"  persona_id:     {persona_id}")
        print("\nAdd this to your .env file:")
        print(f"  TAVUS_PERSONA_ID={persona_id}")
        print("=" * 60 + "\n")

    finally:
        await close_client()


if __name__ == "__main__":
    asyncio.run(main())
