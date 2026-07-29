import asyncio
import json
import os

from fastapi import APIRouter, HTTPException

from helpers.common import CACHE_TTL, cache
from helpers.decorators import route_error_handler

router = APIRouter()

CBS_INJURIES_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../static/cbs_injuries.json"
)


@router.get("/api/injuries")
@route_error_handler("Failed to fetch injuries")
async def get_injuries():
    """Get NBA injury report from CBS Sports"""
    cached = cache.get("injuries")
    if cached is not None:
        return cached

    _missing = object()
    _corrupt = object()

    def _sync():
        try:
            with open(CBS_INJURIES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return _missing
        except json.JSONDecodeError:
            return _corrupt

    result = await asyncio.to_thread(_sync)
    if result is _missing:
        raise HTTPException(status_code=503, detail="CBS injuries data not available")
    if result is _corrupt:
        raise HTTPException(status_code=503, detail="CBS injuries data is corrupt")
    cache.set("injuries", result, CACHE_TTL["injuries"])
    return result
