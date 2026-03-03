"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration for the dental kiosk backend."""

    # Tavus CVI
    tavus_api_key: str = ""
    tavus_persona_id: str = ""
    tavus_replica_id: str = ""

    # Open Dental MySQL
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "opendental"

    # Backend URL (used in persona webhook URLs)
    backend_url: str = "http://localhost:8000"

    # Twilio (optional, for SMS reminders)
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""

    # CORS
    frontend_url: str = "http://localhost:5173"

    # Session
    max_call_duration: int = 300  # seconds (5 min)
    participant_left_timeout: int = 30  # seconds

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
