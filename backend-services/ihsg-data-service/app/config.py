"""
config.py — Satu sumber kebenaran untuk konfigurasi ihsg-data-service.

QUICK WIN (refactor aman, TANPA dependency baru): semua env dibungkus di satu
objek Settings dengan nilai default yang IDENTIK dengan yang sebelumnya
dibaca os.getenv di masing-masing file. Memudahkan audit & pemeliharaan,
tanpa mengubah perilaku.
"""
import os


class Settings:
    # DB
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./ihsg.db")
    db_pool_size: int = int(os.getenv("DB_POOL_SIZE", "10"))
    db_max_overflow: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))

    # GoAPI.io (opsional; jika kosong, provider dilewati -> fallback Yahoo)
    goapi_api_key: str = os.getenv("GOAPI_API_KEY", "")
    goapi_base_url: str = os.getenv("GOAPI_BASE_URL", "https://api.goapi.io")

    # News (RSS Yahoo + Google)
    news_cache_ttl: int = int(os.getenv("NEWS_CACHE_TTL", "180"))
    news_limit: int = int(os.getenv("NEWS_LIMIT", "8"))

    # Screener (universe likuid default)
    screener_universe_limit: int = int(os.getenv("SCREENER_UNIVERSE_LIMIT", "80"))

    # Cache backend: "memory" (default) | "redis" (distribusi antar worker)
    cache_backend: str = os.getenv("CACHE_BACKEND", "memory")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Rate limit (0 = nonaktif). Default longgar agar tidak mengganggu normal.
    rate_limit_scan: int = int(os.getenv("RATE_LIMIT_SCAN", "15"))        # per menit, endpoint scan/stockpick
    rate_limit_analyze: int = int(os.getenv("RATE_LIMIT_ANALYZE", "40"))  # per menit, analyze 1 saham
    rate_limit_correlation: int = int(os.getenv("RATE_LIMIT_CORRELATION", "20"))
    rate_limit_market: int = int(os.getenv("RATE_LIMIT_MARKET", "30"))
    rate_limit_wyckoff: int = int(os.getenv("RATE_LIMIT_WYCKOFF", "20"))
    rate_limit_window: int = int(os.getenv("RATE_LIMIT_WINDOW", "60"))    # detik
    # Aktifkan hanya jika aplikasi di belakang reverse proxy yang di-trust
    # (nginx/gateway) -- memakai IP asli dari X-Forwarded-For, bukan IP gateway.
    rate_limit_trust_proxy: bool = os.getenv("RATE_LIMIT_TRUST_PROXY", "").lower() in ("1", "true", "yes", "on")

    # CORS
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")


settings = Settings()
