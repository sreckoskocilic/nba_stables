"""
Security headers middleware for NBA Stables API.
Adds HTTP security headers to all responses.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


# CSP for static pages (soccer, etc.) that need external API access
STATIC_CSP = (
    "default-src 'self' 'unsafe-inline' https://site.api.espn.com https://sports.core.api.espn.com https://fonts.googleapis.com https://fonts.gstatic.com https://cdn.jsdelivr.net; "
    "connect-src https://site.api.espn.com https://sports.core.api.espn.com https://*.Espn.com https://*.service.brightcove.com ws://localhost:* http://localhost:*; "
    "font-src https://fonts.gstatic.com https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
    "style-src-elem 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
    "img-src 'self' data: https:;"
)

# Default CSP for API endpoints
DEFAULT_CSP = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; img-src 'self' data:; font-src 'self' https://fonts.gstatic.com; connect-src 'self'"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware that adds security headers to all responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Use relaxed CSP for static pages that need external API access
        if request.url.path.startswith("/soccer"):
            response.headers["Content-Security-Policy"] = STATIC_CSP
        else:
            response.headers["Content-Security-Policy"] = DEFAULT_CSP

        return response
