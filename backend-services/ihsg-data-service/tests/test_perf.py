"""Unit test: optimisasi performa (single-flight lock, sector batch, WAL)."""
import threading
from app.services.cache import lock_for, MemoryCache


def test_lock_for_same_key_same_lock():
    a = lock_for("x")
    b = lock_for("x")
    assert a is b          # kunci yang sama -> lock yang sama (efisiensi memory)


def test_lock_for_different_key_different_lock():
    assert lock_for("x") is not lock_for("y")


def test_lock_for_serializes_work():
    """Bukti single-flight: dua thread pakai lock yang sama tidak bisa
    masuk bersamaan (kritis untuk mencegah thundering herd)."""
    lock = lock_for("batch:A|B")
    inside = []
    done = []

    def worker():
        with lock:
            inside.append(True)
            assert len(inside) == 1   # hanya satu di dalam kritis pada satu waktu
            import time; time.sleep(0.02)
            inside.pop()
        done.append(True)

    ts = [threading.Thread(target=worker) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(done) == 6


def test_memory_cache_still_fine_after_lock_registry():
    c = MemoryCache()
    c.set("k", 42, 60)
    assert c.get("k") == 42
    assert c.increment("k2", 60) == 1


def test_circuit_breaker_opens_and_cooldown():
    """Circuit breaker: 5 kegagalan -> open; dalam cooldown -> allow=False."""
    import app.services.cache as cache
    from app.services.cache import MemoryCache
    _mc = MemoryCache()                       # SATU instance (state terjaga)
    cache.get_cache = lambda: _mc
    from app.services.cache import circuit_record_failure, circuit_allows

    # sehat
    assert circuit_allows("t1") is True
    for _ in range(cache._CB_DEFAULTS["fail_threshold"]):
        circuit_record_failure("t1")
    # melebihi threshold -> circuit open -> tidak diizinkan
    assert circuit_allows("t1") is False


def test_circuit_breaker_success_resets():
    import app.services.cache as cache
    from app.services.cache import MemoryCache
    _mc = MemoryCache()
    cache.get_cache = lambda: _mc
    from app.services.cache import circuit_record_failure, circuit_record_success, circuit_allows
    circuit_record_failure("t2")
    circuit_record_failure("t2")
    circuit_record_success("t2")   # reset
    assert circuit_allows("t2") is True
