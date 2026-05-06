from pathlib import Path
from functools import lru_cache
from typing import Literal

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class WatchdogSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LOOP_WATCHDOG_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Loop Watchdog"
    upstream_base_url: str = "https://api.openai.com"
    upstream_api_key: str | None = None
    upstream_auth_mode: Literal["incoming", "bearer", "x-api-key"] = "incoming"
    upstream_timeout_seconds: float = 180.0

    alert_webhook_url: HttpUrl | None = None
    alert_hmac_secret: str | None = None

    persistence_enabled: bool = True
    persistence_path: Path = Path(".loop_watchdog/state.json")

    recent_window: int = 8
    max_events_per_session: int = 40
    session_ttl_seconds: int = 7200

    pause_score_threshold: float = 4.8
    request_similarity_threshold: float = 0.72
    error_similarity_threshold: float = 0.84
    file_repeat_threshold: int = 3

    repeated_request_weight: float = 1.4
    repeated_error_weight: float = 2.0
    repeated_file_weight: float = 1.8
    oscillation_weight: float = 1.6
    no_progress_weight: float = 1.2

    redact_payloads: bool = True
    max_summary_chars: int = 320
    max_response_chars: int = 240
    provider_header_name: str = Field(
        default="x-api-key",
        description="Used only when upstream_auth_mode is x-api-key.",
    )


@lru_cache(maxsize=1)
def get_settings() -> WatchdogSettings:
    return WatchdogSettings()
