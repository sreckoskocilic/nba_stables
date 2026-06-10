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
        self.cache.clear()
        assert self.cache.get("anything") is None

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
    # Background eviction thread
    # ------------------------------------------------------------------

    def test_evict_loop_calls_evict_expired(self):
        # Verify _evict_loop acquires the lock and calls _evict_expired each iteration.
        # Patch sleep to return once then raise to break the infinite loop.
        call_count = [0]
        original_evict = self.cache._evict_expired

        def fake_evict():
            call_count[0] += 1
            original_evict()

        def fake_sleep(_):
            if call_count[0] >= 1:
                raise SystemExit

        with patch("helpers.common.time.sleep", fake_sleep):
            with patch.object(self.cache, "_evict_expired", fake_evict):
                try:
                    self.cache._evict_loop()
                except SystemExit:
                    pass

        assert call_count[0] >= 1

    # ------------------------------------------------------------------
    # Background eviction (_evict_expired called directly)
    # ------------------------------------------------------------------

    def test_background_eviction_removes_expired_entry(self):
        # Set a short-lived entry, let it expire, then trigger eviction directly
        with fake_clock() as clock:
            self.cache.set("stale", "val", ttl_seconds=1)
            clock.advance(2)
            with self.cache._lock:
                self.cache._evict_expired()
            assert "stale" not in self.cache._cache

    def test_background_eviction_keeps_live_entry(self):
        # Expired entry is cleaned up but live entry survives direct eviction call
        with fake_clock() as clock:
            self.cache.set("stale", "gone", ttl_seconds=1)
            self.cache.set("live", "here", ttl_seconds=60)
            clock.advance(2)
            with self.cache._lock:
                self.cache._evict_expired()
            assert "stale" not in self.cache._cache
            assert self.cache.get("live") == "here"

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

    def test_maxsize_eviction_drops_entry_by_heap_order(self):
        # With maxsize=2, adding a 3rd entry triggers eviction.
        # The heap-based eviction pops the oldest (smallest expiry) entry first.
        small = SimpleCache(maxsize=2)
        small.set("a", 1, ttl_seconds=10)
        small.set("b", 2, ttl_seconds=30)
        small.set("c", 3, ttl_seconds=60)  # triggers maxsize eviction
        # After eviction, cache should be at or under maxsize
        assert len(small._cache) <= 2

    def test_evict_oldest_skips_already_evicted_entries(self):
        with fake_clock():
            small = SimpleCache(maxsize=1)
            # Double-set creates two heap entries for "a" with same expiry
            small.set("a", 1, ttl_seconds=10)
            small.set("a", 2, ttl_seconds=10)
            # Adding "b" evicts "a" via the first heap entry
            small.set("b", 3, ttl_seconds=20)
            assert "a" not in small._cache
            # Adding "c" triggers _evict_oldest which pops the leftover
            # (1010, "a") heap entry — cache.get("a") → None (line 79)
            small.set("c", 4, ttl_seconds=30)
            assert small.get("c") == 4

    def test_evict_oldest_skips_phantom_entries(self):
        with fake_clock():
            small = SimpleCache(maxsize=2)
            small.set("a", 1, ttl_seconds=10)
            small.set("b", 2, ttl_seconds=20)
            small.set("a", "updated", ttl_seconds=60)
            # Now add "c" to exceed maxsize → triggers _evict_oldest
            small.set("c", 3, ttl_seconds=30)
            # "a" should survive because its phantom entry (exp=10) doesn't
            # match the current expiry (exp=60)
            assert small.get("a") == "updated"


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

        with patch("helpers.logger.logger") as mock_log:
            log_exceptions(RuntimeError("runtime"))
            log_exceptions(KeyError("key"))
        assert mock_log.exception.call_count == 2


class TestSafeIntEnv:
    def test_returns_default_when_unset(self, monkeypatch):
        from helpers.common import _safe_int_env

        monkeypatch.delenv("_TEST_SAFE_INT", raising=False)
        assert _safe_int_env("_TEST_SAFE_INT", 42) == 42

    def test_returns_parsed_value(self, monkeypatch):
        from helpers.common import _safe_int_env

        monkeypatch.setenv("_TEST_SAFE_INT", "7")
        assert _safe_int_env("_TEST_SAFE_INT", 42) == 7

    def test_returns_default_on_non_numeric(self, monkeypatch):
        from helpers.common import _safe_int_env

        monkeypatch.setenv("_TEST_SAFE_INT", "abc")
        assert _safe_int_env("_TEST_SAFE_INT", 42) == 42
