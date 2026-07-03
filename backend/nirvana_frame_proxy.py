"""ASGI app that proxies all requests to Nirvana WebUI at :8789, stripping frame-blocking headers."""
from __future__ import annotations

import httpx
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.responses import StreamingResponse

NIRVANA_BASE = "http://127.0.0.1:8789"


class NirvanaFrameProxy:
    """ASGI app — proxies every request to :8789, strips CSP/X-Frame-Options."""
    
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        
        path = scope.get("path", "").replace("/nirvana", "", 1) or "/"
        method = scope.get("method", "GET")
        headers = {k.decode(): v.decode() for k, v in scope.get("headers", []) 
                   if k.decode().lower() not in ("host", "connection")}
        headers["host"] = "127.0.0.1:8789"
        
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            try:
                body = b""
                more_body = True
                while more_body:
                    msg = await receive()
                    body += msg.get("body", b"")
                    more_body = msg.get("more_body", False)
                
                resp = await client.request(
                    method, f"{NIRVANA_BASE}{path}", headers=headers, content=body or None
                )
                
                # Strip headers that block iframe embedding
                out_headers = [(k.encode(), v.encode()) for k, v in resp.headers.items()
                               if k.lower() not in (
                                   "content-security-policy",
                                   "content-security-policy-report-only",
                                   "x-frame-options",
                               )]
                
                await send({
                    "type": "http.response.start",
                    "status": resp.status_code,
                    "headers": out_headers,
                })
                await send({
                    "type": "http.response.body",
                    "body": resp.content,
                    "more_body": False,
                })
            except Exception:
                await send({
                    "type": "http.response.start",
                    "status": 502,
                    "headers": [(b"content-type", b"text/plain")],
                })
                await send({
                    "type": "http.response.body",
                    "body": b"Nirvana WebUI not reachable at :8789",
                    "more_body": False,
                })


nirvana_frame_proxy = NirvanaFrameProxy()
