"""
Security headers middleware for NBA Stables API.
Adds HTTP security headers to all responses.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# CSP for HTML pages (NBA stats pages with inline styles, Google Fonts, analytics)
PAGE_CSP = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; img-src 'self'; font-src 'self' https://fonts.gstatic.com; connect-src 'self'"

# CSP for API endpoints (JSON only — no scripts, styles, or resources needed)
DEFAULT_CSP = "default-src 'none'; frame-ancestors 'none'"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware that adds security headers to all responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Choose CSP based on route type
        if request.url.path.startswith("/api/"):
            csp = DEFAULT_CSP
        else:
            csp = PAGE_CSP
        response.headers["Content-Security-Policy"] = csp

        return response
