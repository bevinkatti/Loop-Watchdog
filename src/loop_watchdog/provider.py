from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from .config import WatchdogSettings


class UpstreamProxy:
    def __init__(self, settings: WatchdogSettings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self.transport = transport

    def _build_headers(self, incoming_headers: dict[str, str]) -> dict[str, str]:
        headers = {
            "accept": incoming_headers.get("accept", "application/json"),
            "content-type": incoming_headers.get("content-type", "application/json"),
        }
        auth_mode = self.settings.upstream_auth_mode
        if auth_mode == "incoming" and "authorization" in incoming_headers:
            headers["authorization"] = incoming_headers["authorization"]
        elif auth_mode == "bearer" and self.settings.upstream_api_key:
            headers["authorization"] = f"Bearer {self.settings.upstream_api_key}"
        elif auth_mode == "x-api-key" and self.settings.upstream_api_key:
            headers[self.settings.provider_header_name] = self.settings.upstream_api_key
        return headers

    async def forward_json(
        self,
        path: str,
        payload: dict,
        incoming_headers: dict[str, str],
    ) -> tuple[int, dict[str, str], dict | list | str]:
        async with httpx.AsyncClient(
            base_url=self.settings.upstream_base_url.rstrip("/"),
            timeout=self.settings.upstream_timeout_seconds,
            follow_redirects=True,
            transport=self.transport,
        ) as client:
            response = await client.post(path, json=payload, headers=self._build_headers(incoming_headers))
            parsed: dict | list | str
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                parsed = response.json()
            else:
                parsed = response.text
            return response.status_code, self._response_headers(response), parsed

    async def forward_stream(
        self,
        path: str,
        payload: dict,
        incoming_headers: dict[str, str],
    ) -> tuple[int, dict[str, str], AsyncIterator[bytes]]:
        client = httpx.AsyncClient(
            base_url=self.settings.upstream_base_url.rstrip("/"),
            timeout=self.settings.upstream_timeout_seconds,
            follow_redirects=True,
            transport=self.transport,
        )
        request = client.build_request(
            "POST",
            path,
            json=payload,
            headers=self._build_headers(incoming_headers),
        )
        response = await client.send(request, stream=True)

        async def iterator() -> AsyncIterator[bytes]:
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()
                await client.aclose()

        return response.status_code, self._response_headers(response), iterator()

    @staticmethod
    def _response_headers(response: httpx.Response) -> dict[str, str]:
        allowed = {"content-type", "cache-control", "x-request-id"}
        return {key: value for key, value in response.headers.items() if key.lower() in allowed}
