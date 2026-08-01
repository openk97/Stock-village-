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
