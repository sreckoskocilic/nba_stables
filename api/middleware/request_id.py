"""
Request ID Middleware - adds X-Request-ID header to all responses for log correlation.
"""

import contextvars
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware that adds a unique X-Request-ID to each request for correlation."""

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_var.reset(token)
