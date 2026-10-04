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
        # Storing None is valid; get returns None, same as a cache miss
        self.cache.set("k", None, ttl_seconds=60)
        result = self.cache.get("k")
        assert result is None

    def test_miss_returns_none(self):
        assert self.cache.get("nonexistent") is None

    def test_miss_on_different_key(self):
        self.cache.set("a", 1, ttl_seconds=60)
        assert self.cache.get("b") is None

    def test_overwrite_updates_value(self):
        self.cache.set("key", "first", ttl_seconds=60)
        self.cache.set("key", "second", ttl_seconds=60)
        assert self.cache.get("key") == "second"

    def test_overwrite_extends_ttl(self):
        with fake_clock() as clock:
            self.cache.set("key", "v", ttl_seconds=1)
            self.cache.set("key", "v", ttl_seconds=60)
            clock.advance(2)
            assert self.cache.get("key") == "v"

    def test_expired_entry_returns_none(self):
        with fake_clock() as clock:
            self.cache.set("key", "value", ttl_seconds=1)
            clock.advance(2)
            assert self.cache.get("key") is None

    def test_expired_entry_removed_from_cache(self):
        with fake_clock() as clock:
            self.cache.set("key", "value", ttl_seconds=1)
            clock.advance(2)
            self.cache.get("key")
            assert "key" not in self.cache._cache

    def test_non_expired_entry_survives(self):
        with fake_clock() as clock:
            self.cache.set("key", "alive", ttl_seconds=60)
            clock.advance(0)
            assert self.cache.get("key") == "alive"

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

    def test_evict_loop_calls_evict_expired(self):
        # Patch sleep to return once then raise to break the infinite loop.
        call_count = [0]
        original_evict = self.cache._evict_expired

        def fake_evict():
            call_count[0] += 1
            original_evict()

        def fake_sleep(_):
            if call_count[0] >= 1:
                raise SystemExit

        with (
            patch("helpers.common.time.sleep", fake_sleep),
            patch.object(self.cache, "_evict_expired", fake_evict),
        ):
            try:
                self.cache._evict_loop()
            except SystemExit:
                pass

        assert call_count[0] >= 1

    def test_background_eviction_removes_expired_entry(self):
        with fake_clock() as clock:
            self.cache.set("stale", "val", ttl_seconds=1)
            clock.advance(2)
            with self.cache._lock:
                self.cache._evict_expired()
            assert "stale" not in self.cache._cache

    def test_background_eviction_keeps_live_entry(self):
        with fake_clock() as clock:
            self.cache.set("stale", "gone", ttl_seconds=1)
            self.cache.set("live", "here", ttl_seconds=60)
            clock.advance(2)
            with self.cache._lock:
                self.cache._evict_expired()
            assert "stale" not in self.cache._cache
            assert self.cache.get("live") == "here"

    def test_maxsize_eviction_drops_oldest_entry(self):
        small = SimpleCache(maxsize=3)
        small.set("a", 1, ttl_seconds=60)
        small.set("b", 2, ttl_seconds=60)
        small.set("c", 3, ttl_seconds=60)
        small.set("d", 4, ttl_seconds=60)
        assert len(small._cache) == 3
        assert small.get("a") is None
        assert small.get("d") == 4

    def test_maxsize_eviction_keeps_short_ttl_entry(self):
        # Eviction goes by write recency, not by soonest expiry.
        small = SimpleCache(maxsize=2)
        small.set("a", 1, ttl_seconds=86400)
        small.set("b", 2, ttl_seconds=86400)
        small.set("live", 3, ttl_seconds=30)
        assert small.get("live") == 3
        assert small.get("a") is None

    def test_maxsize_eviction_treats_rewrite_as_fresh(self):
        small = SimpleCache(maxsize=2)
        small.set("a", 1, ttl_seconds=60)
        small.set("b", 2, ttl_seconds=60)
        small.set("a", "updated", ttl_seconds=60)
        small.set("c", 3, ttl_seconds=60)
        assert small.get("a") == "updated"
        assert small.get("b") is None
        assert small.get("c") == 3


class TestKeyLock:
    def test_same_key_is_serialised(self):
        c = SimpleCache()
        with c.lock("k"):
            assert c._key_locks[hash("k") % c._KEY_LOCK_STRIPES].locked()

    def test_waiter_proceeds_after_timeout(self, monkeypatch):
        c = SimpleCache()
        monkeypatch.setattr(c, "_KEY_LOCK_WAIT", 0.01)
        stripe = c._key_locks[hash("k") % c._KEY_LOCK_STRIPES]
        stripe.acquire()
        try:
            with c.lock("k"):
                pass
            assert stripe.locked()
        finally:
            stripe.release()


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
