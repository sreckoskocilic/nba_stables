# Cache TTLs (in seconds)
import atexit
import os
import threading
import time
import heapq
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

CACHE_TTL = {
    "scoreboard": 30,  # 30 seconds - live scores change frequently
    "boxscores": 60,  # 1 minute
    "leaders": 60,  # 1 minute - matches boxscores refresh rate
    "standings": 3600,  # 1 hour - doesn't change often
    "player_stats": 30,  # 30 seconds
    "players": 12 * 3600,  # 12 hours - roster changes are infrequent
    "historical": 86400,  # 24 hours - days_offset >= 2 never changes
    "injuries": 7200,  # 2 hours - injury reports don't change often, avoid rate limits
    "trades": 12 * 3600,  # 12 hours
    "season_leaders": 3600,  # 1 hour
    "playoffs": 60,  # 1 minute - play-in scores and series results change frequently
}


# Simple in-memory cache
class SimpleCache:
    _DEFAULT_MAXSIZE = 2000
    _EVICT_INTERVAL = 60  # seconds between background eviction sweeps
    _MAX_EVICT_PER_OP = 100  # Safety limit to prevent infinite loops

    def __init__(self, maxsize: int = _DEFAULT_MAXSIZE):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._heap = []  # (expires, key)
        self._lock = threading.Lock()
        self._maxsize = maxsize
        self._evict_thread = threading.Thread(target=self._evict_loop, daemon=True)
        self._evict_thread.start()

    def _evict_loop(self):
        while True:
            time.sleep(self._EVICT_INTERVAL)
            with self._lock:
                self._evict_expired()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if time.time() < entry["expires"]:
                return entry["data"]
            # Clean up expired entry
            self._cache.pop(key, None)
            # Mark this key as expired in heap by filtering later
            return None

    def set(self, key: str, data: Any, ttl_seconds: int):
        with self._lock:
            expires = time.time() + ttl_seconds
            self._cache[key] = {"data": data, "expires": expires}
            heapq.heappush(self._heap, (expires, key))

            # Evict expired first, then oldest if still over maxsize
            self._evict_expired()
            if len(self._cache) > self._maxsize:
                self._evict_oldest()

    def _evict_oldest(self):
        """Evict TTL-ordered entries when cache exceeds maxsize."""
        evicted = 0
        while (
            len(self._cache) > self._maxsize
            and self._heap
            and evicted < self._MAX_EVICT_PER_OP
        ):
            _, oldest_key = heapq.heappop(self._heap)
            if oldest_key in self._cache:
                self._cache.pop(oldest_key)
                evicted += 1

    def _evict_expired(self):
        now = time.time()
        # Lazily pop heap entries whose time has passed (O(k log n) vs O(n log n))
        while self._heap and self._heap[0][0] <= now:
            heapq.heappop(self._heap)
        # Remove expired entries from cache dict (handles keys updated after last push)
        expired_keys = [k for k, v in self._cache.items() if v["expires"] <= now]
        for key in expired_keys:
            self._cache.pop(key, None)

    def clear(self):
        with self._lock:
            self._cache.clear()
            self._heap.clear()


# Named constants
DAYS_OFFSET_MIN = 0
DAYS_OFFSET_MAX = 7
SEASON_CUTOFF_MONTH = 10
SEASON_CUTOFF_DAY = 15


def _safe_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Shared singleton instances
cache = SimpleCache()
_DEFAULT_WORKERS = _safe_int_env("EXECUTOR_WORKERS", 10)
executor = ThreadPoolExecutor(
    max_workers=_DEFAULT_WORKERS,
    thread_name_prefix="nba_stats",
)
atexit.register(executor.shutdown, wait=True, cancel_futures=True)
STATS_PROXY = os.environ.get("STATS_PROXY", None)
STATS_TIMEOUT = _safe_int_env("STATS_TIMEOUT", 30)

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
