from __future__ import annotations

import hashlib
import hmac
import json
import logging

import httpx

from .config import WatchdogSettings
from .models import IncidentEnvelope, LoopIncident, WatchdogEvent

logger = logging.getLogger("loop_watchdog.alerting")


class AlertDispatcher:
    def __init__(self, settings: WatchdogSettings) -> None:
        self.settings = settings

    async def dispatch(self, incident: LoopIncident, recent_events: list[WatchdogEvent]) -> None:
        envelope = IncidentEnvelope(incident=incident, recent_events=recent_events)
        payload = envelope.model_dump(mode="json")
        logger.warning(
            "Loop incident detected for session=%s score=%s reasons=%s",
            incident.session_id,
            incident.score,
            "; ".join(incident.reasons),
        )
        if self.settings.alert_webhook_url is None:
            return

        body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        headers = {"content-type": "application/json"}
        if self.settings.alert_hmac_secret:
            digest = hmac.new(
                self.settings.alert_hmac_secret.encode("utf-8"),
                body.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            headers["x-loop-watchdog-signature"] = digest

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    str(self.settings.alert_webhook_url),
                    content=body,
                    headers=headers,
                )
                response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("Failed to deliver loop incident alert for session=%s", incident.session_id)
