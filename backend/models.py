"""Pydantic request/response models for the dental kiosk API."""

from typing import Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Tavus tool webhook (incoming from Tavus)
# ---------------------------------------------------------------------------

class ToolWebhookRequest(BaseModel):
    """Request body sent by Tavus when calling a tool webhook."""
    conversation_id: str
    tool_name: str
    properties: dict  # Tavus sends tool args under "properties"


# ---------------------------------------------------------------------------
# Tool response (returned to Tavus)
# ---------------------------------------------------------------------------

class ToolResponse(BaseModel):
    """Wrapper returned to Tavus from every tool webhook."""
    result: dict


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

class SessionStartRequest(BaseModel):
    """Optional request body for session start (language preference, etc.)."""
    language: str = "en"


class SessionStartResponse(BaseModel):
    """Returned to the frontend after creating a Tavus conversation."""
    conversation_id: str
    conversation_url: str


class SessionEndRequest(BaseModel):
    """Request body for ending a session."""
    conversation_id: str


# ---------------------------------------------------------------------------
# Manual check-in (staff sidebar)
# ---------------------------------------------------------------------------

class ManualSearchRequest(BaseModel):
    """Staff sidebar search by last name and/or DOB."""
    last_name: Optional[str] = None
    dob: Optional[str] = None


class CheckinRequest(BaseModel):
    """Mark an appointment as arrived."""
    appointment_id: int
