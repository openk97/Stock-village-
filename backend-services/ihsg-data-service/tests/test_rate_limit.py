"""Unit test: increment atomik cache + rate limiter."""
import threading
import time
from types import SimpleNamespace

from app.services.cache import MemoryCache
from app.services.rate_limit import check_rate_limit, _client_ip


def test_increment_basic():
    c = MemoryCache()
    assert c.increment("k", 60) == 1
    assert c.increment("k", 60) == 2
    assert c.increment("k", 60) == 3


def test_increment_after_expiry_restarts():
    c = MemoryCache()
    c.increment("k", 1)
    time.sleep(1.1)
    # expired -> mulai dari delta lagi
    assert c.increment("k", 60) == 1


def test_increment_atomic_under_concurrency():
    """Bukti TOCTOU race hilang: N thread x M increment = N*M tanpa lost update."""
    c = MemoryCache()
    n, per = 8, 200
    threads = [threading.Thread(target=lambda: [c.increment("k", 60) for _ in range(per)]) for _ in range(n)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert c.get("k") == n * per


def test_rate_limit_allows_then_blocks():
    c = MemoryCache()
    # patch get_cache untuk memakai instance sendiri (hindari state global)
    import app.services.rate_limit as rl
    rl.get_cache = lambda: c
    req = SimpleNamespace(client=SimpleNamespace(host="1.2.3.4"), headers={})
    for _ in range(15):
        check_rate_limit(req, "scan", 15, 60)   # 15 request pertama boleh
    try:
        check_rate_limit(req, "scan", 15, 60)   # ke-16 -> 429
        assert False, "harusnya 429"
    except Exception as e:
        assert getattr(e, "status_code", None) == 429


def test_client_ip_proxy_off():
    req = SimpleNamespace(client=SimpleNamespace(host="10.0.0.1"), headers={})
    assert _client_ip(req, False) == "10.0.0.1"


def test_client_ip_proxy_on():
    req = SimpleNamespace(client=SimpleNamespace(host="10.0.0.1"),
                          headers={"x-forwarded-for": "203.0.113.9, 10.0.0.1"})
    assert _client_ip(req, True) == "203.0.113.9"
    assert _client_ip(req, False) == "10.0.0.1"
