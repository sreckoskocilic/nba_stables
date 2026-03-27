"""Decorators for route handlers."""

import functools

from fastapi import HTTPException

from helpers.logger import log_exceptions


def route_error_handler(detail: str):
    """Decorator to handle exceptions in route handlers.

    Catches HTTPException and re-raises it (preserves status codes).
    Catches generic Exception, logs via log_exceptions, and raises HTTPException(500).

    Args:
        detail: The detail message for the 500 error response.

    Usage:
        @route_error_handler("Failed to fetch ...")
        async def endpoint_name():
            result = await asyncio.to_thread(_sync)
            return result
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                raise
            except Exception as e:
                log_exceptions(e)
                raise HTTPException(status_code=500, detail=detail)

        return wrapper

    return decorator
