"""Nirvana WebUI reverse proxy middleware.

Registered as ASGI middleware in main.py. Runs ONLY when no NPU-STACK native
route matches — the middleware checks if a response was already set and only
forwards unmatched paths to the absorbed WebUI at :8789.
"""

from __future__ import annotations

import httpx
from starlette.types import ASGIApp, Receive, Scope, Send


NIRVANA_WEBUI_BASE = "http://127.0.0.1:8789"

# NPU-STACK native path prefixes — NEVER proxy these
NATIVE_PREFIXES: tuple[str, ...] = (
    "/api/nirvana",
    "/api/espnow",
    "/api/esp",
    "/api/flash",
    "/api/training",
    "/api/conversion",
    "/api/benchmark",
    "/api/inference",
    "/api/huggingface",
    "/api/datasets",
    "/api/serving",
    "/api/finetuning",
    "/api/finetune",
    "/api/finetune-publish",
    "/api/scanner",
    "/api/webcam",
    "/api/filebrowser",
    "/api/ingest",
    "/api/assets",
    "/api/gguf-pipeline",
    "/api/nim",
    "/api/cvedia",
    "/api/vitis",
    "/api/models",
    "/api/agent",
    "/api/agent",
    "/api/orchestration",
    "/api/devices",
    "/api/fleet",
    "/api/fleet-command",
    "/api/fleet-agent",
    "/api/civitai",
    "/api/flm",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
    "/api/health",
    "/api/status",
    "/v1",
    "/ws",
)


class NirvanaProxyMiddleware:
    """ASGI middleware that forwards unmatched /api/* paths to the Nirvana WebUI."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")

        # Skip if it's a NPU-STACK native route
        if any(path.startswith(prefix) for prefix in NATIVE_PREFIXES):
            await self.app(scope, receive, send)
            return

        # Forward everything else to the Nirvana WebUI
        await self._proxy_to_webui(scope, receive, send)

    async def _proxy_to_webui(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        query = scope.get("query_string", b"").decode("utf-8", errors="replace")
        target_url = f"{NIRVANA_WEBUI_BASE}{path}"
        if query:
            target_url += f"?{query}"

        method = scope.get("method", "GET")

        # Collect request body
        body = b""
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.request":
                body += message.get("body", b"")
                more_body = message.get("more_body", False)
            elif message["type"] == "http.disconnect":
                return

        # Read request headers (skip host/content-length, rewrite origin for CSRF)
        request_headers: dict[str, str] = {}
        for key, value in scope.get("headers", []):
            decoded_key = key.decode("latin-1").lower()
            if decoded_key not in ("host", "content-length"):
                request_headers[key.decode("latin-1")] = value.decode("latin-1")
        # Rewrite origin to the WebUI's own origin so CSRF checks pass
        request_headers["origin"] = NIRVANA_WEBUI_BASE

        # Forward to Nirvana WebUI
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                upstream_resp = await client.request(
                    method=method,
                    url=target_url,
                    headers=request_headers,
                    content=body or None,
                )

            # Send response status + headers
            # Strip headers that break proxying or iframe embedding
            response_headers = [
                (k.encode("latin-1"), v.encode("latin-1"))
                for k, v in upstream_resp.headers.items()
                if k.lower() not in (
                    "transfer-encoding", "content-encoding", "content-length",
                    "content-security-policy", "content-security-policy-report-only",
                    "x-frame-options",
                )
            ]
            await send({
                "type": "http.response.start",
                "status": upstream_resp.status_code,
                "headers": response_headers,
            })

            # Stream body chunk-by-chunk
            async for chunk in upstream_resp.aiter_bytes(8192):
                await send({
                    "type": "http.response.body",
                    "body": chunk,
                    "more_body": True,
                })
            await send({
                "type": "http.response.body",
                "body": b"",
                "more_body": False,
            })

        except httpx.ConnectError:
            error_body = (
                '{"error":"Nirvana WebUI not reachable",'
                f'"detail":"Is the WebUI running at {NIRVANA_WEBUI_BASE}?"}}'
            ).encode("utf-8")
            await send({
                "type": "http.response.start",
                "status": 502,
                "headers": [(b"content-type", b"application/json")],
            })
            await send({
                "type": "http.response.body",
                "body": error_body,
                "more_body": False,
            })
