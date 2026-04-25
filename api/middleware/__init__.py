"""
NBA Stables API Middleware
"""

from .security import SecurityHeadersMiddleware

__all__ = [
    "SecurityHeadersMiddleware",
]
