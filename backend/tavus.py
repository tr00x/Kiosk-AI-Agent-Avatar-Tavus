"""Tavus CVI API client.

Handles:
- Creating conversations (one per kiosk session)
- Ending conversations
- Creating personas (one-time setup)
- Creating objectives & guardrails (one-time setup)
"""

import logging
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

TAVUS_BASE_URL = "https://tavusapi.com"

# Shared httpx client (initialized in main.py lifespan)
_client: Optional[httpx.AsyncClient] = None


def init_client() -> None:
    """Initialize the shared httpx client."""
    global _client
    _client = httpx.AsyncClient(
        base_url=TAVUS_BASE_URL,
        headers={
            "x-api-key": settings.tavus_api_key,
            "Content-Type": "application/json",
        },
        timeout=30.0,
    )


async def close_client() -> None:
    """Close the shared httpx client."""
    global _client
    if _client:
        await _client.aclose()
        _client = None


GREETINGS = {
    "en": "Hi! Welcome to All Nassau Dental! I'm Emma — I can help you check in real quick. What's your name?",
    "es": "¡Hola! ¡Bienvenido a All Nassau Dental! Soy Emma, puedo ayudarle a registrarse. ¿Cómo se llama?",
    "ru": "Привет! Добро пожаловать в All Nassau Dental! Я Эмма, помогу быстро зарегистрироваться. Как вас зовут?",
}

LANGUAGE_CONTEXT = {
    "en": "The patient speaks English. Communicate in English.",
    "es": "The patient speaks Spanish. Communicate in Spanish (Español). Respond in Spanish throughout the conversation.",
    "ru": "The patient speaks Russian. Communicate in Russian (Русский). Respond in Russian throughout the conversation.",
}

LANGUAGE_PROPERTY = {
    "en": "english",
    "es": "spanish",
    "ru": "russian",
}

CLINIC_CONTEXT = """CLINIC INFO for answering patient questions:
Address: 91 Clinton Street, Hempstead, New York 11550
Phone: (929) 822-4005
Hours: Mon-Thu 9AM-7PM, Fri 9AM-4PM, Sun 9AM-3PM
24/7 Emergency line available
Doctors: Dr. Chrisphonte (General), Dr. Ferdman (Pediatric), Dr. Kalendarev (Endo/Root Canals), Dr. Phan (Implants/IV Sedation), Dr. Chowdhury (Orthodontics)
Services: orthodontics, implants, IV sedation, needle-free dentistry, TMJ, anti-snoring, pediatric, emergency
Insurance: most major accepted, financing available
Parking: street parking on Clinton St
Unknown questions: "Great question! The front desk can help with that."
"""


async def create_conversation(
    persona_id: Optional[str] = None,
    replica_id: Optional[str] = None,
    conversation_name: str = "Kiosk Session",
    language: str = "en",
) -> dict:
    """Create a new Tavus conversation.

    Args:
        language: Session language code (en, es, ru). Sets custom greeting & context.

    Returns:
        {
            "conversation_id": "c_xxx",
            "conversation_url": "https://tavus.daily.co/xxx"
        }
    """
    if _client is None:
        raise RuntimeError("Tavus HTTP client not initialized.")

    custom_greeting = GREETINGS.get(language, GREETINGS["en"])
    lang_context = LANGUAGE_CONTEXT.get(language, LANGUAGE_CONTEXT["en"])
    full_context = CLINIC_CONTEXT + "\n" + lang_context

    payload = {
        "persona_id": persona_id or settings.tavus_persona_id,
        "replica_id": replica_id or settings.tavus_replica_id,
        "conversation_name": conversation_name,
        "custom_greeting": custom_greeting,
        "conversational_context": full_context,
        "properties": {
            "max_call_duration": settings.max_call_duration,
            "participant_left_timeout": settings.participant_left_timeout,
            "language": LANGUAGE_PROPERTY.get(language, "english"),
            "enable_recording": False,
            "apply_greenscreen": False,
        },
    }

    logger.info("Creating Tavus conversation: persona=%s, replica=%s", payload["persona_id"], payload["replica_id"])
    resp = await _client.post("/v2/conversations", json=payload)
    resp.raise_for_status()
    data = resp.json()

    conversation_id = data.get("conversation_id", "")
    conversation_url = data.get("conversation_url", "")

    logger.info("Tavus conversation created: id=%s, url=%s", conversation_id, conversation_url)

    return {
        "conversation_id": conversation_id,
        "conversation_url": conversation_url,
    }


async def end_conversation(conversation_id: str) -> None:
    """End an active Tavus conversation."""
    if _client is None:
        raise RuntimeError("Tavus HTTP client not initialized.")

    logger.info("Ending Tavus conversation: %s", conversation_id)
    resp = await _client.delete(f"/v2/conversations/{conversation_id}")

    if resp.status_code == 404:
        logger.warning("Conversation %s not found (already ended?)", conversation_id)
        return

    resp.raise_for_status()
    logger.info("Tavus conversation ended: %s", conversation_id)


async def create_objectives(objectives_data: list) -> str:
    """Create Tavus objectives (one-time setup).

    Args:
        objectives_data: List of objective dicts (see setup_persona.py).

    Returns:
        The objectives_id string.
    """
    if _client is None:
        raise RuntimeError("Tavus HTTP client not initialized.")

    payload = {"data": objectives_data}
    logger.info("Creating Tavus objectives (%d objectives)", len(objectives_data))
    resp = await _client.post("/v2/objectives", json=payload)
    if resp.status_code != 200:
        logger.error("Objectives API error %d: %s", resp.status_code, resp.text)
    resp.raise_for_status()
    data = resp.json()

    objectives_id = data.get("objectives_id", "")
    logger.info("Tavus objectives created: %s", objectives_id)

    return objectives_id


async def create_guardrails(guardrails_config: dict) -> str:
    """Create Tavus guardrails (one-time setup).

    Args:
        guardrails_config: Dict with "name" and "data" keys (see setup_persona.py).

    Returns:
        The guardrails_id string.
    """
    if _client is None:
        raise RuntimeError("Tavus HTTP client not initialized.")

    logger.info("Creating Tavus guardrails: %s", guardrails_config.get("name", "unnamed"))
    resp = await _client.post("/v2/guardrails", json=guardrails_config)
    if resp.status_code != 200:
        logger.error("Guardrails API error %d: %s", resp.status_code, resp.text)
    resp.raise_for_status()
    data = resp.json()

    guardrails_id = data.get("guardrails_id", "")
    logger.info("Tavus guardrails created: %s", guardrails_id)

    return guardrails_id


async def create_persona(persona_config: dict) -> str:
    """Create a new Tavus persona (one-time setup).

    Args:
        persona_config: Full persona payload (see setup_persona.py).

    Returns:
        The persona_id string.
    """
    if _client is None:
        raise RuntimeError("Tavus HTTP client not initialized.")

    logger.info("Creating Tavus persona: %s", persona_config.get("persona_name", "unnamed"))
    resp = await _client.post("/v2/personas", json=persona_config)
    resp.raise_for_status()
    data = resp.json()

    persona_id = data.get("persona_id", "")
    logger.info("Tavus persona created: %s", persona_id)

    return persona_id
