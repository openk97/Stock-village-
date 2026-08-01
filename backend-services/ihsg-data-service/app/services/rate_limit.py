"""
rate_limit.py — Rate limiter ringan untuk endpoint mahal.

FASE 7 (hardening produksi): membatasi frekuensi request per IP pada endpoint
yang berat (screener scan, stock pick, korelasi, wyckoff). Tanpa dependency
baru -- memakai lapisan cache terpusat (MemoryCache/RedisCache), sehingga
begitu Redis diaktifkan, rate limit otomatis terdistribusi antar worker.

Metode: fixed-window sederhana (counter per IP per key; TTL diperbarui tiap
hit = rolling window sederhana). Default sengaja longgar agar tidak mengganggu
penggunaan normal; nilainya bisa diset lewat env (RATE_LIMIT_*).
"""
from fastapi import Request, HTTPException
from app.services.cache import get_cache


def check_rate_limit(request: Request, key: str, max_requests: int, window_seconds: int) -> None:
    """Naikkan counter untuk (key, IP); jika melewati batas -> 429."""
    if max_requests <= 0:
        return  # 0 / negatif = nonaktif
    ip = request.client.host if request.client else "unknown"
    cache_key = f"ratelimit:{key}:{ip}"
    count = get_cache().get(cache_key)
    if count is None:
        get_cache().set(cache_key, 1, window_seconds)
        return
    if count >= max_requests:
        raise HTTPException(
            status_code=429,
            detail="Terlalu banyak permintaan. Silakan tunggu beberapa saat lalu coba lagi.",
        )
    get_cache().set(cache_key, count + 1, window_seconds)
