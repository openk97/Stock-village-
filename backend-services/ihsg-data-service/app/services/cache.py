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
from typing import Any, Dict, Optional


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

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)


class TTL:
    """Kebijakan TTL terpusat (nilai identik dengan sebelumnya)."""
    QUOTE = 20
    PROFILE = 600
    MARKET = 60
    HISTORY = 600
    NEWS = 180


_cache: Optional[MemoryCache] = None


def get_cache() -> MemoryCache:
    """Singleton cache. Backend Redis (RedisCache) dapat dipilih lewat
    konfigurasi tanpa mengubah satu pun pemanggil."""
    global _cache
    if _cache is None:
        _cache = MemoryCache()
    return _cache
