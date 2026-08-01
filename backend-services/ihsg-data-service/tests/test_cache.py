"""Unit test: lapisan cache terpusat (app/services/cache.py)."""
import time
from app.services.cache import MemoryCache, TTL


def test_set_get():
    c = MemoryCache()
    c.set("a", {"x": 1}, TTL.QUOTE)
    assert c.get("a") == {"x": 1}


def test_ttl_expiry():
    c = MemoryCache()
    c.set("a", 1, 1)          # TTL 1 detik
    assert c.get("a") == 1
    time.sleep(1.1)
    assert c.get("a") is None  # expired -> hilang


def test_allow_stale():
    c = MemoryCache()
    c.set("a", "stale", 1)
    time.sleep(1.1)
    assert c.get("a") is None
    assert c.get("a", allow_stale=True) == "stale"  # fallback nilai basi


def test_delete():
    c = MemoryCache()
    c.set("a", 1, TTL.PROFILE)
    c.delete("a")
    assert c.get("a") is None


def test_ttl_constants_sane():
    assert TTL.QUOTE == 20
    assert TTL.PROFILE == 600
    assert TTL.MARKET == 60
    assert TTL.HISTORY == 600
    assert TTL.NEWS == 180
