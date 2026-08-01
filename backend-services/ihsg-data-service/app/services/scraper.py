"""
scraper.py — FACADE (CLEAN ARCHITECTURE).

Sebelumnya file ini adalah "god class" ~1300 baris yang mencampur: provider
Yahoo/GoAPI, cache, market (sektor/marquee/breadth), korelasi, Wyckoff, seed,
dan history. Sekarang menjadi FACADE TIPIS yang men-delegasi ke modul domain
fokus, agar main.py & test lama TIDAK berubah sama sekali (perilaku identik):

  - quotes.py      : kutipan harga & profil (rantai GoAPI -> Yahoo -> stale)
  - history.py     : riwayat IHSG & realtime
  - market.py      : sektor heatmap, marquee makro, market breadth
  - correlation.py : mesin korelasi (matrix/detail/lead-lag) + konstanta
  - wyckoff.py     : deteksi heuristik Wyckoff/VPA
  - seed.py        : seed data awal (demo)
  - cache.py       : infra cache terpusat   (lihat app/services/cache.py)
  - rate_limit.py  : infra rate limit       (lihat app/services/rate_limit.py)

Kelas IHSGScraper dipertahankan sebagai titik masuk kompatibel; setiap method
adalah delegasi staticmethod ke fungsi domain. Tidak ada logika bisnis di sini.
"""
from app.services.quotes import get_stock_quotes, get_stock_profile
from app.services.history import (
    fetch_and_sync_history,
    get_history_from_db,
    get_realtime_status,
    _get_mock_realtime,
)
from app.services.market import (
    SECTOR_BASKETS,
    MARQUEE_TICKERS,
    get_sector_performance,
    get_macro_quotes,
    get_market_breadth,
)
from app.services.correlation import (
    STOCK_SECTOR_MAP,
    CORRELATION_FACTORS,
    CORRELATION_MATRIX_FACTORS,
    _extract_close_series,
    _interpret_correlation,
    get_correlation_matrix,
    get_correlation_detail,
    _resolve_asset_ticker,
    get_lead_lag_analysis,
    _rolling_mean,
)
from app.services.wyckoff import analyze_wyckoff_vpa
from app.services.seed import seed_initial_data


class IHSGScraper:
    """Facade — delegasi murni ke modul domain (lihat docstring modul)."""

    # Konstanta (re-export untuk kompatibilitas)
    SECTOR_BASKETS = SECTOR_BASKETS
    MARQUEE_TICKERS = MARQUEE_TICKERS
    STOCK_SECTOR_MAP = STOCK_SECTOR_MAP
    CORRELATION_FACTORS = CORRELATION_FACTORS
    CORRELATION_MATRIX_FACTORS = CORRELATION_MATRIX_FACTORS

    # History & realtime
    fetch_and_sync_history = staticmethod(fetch_and_sync_history)
    get_history_from_db = staticmethod(get_history_from_db)
    get_realtime_status = staticmethod(get_realtime_status)
    _get_mock_realtime = staticmethod(_get_mock_realtime)

    # Market
    get_sector_performance = staticmethod(get_sector_performance)
    get_macro_quotes = staticmethod(get_macro_quotes)
    get_market_breadth = staticmethod(get_market_breadth)

    # Quotes & profile
    get_stock_quotes = staticmethod(get_stock_quotes)
    get_stock_profile = staticmethod(get_stock_profile)

    # Korelasi
    _extract_close_series = staticmethod(_extract_close_series)
    _interpret_correlation = staticmethod(_interpret_correlation)
    get_correlation_matrix = staticmethod(get_correlation_matrix)
    get_correlation_detail = staticmethod(get_correlation_detail)
    _resolve_asset_ticker = staticmethod(_resolve_asset_ticker)
    get_lead_lag_analysis = staticmethod(get_lead_lag_analysis)
    _rolling_mean = staticmethod(_rolling_mean)

    # Wyckoff/VPA
    analyze_wyckoff_vpa = staticmethod(analyze_wyckoff_vpa)

    # Seed
    seed_initial_data = staticmethod(seed_initial_data)
