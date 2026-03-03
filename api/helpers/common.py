# Cache TTLs (in seconds)
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

CACHE_TTL = {
    "scoreboard": 30,  # 30 seconds - live scores change frequently
    "boxscores": 60,  # 1 minute
    "leaders": 300,  # 5 minutes
    "standings": 3600,  # 1 hour - doesn't change often
    "player_stats": 30,  # 30 seconds
    "historical": 86400,  # 24 hours - days_offset >= 2 never changes
    "injuries": 7200,  # 2 hours - injury reports don't change often, avoid rate limits
    "trades": 12 * 3600,  # 12 hours
    "season_leaders": 3600,  # 1 hour
}


# Simple in-memory cache
class SimpleCache:
    _EVICT_EVERY = 50

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._call_count = 0
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if time.time() < entry["expires"]:
                    return entry["data"]
                del self._cache[key]
            return None

    def set(self, key: str, data: Any, ttl_seconds: int):
        with self._lock:
            self._cache[key] = {"data": data, "expires": time.time() + ttl_seconds}
            self._call_count += 1
            if self._call_count >= self._EVICT_EVERY:
                self._evict_expired()
                self._call_count = 0

    def _evict_expired(self):
        now = time.time()
        expired = [k for k, v in self._cache.items() if now >= v["expires"]]
        for k in expired:  # pragma: no cover
            del self._cache[k]

    def clear(self):
        with self._lock:
            self._cache.clear()


# Shared singleton instances
cache = SimpleCache()
executor = ThreadPoolExecutor(max_workers=10)
STATS_PROXY = os.environ.get("STATS_PROXY", None)
