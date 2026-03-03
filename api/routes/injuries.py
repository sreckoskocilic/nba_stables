import json
import os

from fastapi import APIRouter, HTTPException
from helpers.common import CACHE_TTL, cache
from helpers.logger import log_exceptions

router = APIRouter()

CBS_INJURIES_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../static/cbs_injuries.json"
)


@router.get("/api/injuries")
def get_injuries():
    """Get NBA injury report from CBS Sports"""
    cached = cache.get("injuries")
    if cached:
        return cached

    if not os.path.exists(CBS_INJURIES_FILE):
        raise HTTPException(status_code=503, detail="CBS injuries data not available")
    try:
        with open(CBS_INJURIES_FILE, "r", encoding="utf-8") as f:
            result = json.load(f)
        cache.set("injuries", result, CACHE_TTL["injuries"])
        return result
    except Exception as e:  # pragma: no cover
        log_exceptions(e)
        raise HTTPException(status_code=500, detail=str(e))
