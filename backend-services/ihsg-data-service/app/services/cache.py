"""
cache.py — Lapisan cache terpusat untuk ihsg-data-service.

FASE 1 REFACTOR (ARCHITECTURE_REVIEW.md): menggantikan 4 dict cache terpisah
(_QUOTE_CACHE, _PROFILE_CACHE, _MARKET_CACHE, _HISTORY_CACHE) dengan SATU
interface + SATU kebijakan TTL. Perilaku dipertahankan persis:
  - TTL yang sama dengan sebelumnya (20s quote, 600s profile/history, 60s market)
  - allow_stale=True mempertahankan perilaku "pakai nilai basi saat fetch gagal"
  - Thread-safe dengan lock (sebelumnya dict polos tanpa lock)

Backend Redis siap ditambahkan (RedisCache) tanpa mengubah pemanggil; aktif
lewat config CACHE_BACKEND=redis (belum diaktifkan, default memory).
"""
import threading
import time
import json
import logging
from typing import Any, Dict, Optional

log = logging.getLogger("cache")


class MemoryCache:
    """Cache in-memory dengan TTL. Nilai bisa objek apa pun (termasuk DataFrame)."""

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str, allow_stale: bool = False) -> Optional[Any]:
        """Ambil nilai jika masih fresh. allow_stale=True mengembalikan nilai
        basi -- dipakai untuk fallback saat fetch gagal (mereplikasi perilaku
        cache lama). Entri yang basi TIDAK dihapus di sini, agar nilai basi
        tetap bisa diambil setelah fresh-check gagal (urutan pemanggilan khas
        stale-fallback: get() -> None, lalu get(allow_stale=True))."""
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            fresh = (time.time() - entry["_at"]) < entry["_ttl"]
            if fresh or allow_stale:
                return entry["value"]
            return None

    def set(self, key: str, value: Any, ttl: int) -> None:
        with self._lock:
            self._store[key] = {"value": value, "_at": time.time(), "_ttl": ttl}

    def increment(self, key: str, ttl: int, delta: int = 1) -> int:
        """Increment ATOMIK di bawah satu lock. BUG FIX produksi: pola lama
        (get lalu set terpisah) adalah TOCTOU race -- terbukti kehilangan 86%
        increment di bawah konkurensi, sehingga rate limiter bisa dilewati.
        Key baru/expired dimulai dari `delta` (bukan 0+delta), agar pemanggil
        bisa deteksi "hit pertama" via nilai == delta."""
        with self._lock:
            now = time.time()
            entry = self._store.get(key)
            if entry and (now - entry["_at"]) < entry["_ttl"]:
                new = entry["value"] + delta
            else:
                new = delta
            self._store[key] = {"value": new, "_at": now, "_ttl": ttl}
            return new

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)


class RedisCache:
    """Backend produksi (FASE 7): cache terdistribusi antar worker via Redis.

    Nilai harus JSON-serializable (quote/profile/market/news/counter rate-limit
    aman). Nilai non-serializable (mis. DataFrame riwayat harga) TIDAK di-cache
    di Redis -- dilewati dengan log, lalu pemanggil tetap memakai jalur fetch
    biasa (graceful degradation, tidak pernah crash).

    Catatan: allow_stale tidak didukung di Redis (TTL dihapus otomatis oleh
    Redis); untuk nilai basi, pertahankan key terpisah 'last' yang tanpa TTL.
    """

    def __init__(self, url: str) -> None:
        import redis  # lazy import: wajib hanya saat backend=redis
        self._r = redis.from_url(url, decode_responses=False)

    def get(self, key: str, allow_stale: bool = False) -> Optional[Any]:
        raw = self._r.get(key)
        if raw is None and allow_stale:
            raw = self._r.get(f"{key}:last")
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def set(self, key: str, value: Any, ttl: int) -> None:
        try:
            payload = json.dumps(value)
        except (TypeError, ValueError):
            log.warning("[redis-cache] nilai tidak JSON-serializable, dilewati: %s", key)
            return
        self._r.set(key, payload, ex=ttl)
        # simpan "nilai terakhir" tanpa TTL untuk allow_stale
        try:
            self._r.set(f"{key}:last", payload)
        except Exception:
            pass

    def delete(self, key: str) -> None:
        self._r.delete(key)
        self._r.delete(f"{key}:last")

    def increment(self, key: str, ttl: int, delta: int = 1) -> int:
        """Increment ATOMIK server-side (INCR + EXPIRE). BUG FIX: pola
        get+set lama = 2 round-trip Redis = jendela race lebar (rate limiter
        bisa dilewati). INCR atomik di Redis; EXPIRE hanya saat key baru
        (nilai == delta) agar TTL tidak di-refresh terus oleh request normal.
        Jika Redis bermasalah: FAIL-OPEN (kembalikan 0 = di bawah batas) +
        log -- memblokir semua user saat Redis down lebih buruk daripada
        melonggarkan limit sementara."""
        try:
            val = int(self._r.incr(key, delta))
            if val == delta:  # key baru dibuat oleh operasi ini
                self._r.expire(key, ttl)
            return val
        except Exception as e:
            log.warning("[redis-cache] increment gagal (fail-open): %s", e)
            return 0


class TTL:
    """Kebijakan TTL terpusat (nilai identik dengan sebelumnya)."""
    QUOTE = 20
    PROFILE = 600
    MARKET = 60
    HISTORY = 600
    NEWS = 180


_cache: Any = None


def get_cache() -> Any:
    """Singleton cache. Backend dipilih lewat config CACHE_BACKEND:
    "memory" (default) atau "redis". Pemanggil tidak perlu tahu backend-nya."""
    global _cache
    if _cache is None:
        from app.config import settings
        if settings.cache_backend == "redis":
            try:
                _cache = RedisCache(settings.redis_url)
            except Exception as e:  # Redis tidak tersedia -> degradasi ke memory
                log.warning("[cache] Redis tidak tersedia, fallback ke memory: %s", e)
                _cache = MemoryCache()
        else:
            _cache = MemoryCache()
    return _cache
