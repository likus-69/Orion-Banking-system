"""Custom middleware: request IDs + IP/User-Agent capture for audit logs."""
from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a unique ID to every request and reflect it in the response headers.

    The ID is reused if the client sent `X-Request-ID`, so upstream services
    can trace a request across boundaries.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid
        request.state.current_user = None

        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response
