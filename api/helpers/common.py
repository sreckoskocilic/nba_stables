# Cache TTLs (in seconds)
import time
from typing import Any, Dict, Optional

from termcolor import colored

CACHE_TTL = {
    "scoreboard": 30,  # 30 seconds - live scores change frequently
    "boxscores": 60,  # 1 minute
    "leaders": 300,  # 5 minutes
    "standings": 3600,  # 1 hour - doesn't change often
    "player_stats": 30,  # 30 seconds
    "historical": 86400,  # 24 hours - days_offset >= 2 never changes
    "injuries": 7200,  # 2 hours - injury reports don't change often, avoid rate limits
}

# Simple in-memory cache
class SimpleCache:
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            entry = self._cache[key]
            if time.time() < entry["expires"]:
                return entry["data"]
            del self._cache[key]
        return None

    def set(self, key: str, data: Any, ttl_seconds: int):
        self._cache[key] = {"data": data, "expires": time.time() + ttl_seconds}

    def clear(self):
        self._cache.clear()

def rgc(statval: list) -> list:
    return [colored(item, "light_green") for item in statval]


def bgc(statval: list) -> list:
    return [colored(item, "light_blue") for item in statval]