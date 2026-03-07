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

# NBA team ID → (tricode, full name)
TEAMS = {
    1610612737: ("ATL", "Atlanta Hawks"),
    1610612738: ("BOS", "Boston Celtics"),
    1610612751: ("BKN", "Brooklyn Nets"),
    1610612766: ("CHA", "Charlotte Hornets"),
    1610612741: ("CHI", "Chicago Bulls"),
    1610612739: ("CLE", "Cleveland Cavaliers"),
    1610612742: ("DAL", "Dallas Mavericks"),
    1610612743: ("DEN", "Denver Nuggets"),
    1610612765: ("DET", "Detroit Pistons"),
    1610612744: ("GSW", "Golden State Warriors"),
    1610612745: ("HOU", "Houston Rockets"),
    1610612754: ("IND", "Indiana Pacers"),
    1610612746: ("LAC", "LA Clippers"),
    1610612747: ("LAL", "Los Angeles Lakers"),
    1610612763: ("MEM", "Memphis Grizzlies"),
    1610612748: ("MIA", "Miami Heat"),
    1610612749: ("MIL", "Milwaukee Bucks"),
    1610612750: ("MIN", "Minnesota Timberwolves"),
    1610612740: ("NOP", "New Orleans Pelicans"),
    1610612752: ("NYK", "New York Knicks"),
    1610612760: ("OKC", "Oklahoma City Thunder"),
    1610612753: ("ORL", "Orlando Magic"),
    1610612755: ("PHI", "Philadelphia 76ers"),
    1610612756: ("PHX", "Phoenix Suns"),
    1610612757: ("POR", "Portland Trail Blazers"),
    1610612758: ("SAC", "Sacramento Kings"),
    1610612759: ("SAS", "San Antonio Spurs"),
    1610612761: ("TOR", "Toronto Raptors"),
    1610612762: ("UTA", "Utah Jazz"),
    1610612764: ("WAS", "Washington Wizards"),
}
