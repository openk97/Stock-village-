"""
rate_limit.py — Rate limiter ringan untuk endpoint mahal.

FASE 7 (hardening produksi): membatasi frekuensi request per IP pada endpoint
yang berat (screener scan, stock pick, korelasi, wyckoff). Tanpa dependency
baru -- memakai lapisan cache terpusat (MemoryCache/RedisCache), sehingga
begitu Redis diaktifkan, rate limit otomatis terdistribusi antar worker.

Metode: rolling window sederhana (counter atomik per IP per key; TTL diperbarui
tiap hit). Default sengaja longgar agar tidak mengganggu penggunaan normal;
nilainya bisa diset lewat env (RATE_LIMIT_*).

BUG FIX produksi: counter dinaikkan lewat cache.increment() yang ATOMIK
(MemoryCache: satu lock; RedisCache: INCR server-side). Pola lama get-then-set
terbukti TOCTOU race di bawah konkurensi (kehilangan 86% increment), sehingga
rate limit bisa dilewati saat trafik tinggi.
"""
from fastapi import Request, HTTPException
from app.services.cache import get_cache


def _client_ip(request: Request, trust_proxy: bool) -> str:
    """IP klien. Di belakang reverse proxy (nginx/gateway), request.client
    selalu alamat gateway sehingga SEMUA user berbagi satu bucket -- itu
    membuat rate limit tidak adil & bisa memblokir satu kantor/ISP bersama.
    trust_proxy=True memakai X-Forwarded-For (IP pertama = klien asli).
    Jangan aktifkan kecuali aplikasi benar-benar di belakang proxy yang
    di-trust (kalau tidak, header bisa dipalsukan klien)."""
    if trust_proxy:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            first = xff.split(",")[0].strip()
            if first:
                return first
    return request.client.host if request.client else "unknown"


def check_rate_limit(request: Request, key: str, max_requests: int,
                     window_seconds: int, trust_proxy: bool = False) -> None:
    """Naikkan counter atomik untuk (key, IP); jika melewati batas -> 429."""
    if max_requests <= 0:
        return  # 0 / negatif = nonaktif
    ip = _client_ip(request, trust_proxy)
    cache_key = f"ratelimit:{key}:{ip}"
    count = get_cache().increment(cache_key, window_seconds, 1)
    if count > max_requests:
        raise HTTPException(
            status_code=429,
            detail="Terlalu banyak permintaan. Silakan tunggu beberapa saat lalu coba lagi.",
        )
