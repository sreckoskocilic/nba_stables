"""Unit tests for helpers/common.py — SimpleCache and helpers/logger.py."""

from contextlib import contextmanager
from unittest.mock import patch

from helpers.common import SimpleCache


@contextmanager
def fake_clock(start=1000.0):
    """Patch helpers.common.time.time with a steppable fake clock."""
    t = [start]

    def now():
        return t[0]

    def advance(dt):
        t[0] += dt

    now.advance = advance
    with patch("helpers.common.time.time", now):
        yield now


class TestSimpleCache:
    def setup_method(self):
        self.cache = SimpleCache()

    # ------------------------------------------------------------------
    # Basic set / get
    # ------------------------------------------------------------------

    def test_set_and_get_dict(self):
        self.cache.set("key", {"data": 1}, ttl_seconds=60)
        assert self.cache.get("key") == {"data": 1}

    def test_set_and_get_list(self):
        self.cache.set("k", [1, 2, 3], ttl_seconds=60)
        assert self.cache.get("k") == [1, 2, 3]

    def test_set_and_get_string(self):
        self.cache.set("k", "hello", ttl_seconds=60)
        assert self.cache.get("k") == "hello"

    def test_set_and_get_integer(self):
        self.cache.set("k", 42, ttl_seconds=60)
        assert self.cache.get("k") == 42

    def test_set_and_get_none_value(self):
        # Storing None is valid; get should return None (same as a cache miss—
        # callers are expected to handle this)
        self.cache.set("k", None, ttl_seconds=60)
        # None value expires immediately at set time so this is a miss
        # — documenting the current behaviour rather than asserting a "correct" one
        result = self.cache.get("k")
        assert result is None

    # ------------------------------------------------------------------
    # Cache miss
    # ------------------------------------------------------------------

    def test_miss_returns_none(self):
        assert self.cache.get("nonexistent") is None

    def test_miss_on_different_key(self):
        self.cache.set("a", 1, ttl_seconds=60)
        assert self.cache.get("b") is None

    # ------------------------------------------------------------------
    # Overwrite
    # ------------------------------------------------------------------

    def test_overwrite_updates_value(self):
        self.cache.set("key", "first", ttl_seconds=60)
        self.cache.set("key", "second", ttl_seconds=60)
        assert self.cache.get("key") == "second"

    def test_overwrite_extends_ttl(self):
        with fake_clock() as clock:
            self.cache.set("key", "v", ttl_seconds=1)
            self.cache.set("key", "v", ttl_seconds=60)  # refresh
            clock.advance(2)  # past original TTL of 1s
            # Should still be alive because TTL was reset to 60
            assert self.cache.get("key") == "v"

    # ------------------------------------------------------------------
    # Expiry
    # ------------------------------------------------------------------

    def test_expired_entry_returns_none(self):
        with fake_clock() as clock:
            self.cache.set("key", "value", ttl_seconds=1)
            clock.advance(2)
            assert self.cache.get("key") is None

    def test_expired_entry_removed_from_cache(self):
        with fake_clock() as clock:
            self.cache.set("key", "value", ttl_seconds=1)
            clock.advance(2)
            self.cache.get("key")  # triggers eviction
            assert "key" not in self.cache._cache

    def test_non_expired_entry_survives(self):
        with fake_clock() as clock:
            self.cache.set("key", "alive", ttl_seconds=60)
            clock.advance(0)
            assert self.cache.get("key") == "alive"

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------

    def test_clear_removes_all_entries(self):
        self.cache.set("k1", 1, ttl_seconds=60)
        self.cache.set("k2", 2, ttl_seconds=60)
        self.cache.clear()
        assert self.cache.get("k1") is None
        assert self.cache.get("k2") is None

    def test_clear_on_empty_cache_is_safe(self):
        self.cache.clear()  # should not raise

    def test_clear_then_set(self):
        self.cache.set("k", "old", ttl_seconds=60)
        self.cache.clear()
        self.cache.set("k", "new", ttl_seconds=60)
        assert self.cache.get("k") == "new"

    # ------------------------------------------------------------------
    # Multiple independent keys
    # ------------------------------------------------------------------

    def test_multiple_keys_independent(self):
        self.cache.set("a", 1, ttl_seconds=60)
        self.cache.set("b", 2, ttl_seconds=60)
        self.cache.set("c", 3, ttl_seconds=60)
        assert self.cache.get("a") == 1
        assert self.cache.get("b") == 2
        assert self.cache.get("c") == 3

    def test_expire_one_key_leaves_others(self):
        with fake_clock() as clock:
            self.cache.set("short", "gone", ttl_seconds=1)
            self.cache.set("long", "here", ttl_seconds=60)
            clock.advance(2)
            assert self.cache.get("short") is None
            assert self.cache.get("long") == "here"

    # ------------------------------------------------------------------
    # Periodic eviction (_evict_expired via call-count threshold)
    # ------------------------------------------------------------------

    def test_periodic_eviction_removes_expired_entry(self):
        # Set a short-lived entry, let it expire, then trigger periodic eviction
        with fake_clock() as clock:
            self.cache.set("stale", "val", ttl_seconds=1)
            clock.advance(2)
            self.cache._call_count = SimpleCache._EVICT_EVERY - 1
            self.cache.get(
                "anything"
            )  # pushes count to threshold → _evict_expired runs
            assert "stale" not in self.cache._cache

    def test_periodic_eviction_keeps_refreshed_entry(self):
        # Overwriting a key leaves a stale heap pointer for the old TTL.
        # When _evict_expired pops that pointer the cache entry has a newer expiry,
        # so it must NOT be deleted (line 62 guard).
        with fake_clock() as clock:
            self.cache.set("key", "old", ttl_seconds=1)
            self.cache.set(
                "key", "new", ttl_seconds=60
            )  # refreshes cache; old heap entry remains
            clock.advance(2)
            self.cache._call_count = SimpleCache._EVICT_EVERY - 1
            self.cache.get("anything")
            assert self.cache.get("key") == "new"

    # ------------------------------------------------------------------
    # Maxsize eviction
    # ------------------------------------------------------------------

    def test_maxsize_eviction_drops_oldest_entry(self):
        # Fill a tiny cache to capacity then add one more entry.
        # The oldest entry should be evicted to stay within maxsize.
        small = SimpleCache(maxsize=3)
        small.set("a", 1, ttl_seconds=60)
        small.set("b", 2, ttl_seconds=60)
        small.set("c", 3, ttl_seconds=60)
        small.set("d", 4, ttl_seconds=60)  # triggers maxsize eviction
        assert len(small._cache) <= 3

    def test_maxsize_eviction_spares_rewritten_key(self):
        # "a" is overwritten, leaving a stale heap entry with ttl=1 (smallest expiry).
        # "b" has ttl=30, sitting between "a"'s stale (1) and valid (60) entries.
        # When eviction pops the stale (t+1, "a") entry, the expires-match guard
        # must skip it rather than deleting "a"'s live data. The loop then pops
        # (t+30, "b") and evicts that instead.
        small = SimpleCache(maxsize=2)
        small.set("a", "old", ttl_seconds=1)  # stale heap entry: (t+1, "a")
        small.set("a", "new", ttl_seconds=60)  # valid heap entry: (t+60, "a")
        small.set("b", 2, ttl_seconds=30)  # heap entry: (t+30, "b")
        small.set("c", 3, ttl_seconds=60)  # triggers eviction
        # Guard must prevent "a" from being deleted via its stale pointer;
        # "b" (next oldest) is evicted instead.
        assert small.get("a") == "new"
        assert len(small._cache) <= 2


class TestLogExceptions:
    def test_calls_logger_exception(self):
        from helpers.logger import log_exceptions

        err = ValueError("boom")
        with patch("helpers.logger.logger") as mock_log:
            log_exceptions(err)
        mock_log.exception.assert_called_once()
        args = mock_log.exception.call_args[0]
        assert args[0] == "%s: %s"
        assert args[1] == "ValueError"
        assert args[2] is err

    def test_accepts_any_exception_type(self):
        from helpers.logger import log_exceptions

        with patch("helpers.logger.logger"):
            log_exceptions(RuntimeError("runtime"))
            log_exceptions(KeyError("key"))
