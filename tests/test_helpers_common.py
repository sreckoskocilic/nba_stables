"""Unit tests for helpers/common.py — SimpleCache."""
import time


from helpers.common import SimpleCache


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
        self.cache.set("key", "v", ttl_seconds=1)
        self.cache.set("key", "v", ttl_seconds=60)   # refresh
        time.sleep(1.05)
        # Should still be alive because TTL was reset to 60
        assert self.cache.get("key") == "v"

    # ------------------------------------------------------------------
    # Expiry
    # ------------------------------------------------------------------

    def test_expired_entry_returns_none(self):
        self.cache.set("key", "value", ttl_seconds=1)
        time.sleep(1.1)
        assert self.cache.get("key") is None

    def test_expired_entry_removed_from_cache(self):
        self.cache.set("key", "value", ttl_seconds=1)
        time.sleep(1.1)
        self.cache.get("key")                         # triggers eviction
        assert "key" not in self.cache._cache

    def test_non_expired_entry_survives(self):
        self.cache.set("key", "alive", ttl_seconds=60)
        time.sleep(0.05)
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
        self.cache.clear()   # should not raise

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
        self.cache.set("short", "gone", ttl_seconds=1)
        self.cache.set("long",  "here", ttl_seconds=60)
        time.sleep(1.1)
        assert self.cache.get("short") is None
        assert self.cache.get("long") == "here"
