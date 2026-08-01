"""
market.py — Domain: data pasar agregat (sektor heatmap, marquee makro, breadth).

CLEAN ARCHITECTURE: dipisah dari god-class scraper.py. Hanya bergantung pada
provider quote (quotes.py) & konstanta screener (LIQUID_UNIVERSE). Tidak tahu
apa pun tentang HTTP/presentation.
"""
import yfinance as yf
import pandas as pd
from typing import List, Dict, Any

from app.services.cache import get_cache, TTL
from app.services.quotes import get_stock_quotes

import yfinance as yf
import pandas as pd
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models import IHSGHistory, NewsArticle, SectorPerformance
from app.services import goapi_provider
from app.services.goapi_provider import GoApiUnavailable

# FASE 1 REFACTOR: seluruh cache kini lewat SATU lapisan terpusat
# (app/services/cache.py) dengan kebijakan TTL terpusat & thread-safe.
# Nilai TTL & perilaku stale-fallback dipertahankan identik dengan sebelumnya.
from app.services.cache import get_cache, TTL, lock_for

# ---------------------------------------------------------------------------
# Basket 11 SEKTOR RESMI IDX -- SATU SUMBER KEBENARAN sektor di backend.
# Konstituen = fakta keanggotaan sektor; harga diambil RIIL dari Yahoo Finance.
# Dipakai untuk: (1) heatmap sektor (rata-rata % konstituen), dan (2) diturunkan
# menjadi STOCK_SECTOR_MAP untuk basket peer korelasi (FASE 5 dedup -- sebelumnya
# ada 2 struktur terpisah yang bisa divergen, mis. ASII & WIFI beda sektor).
# corr_label mempertahankan label lama yang dipakai korelasi.
# ---------------------------------------------------------------------------
SECTOR_BASKETS: Dict[str, Dict[str, Any]] = {
"IDXFIN":    {"name": "1. Finansial (IDXFIN)", "corr_label": "Sektor Keuangan", "stocks": ["BBCA","BBRI","BMRI","BBNI","BRIS","BDMN","BBTN","ARTO"]},
"IDXINFRA":  {"name": "2. Infrastruktur (IDXINFRA)", "corr_label": "Sektor Infrastruktur", "stocks": ["TLKM","PGAS","JSMR","EXCL","ISAT","WIKA","ADHI"]},
"IDXENERGY": {"name": "3. Energi (IDXENERGY)", "corr_label": "Sektor Energi", "stocks": ["ADRO","PTBA","ITMG","HRUM","MEDC","BUMI","AKRA"]},
"IDXBASIC":  {"name": "4. Barang Baku (IDXBASIC)", "corr_label": "Sektor Barang Baku", "stocks": ["MDKA","ANTM","INCO","TPIA","SMGR","BRPT","INKP","AMMN"]},
"IDXNONCYC": {"name": "5. Konsumer Primer (IDXNONCYC)", "corr_label": "Sektor Konsumer Primer", "stocks": ["UNVR","ICBP","INDF","CPIN","GGRM","HMSP","MYOR","SIDO"]},
"IDXCYCLIC": {"name": "6. Konsumer Non-Primer (IDXCYCLIC)", "corr_label": "Sektor Konsumer Non-Primer", "stocks": ["MAPA","MAPI","ACES","ERAA","SCMA","MNCN"]},
"IDXHEALTH": {"name": "7. Kesehatan (IDXHEALTH)", "corr_label": "Sektor Kesehatan", "stocks": ["KLBF","MIKA","HEAL","PRDA","SILO"]},
"IDXINDUST": {"name": "8. Industri (IDXINDUST)", "corr_label": "Sektor Perindustrian", "stocks": ["UNTR","ASII","AALI","HEXA"]},
"IDXPROPERT":{"name": "9. Properti (IDXPROPERT)", "corr_label": "Sektor Properti", "stocks": ["BSDE","PWON","SMRA","CTRA","LPKR","APLN"]},
"IDXTECHNO": {"name": "10. Teknologi (IDXTECHNO)", "corr_label": "Sektor Teknologi", "stocks": ["GOTO","BUKA","EMTK","WIFI"]},
"IDXTRANS":  {"name": "11. Transportasi (IDXTRANS)", "corr_label": "Sektor Transportasi", "stocks": ["ASSA","BIRD","SMDR","TMAS"]},
}

# Ticker makro/komoditas/global untuk marquee atas (semua tersedia di Yahoo).
MARQUEE_TICKERS = [
{"key": "usdidr", "label": "USD/IDR", "ticker": "USDIDR=X"},
{"key": "n225", "label": "NIKKEI 225", "ticker": "^N225"},
{"key": "hsi", "label": "HANG SENG", "ticker": "^HSI"},
{"key": "sti", "label": "STI INDEX", "ticker": "^STI"},
{"key": "dji", "label": "DOW JONES", "ticker": "^DJI"},
{"key": "spx", "label": "S&P 500", "ticker": "^GSPC"},
{"key": "ixic", "label": "NASDAQ", "ticker": "^IXIC"},
{"key": "gold", "label": "EMAS (XAU)", "ticker": "GC=F"},
{"key": "coal", "label": "BATU BARA", "ticker": "MTF=F"},
{"key": "brent", "label": "BRENT CRUDE", "ticker": "BZ=F"},
{"key": "cpo", "label": "CPO SAWIT", "ticker": "CPO=F"},
{"key": "copper", "label": "COPPER (LME)", "ticker": "HG=F"},
{"key": "us10y", "label": "US 10Y BOND", "ticker": "^TNX"},
]


def get_sector_performance() -> List[Dict[str, Any]]:
    """Performa 11 sektor IDX = rata-rata % perubahan harga RIIL konstituen
    (proksi jujur, bukan indeks resmi BEI). Fallback None per sektor bila
    semua konstituen gagal diambil."""
    cached = get_cache().get("market:sectors")
    if cached is not None:
        return cached

    # PERF: ambil SEMUA konstituen unik dalam SATU batch quote (sebelumnya
    # 11 panggilan batch terpisah per sektor). Hasil identik: rata-rata %
    # perubahan harga riil konstituen per sektor.
    all_symbols = sorted({s for info in SECTOR_BASKETS.values() for s in info["stocks"]})
    quotes = get_stock_quotes(all_symbols)
    by_symbol = {q["symbol"]: q.get("change_percent") for q in quotes}

    result = []
    for code, info in SECTOR_BASKETS.items():
        changes = [
            by_symbol[s] for s in info["stocks"]
            if isinstance(by_symbol.get(s), (int, float))
        ]
        if changes:
            avg = round(sum(changes) / len(changes), 2)
        else:
            avg = None
        result.append({
            "sector_code": code,
            "sector_name": info["name"],
            "change_percent": avg,
            "constituents": len(info["stocks"]),
            "with_data": len(changes),
            "source": "yahoo_finance",
        })
    get_cache().set("market:sectors", result, TTL.MARKET)
    return result

def get_macro_quotes() -> List[Dict[str, Any]]:
    """Quote RIIL ticker makro/komoditas/global untuk marquee atas."""
    cached = get_cache().get("market:marquee")
    if cached is not None:
        return cached

    tickers = [t["ticker"] for t in MARQUEE_TICKERS]
    result = []
    try:
        df = yf.download(tickers=" ".join(tickers), period="5d", interval="1d",
                         progress=False, threads=True, group_by="ticker")
        for t in MARQUEE_TICKERS:
            key = t["ticker"]
            try:
                if isinstance(df.columns, pd.MultiIndex) and key in df.columns.get_level_values(0):
                    sub = df[key]
                else:
                    sub = df
                close = sub["Close"].dropna()
                if len(close) >= 2:
                    last = float(close.iloc[-1])
                    prev = float(close.iloc[-2])
                    chg = round((last - prev) / prev * 100, 2) if prev else 0.0
                    result.append({"key": t["key"], "label": t["label"], "value": round(last, 2),
                                   "change_pct": chg, "source": "yahoo_finance"})
                elif len(close) == 1:
                    result.append({"key": t["key"], "label": t["label"], "value": round(float(close.iloc[-1]), 2),
                                   "change_pct": None, "source": "yahoo_finance"})
            except Exception as e:
                print(f"[marquee] {key} gagal: {e}")
    except Exception as e:
        print(f"[marquee] batch gagal: {e}")

    get_cache().set("market:marquee", result, TTL.MARKET)
    return result

def get_market_breadth() -> Dict[str, Any]:
    """Market breadth (naik/tetap/turun) dihitung dari quote RIIL universe
    saham likuid -- proksi jujur, bukan seluruh bursa."""
    from app.services.screener import LIQUID_UNIVERSE
    cached = get_cache().get("market:breadth")
    if cached is not None:
        return cached

    quotes = get_stock_quotes(LIQUID_UNIVERSE)
    advances = sum(1 for q in quotes if (q.get("change_percent") or 0) > 0)
    declines = sum(1 for q in quotes if (q.get("change_percent") or 0) < 0)
    unchanged = sum(1 for q in quotes if q.get("change_percent") == 0)
    data = {
        "advances": advances,
        "unchanged": unchanged,
        "declines": declines,
        "scanned": len(quotes),
        "source": "yahoo_finance",
    }
    get_cache().set("market:breadth", data, TTL.MARKET)
    return data
