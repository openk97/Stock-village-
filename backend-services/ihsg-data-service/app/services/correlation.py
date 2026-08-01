"""
correlation.py — Domain: mesin korelasi (matrix/detail/lead-lag) & konstanta.

CLEAN ARCHITECTURE: dipisah dari god-class scraper.py. STOCK_SECTOR_MAP
diturunkan dari SECTOR_BASKETS (market.py); konstanta faktor korelasi ada di
sini. Murni komputasi data historis Yahoo -- tidak tahu soal HTTP.
"""
import yfinance as yf
import pandas as pd
from typing import List, Dict, Any

from app.services.market import SECTOR_BASKETS

CORRELATION_FACTORS = [
    {"key": "ihsg", "label": "IHSG (Indeks Komposit)", "ticker": "^JKSE", "category": "index"},
    {"key": "usdidr", "label": "Kurs USD/IDR", "ticker": "USDIDR=X", "category": "makro"},
    {"key": "gold", "label": "Emas Dunia (Gold Futures)", "ticker": "GC=F", "category": "komoditas"},
    {"key": "brent", "label": "Minyak Brent", "ticker": "BZ=F", "category": "komoditas"},
    {"key": "coal", "label": "Batu Bara (Coal API2 Rotterdam)", "ticker": "MTF=F", "category": "komoditas"},
    {"key": "cpo", "label": "CPO Malaysia (Proxy Sawit)", "ticker": "CPO=F", "category": "komoditas"},
    {"key": "copper", "label": "Tembaga (Copper)", "ticker": "HG=F", "category": "komoditas"},
    {"key": "dji", "label": "Dow Jones (DJIA)", "ticker": "^DJI", "category": "global"},
    {"key": "ixic", "label": "Nasdaq Composite", "ticker": "^IXIC", "category": "global"},
    {"key": "n225", "label": "Nikkei 225 (Jepang)", "ticker": "^N225", "category": "global"},
    {"key": "hsi", "label": "Hang Seng (Hong Kong)", "ticker": "^HSI", "category": "global"},
]

# Faktor inti (subset) dipakai khusus untuk tampilan Matrix (banyak saham
# sekaligus) supaya jumlah ticker yang di-download dalam 1 batch tetap wajar.
CORRELATION_MATRIX_FACTORS = [
    {"key": "ihsg", "label": "IHSG", "ticker": "^JKSE"},
    {"key": "usdidr", "label": "Kurs USD/IDR", "ticker": "USDIDR=X"},
    {"key": "gold", "label": "Emas Dunia", "ticker": "GC=F"},
    {"key": "brent", "label": "Minyak Brent", "ticker": "BZ=F"},
    {"key": "ixic", "label": "Nasdaq (AS)", "ticker": "^IXIC"},
]

# Pemetaan saham -> indeks sektor IDX (Yahoo Finance) untuk menghitung
# korelasi terhadap sektornya sendiri. CATATAN KEJUJURAN DATA: ini adalah
# pemetaan sektor yang disederhanakan berdasarkan bidang usaha utama emiten
# (bukan hasil scraping klasifikasi resmi IDX-IC), dipakai murni sebagai
# proksi/pendekatan untuk analisis korelasi, bukan rujukan klasifikasi resmi.
# FASE 5 (dedup): STOCK_SECTOR_MAP kini DITURUNKAN dari SECTOR_BASKETS --
# satu sumber kebenaran. Field "ticker" dipertahankan (tidak dipakai oleh
# logika korelasi, hanya label yang dipakai untuk mengelompokkan peer sektor).
STOCK_SECTOR_MAP: Dict[str, Dict[str, Any]] = {
    stock: {"ticker": f"{code}.JK", "label": info["corr_label"]}
    for code, info in SECTOR_BASKETS.items()
    for stock in info["stocks"]
}

def _extract_close_series(df, ticker: str):
    """Ambil kolom 'Close' untuk satu ticker dari hasil yf.download batch,
    menangani MultiIndex (banyak ticker) maupun kolom flat (1 ticker)."""
    try:
        if isinstance(df.columns, pd.MultiIndex):
            if ticker not in df.columns.get_level_values(0):
                return None
            sub = df[ticker]
        else:
            sub = df
        close = sub["Close"].dropna()
        return close if len(close) >= 5 else None
    except Exception:
        return None

def _interpret_correlation(value):
    if value is None:
        return "Data Historis Tidak Cukup"
    if value >= 0.7:
        return "Korelasi Kuat Positif"
    if value >= 0.3:
        return "Korelasi Sedang Positif"
    if value > -0.3:
        return "Korelasi Lemah / Tidak Signifikan"
    if value > -0.7:
        return "Korelasi Sedang Negatif"
    return "Korelasi Kuat Negatif"

def get_correlation_matrix(symbols: List[str], period: str = "1y", method: str = "pearson") -> Dict[str, Any]:
    """
    Menghitung matrix korelasi harga (berbasis return harian) untuk sejumlah
    saham sekaligus terhadap 5 faktor makro/komoditas/global inti.
    Data diambil real dari Yahoo Finance (bukan simulasi).

    method: "pearson" (default, standar untuk data return yang mendekati
    normal) atau "spearman" (korelasi rank, lebih tahan outlier/pasar
    ekstrem -- lihat catatan metodologi di endpoint /api/correlation/guide).
    """
    method = method if method in ("pearson", "spearman") else "pearson"
    symbols = [s.strip().upper() for s in symbols if s.strip()][:40]  # batasi agar 1 request wajar
    factors = CORRELATION_MATRIX_FACTORS
    if not symbols:
        return {"period": period, "method": method, "factors": factors, "rows": [], "source": "yahoo_finance"}

    stock_tickers = [f"{s}.JK" for s in symbols]
    factor_tickers = [f["ticker"] for f in factors]
    all_tickers = stock_tickers + factor_tickers

    try:
        df = yf.download(tickers=" ".join(all_tickers), period=period, interval="1d",
                          group_by="ticker", progress=False, threads=True)
    except Exception as e:
        print(f"Error fetching correlation matrix data: {str(e)}")
        return {"period": period, "method": method, "factors": factors, "rows": [], "source": "yahoo_finance", "error": "fetch_failed"}

    factor_returns = {}
    for f in factors:
        close = _extract_close_series(df, f["ticker"])
        factor_returns[f["key"]] = close.pct_change().dropna() if close is not None else None

    rows = []
    for symbol, ticker in zip(symbols, stock_tickers):
        close = _extract_close_series(df, ticker)
        stock_ret = close.pct_change().dropna() if close is not None else None
        row: Dict[str, Any] = {"symbol": symbol}
        for f in factors:
            fret = factor_returns.get(f["key"])
            corr_value = None
            n_points = 0
            if stock_ret is not None and fret is not None:
                aligned = pd.concat([stock_ret, fret], axis=1, join="inner").dropna()
                n_points = len(aligned)
                if n_points >= 15:
                    corr_value = round(float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1], method=method)), 3)
            row[f["key"]] = corr_value
            row[f"{f['key']}_n"] = n_points
        rows.append(row)

    return {"period": period, "method": method, "factors": factors, "rows": rows, "source": "yahoo_finance"}

def get_correlation_detail(symbol: str, period: str = "1y", peers: List[str] = None, method: str = "pearson") -> Dict[str, Any]:
    """
    Menghitung detail korelasi 1 saham terhadap seluruh faktor makro/komoditas
    /indeks global, basket saham sejenis (proksi sektor), dan sejumlah saham
    lain (peer), menggunakan data return harian real dari Yahoo Finance.

    method: "pearson" (default) atau "spearman" (rank correlation, lebih
    tahan terhadap outlier/kondisi pasar ekstrem).

    CATATAN KEJUJURAN DATA mengenai "sektor": indeks sektor resmi IDX
    (mis. IDXFINANCE.JK) di Yahoo Finance ternyata hanya menyediakan 1 titik
    data historis (snapshot), TIDAK CUKUP untuk hitung korelasi return harian.
    Sebagai gantinya kita hitung rata-rata return harian dari beberapa saham
    lain sejenis (basket peer sektor, berdasarkan STOCK_SECTOR_MAP) sebagai
    proksi pergerakan sektor -- ini tetap data pasar riil (bukan simulasi),
    hanya metodenya adalah agregasi manual, bukan indeks resmi.
    """
    method = method if method in ("pearson", "spearman") else "pearson"
    symbol = symbol.strip().upper()
    peers = [p.strip().upper() for p in (peers or []) if p.strip() and p.strip().upper() != symbol]

    factor_defs = list(CORRELATION_FACTORS)

    sector_info = STOCK_SECTOR_MAP.get(symbol)
    sector_basket_symbols: List[str] = []
    if sector_info:
        sector_basket_symbols = [
            s for s, info in STOCK_SECTOR_MAP.items()
            if info["label"] == sector_info["label"] and s != symbol
        ][:6]

    target_ticker = f"{symbol}.JK"
    peer_tickers = [f"{p}.JK" for p in peers]
    sector_basket_tickers = [f"{s}.JK" for s in sector_basket_symbols]

    all_tickers_ordered = (
        [target_ticker] + [f["ticker"] for f in factor_defs] + peer_tickers + sector_basket_tickers
    )
    seen = set()
    dedup_tickers = []
    for t in all_tickers_ordered:
        if t not in seen:
            seen.add(t)
            dedup_tickers.append(t)

    try:
        df = yf.download(tickers=" ".join(dedup_tickers), period=period, interval="1d",
                          group_by="ticker", progress=False, threads=True)
    except Exception as e:
        print(f"Error fetching correlation detail data: {str(e)}")
        return {"symbol": symbol, "period": period, "method": method, "factors": [], "peers": [],
                "source": "yahoo_finance", "error": "fetch_failed"}

    target_close = _extract_close_series(df, target_ticker)
    target_ret = target_close.pct_change().dropna() if target_close is not None else None

    def compute_corr_from_return(other_ret):
        if target_ret is None or other_ret is None:
            return None, 0
        aligned = pd.concat([target_ret, other_ret], axis=1, join="inner").dropna()
        n = len(aligned)
        if n < 15:
            return None, n
        return round(float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1], method=method)), 3), n

    def compute_corr(other_ticker: str):
        other_close = _extract_close_series(df, other_ticker)
        other_ret = other_close.pct_change().dropna() if other_close is not None else None
        return compute_corr_from_return(other_ret)

    factors_result = []
    for f in factor_defs:
        corr, n = compute_corr(f["ticker"])
        factors_result.append({
            "key": f["key"], "label": f["label"], "ticker": f["ticker"], "category": f["category"],
            "correlation": corr, "data_points": n, "interpretation": _interpret_correlation(corr)
        })

    # Basket sektor (rata-rata return harian beberapa saham sejenis lain)
    if sector_basket_tickers:
        basket_returns = []
        for bt in sector_basket_tickers:
            bclose = _extract_close_series(df, bt)
            if bclose is not None:
                basket_returns.append(bclose.pct_change().dropna())
        if basket_returns:
            combined = pd.concat(basket_returns, axis=1, join="outer")
            sector_avg_ret = combined.mean(axis=1, skipna=True).dropna()
            corr, n = compute_corr_from_return(sector_avg_ret)
            factors_result.append({
                "key": "sector", "label": f"{sector_info['label']} (Rata-rata {len(basket_returns)} Saham Sejenis)",
                "ticker": None, "category": "sektor",
                "correlation": corr, "data_points": n, "interpretation": _interpret_correlation(corr),
                "basket_symbols": sector_basket_symbols
            })
        else:
            factors_result.append({
                "key": "sector", "label": sector_info["label"], "ticker": None, "category": "sektor",
                "correlation": None, "data_points": 0, "interpretation": _interpret_correlation(None),
                "basket_symbols": []
            })

    peers_result = []
    for p, pt in zip(peers, peer_tickers):
        corr, n = compute_corr(pt)
        peers_result.append({
            "symbol": p, "correlation": corr, "data_points": n,
            "interpretation": _interpret_correlation(corr)
        })
    peers_result.sort(key=lambda x: (x["correlation"] is None, -(abs(x["correlation"]) if x["correlation"] is not None else 0)))

    return {
        "symbol": symbol,
        "period": period,
        "method": method,
        "target_ticker": target_ticker,
        "data_points_target": int(len(target_close)) if target_close is not None else 0,
        "has_sector_mapping": sector_info is not None,
        "factors": factors_result,
        "peers": peers_result,
        "source": "yahoo_finance",
    }

def _resolve_asset_ticker(asset_code: str, asset_type: str):
    """
    Menerjemahkan 1 input asset (dipakai fitur Lead-Lag) menjadi ticker
    Yahoo Finance & label tampilan. asset_type "factor" mengacu pada daftar
    CORRELATION_FACTORS (mis. "gold", "brent", "usdidr"); selain itu
    diperlakukan sebagai kode saham IDX biasa (otomatis + ".JK").
    """
    asset_code = asset_code.strip().upper()
    if asset_type == "factor":
        match = next((f for f in CORRELATION_FACTORS if f["key"] == asset_code.lower()), None)
        if match:
            return match["ticker"], match["label"]
        return None, asset_code
    return f"{asset_code}.JK", asset_code

def get_lead_lag_analysis(asset_a: str, asset_a_type: str, asset_b: str, asset_b_type: str,
                           period: str = "1y", max_lag: int = 10) -> Dict[str, Any]:
    """
    Cross-Correlation Function (CCF) / analisis Lead-Lag antara 2 variabel
    (saham atau faktor makro/komoditas/global), untuk menguji apakah
    pergerakan salah satu variabel baru "terasa" di variabel lain setelah
    jeda waktu tertentu (mis. harga minyak dunia hari ini baru memengaruhi
    saham maskapai 2 hari kemudian).

    Konvensi lag (k):
      - k > 0 : asset_a MENDAHULUI (leads) asset_b sebanyak k hari
                (return asset_a hari t dikorelasikan dengan return asset_b hari t+k)
      - k < 0 : asset_b mendahului asset_a sebanyak |k| hari
      - k = 0 : korelasi searah waktu (contemporaneous), sama seperti Pearson/Spearman biasa

    Data return harian real dari Yahoo Finance (bukan simulasi).
    """
    max_lag = max(1, min(int(max_lag), 20))  # batasi supaya wajar & tidak mahal secara komputasi

    ticker_a, label_a = _resolve_asset_ticker(asset_a, asset_a_type)
    ticker_b, label_b = _resolve_asset_ticker(asset_b, asset_b_type)

    if not ticker_a or not ticker_b:
        return {"error": "invalid_asset", "source": "yahoo_finance"}

    try:
        df = yf.download(tickers=f"{ticker_a} {ticker_b}", period=period, interval="1d",
                          group_by="ticker", progress=False, threads=True)
    except Exception as e:
        print(f"Error fetching lead-lag data: {str(e)}")
        return {"error": "fetch_failed", "source": "yahoo_finance"}

    close_a = _extract_close_series(df, ticker_a)
    close_b = _extract_close_series(df, ticker_b)
    if close_a is None or close_b is None:
        return {"error": "insufficient_data", "source": "yahoo_finance"}

    ret_a = close_a.pct_change().dropna()
    ret_b = close_b.pct_change().dropna()

    combined = pd.concat([ret_a, ret_b], axis=1, join="inner").dropna()
    combined.columns = ["a", "b"]

    if len(combined) < (max_lag * 2 + 15):
        # Data historis tidak cukup untuk menguji lag sejauh itu secara wajar
        max_lag = max(1, (len(combined) - 15) // 2)
        if max_lag < 1:
            return {"error": "insufficient_data", "source": "yahoo_finance",
                    "data_points": len(combined)}

    lag_results = []
    for k in range(-max_lag, max_lag + 1):
        shifted_b = combined["b"].shift(-k)
        aligned = pd.concat([combined["a"], shifted_b], axis=1).dropna()
        n = len(aligned)
        corr = round(float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1])), 3) if n >= 15 else None
        lag_results.append({"lag": k, "correlation": corr, "data_points": n})

    valid = [r for r in lag_results if r["correlation"] is not None]
    best = max(valid, key=lambda r: abs(r["correlation"])) if valid else None

    if best is None:
        best_summary = "Data historis tidak cukup untuk menentukan lag terbaik."
    elif best["lag"] == 0:
        best_summary = f"Korelasi tertinggi terjadi pada lag 0 (searah waktu / contemporaneous), tidak ada efek jeda yang signifikan."
    elif best["lag"] > 0:
        best_summary = f"{label_a} tampak MENDAHULUI {label_b} sebesar {best['lag']} hari (korelasi {best['correlation']:+.2f})."
    else:
        best_summary = f"{label_b} tampak MENDAHULUI {label_a} sebesar {abs(best['lag'])} hari (korelasi {best['correlation']:+.2f})."

    return {
        "asset_a": {"code": asset_a.strip().upper(), "type": asset_a_type, "ticker": ticker_a, "label": label_a},
        "asset_b": {"code": asset_b.strip().upper(), "type": asset_b_type, "ticker": ticker_b, "label": label_b},
        "period": period,
        "max_lag": max_lag,
        "lags": lag_results,
        "best_lag": best,
        "summary": best_summary,
        "data_points": len(combined),
        "source": "yahoo_finance",
    }


# ------------------------------------------------------------------
# ANALISIS WYCKOFF & VPA (HEURISTIK OTOMATIS) DARI DATA HARGA RIIL
# ------------------------------------------------------------------
# CATATAN KEJUJURAN METODOLOGI: Wyckoff Method & VPA pada dasarnya bersifat
# interpretatif (dibaca oleh analis manusia dari bentuk chart), BUKAN rumus
# matematika baku. Fungsi di bawah ini menerapkan seperangkat ATURAN
# KUANTITATIF (heuristik) yang MENDEKATI logika Wyckoff/VPA -- misalnya
# "volume > 2x rata-rata 20 hari" untuk mendeteksi klimaks, atau "range
# harga menyempit dalam N hari" untuk mendeteksi trading range -- namun
# HASILNYA TETAP PERKIRAAN/ESTIMASI, bukan analisis pasti seorang ahli.
# Karena itu hasilnya SELALU dilabeli "Deteksi Otomatis (Heuristik)" di
# frontend, bukan "Live DB" / analisis definitif.
def _rolling_mean(values: List[float], window: int) -> List[Any]:
    result = []
    for i in range(len(values)):
        if i < window:
            result.append(None)
        else:
            window_vals = values[i - window:i]
            result.append(sum(window_vals) / window)
    return result
