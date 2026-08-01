"""
wyckoff.py — Domain: deteksi heuristik Wyckoff/VPA pada data riil.

CLEAN ARCHITECTURE: dipisah dari god-class scraper.py. Heuristik interpretatif
pada OHLCV riil; hasil wajib dilabeli "Deteksi Otomatis (Heuristik)".
"""
import yfinance as yf
import pandas as pd
from typing import List, Dict, Any

from app.services.correlation import _rolling_mean

def analyze_wyckoff_vpa( symbol: str, period: str = "6mo") -> Dict[str, Any]:
    """
    Mengambil data harga historis RIIL (Yahoo Finance) untuk 1 saham, lalu
    menjalankan deteksi heuristik untuk:
      1. Volume spike (VSA): volume > 2x rata-rata volume 20 hari.
      2. Trading range (fase akumulasi/distribusi Wyckoff Phase B): rentang
         harga tertinggi-terendah dalam window bergulir menyempit secara
         signifikan dibanding rata-rata rentang periode sebelumnya.
      3. Spring: harga menembus (breakdown) di bawah batas bawah trading
         range yang baru terdeteksi, lalu ditutup kembali naik di ATAS
         batas bawah tsb dalam <=3 hari berikutnya, disertai volume tinggi.
      4. Sign of Strength (SOS): breakout di ATAS batas atas trading range
         disertai volume di atas rata-rata.
      5. Selling Climax (VPA): penurunan harga tajam (>3% dalam 1 hari)
         dengan volume spike (>2.5x rata-rata) -- pola pembalikan potensial.
    Semua ambang batas (threshold) di atas adalah aturan heuristik umum yang
    dipakai praktisi VPA/Wyckoff, BUKAN garansi keakuratan.
    """
    symbol = symbol.strip().upper()
    ticker = f"{symbol}.JK"

    try:
        df = yf.download(tickers=ticker, period=period, interval="1d", progress=False)
    except Exception as e:
        print(f"Error fetching Wyckoff/VPA analysis data: {str(e)}")
        return {"symbol": symbol, "source": "yahoo_finance", "error": "fetch_failed"}

    if df.empty:
        return {"symbol": symbol, "source": "yahoo_finance", "error": "no_data"}

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()

    if len(df) < 30:
        return {"symbol": symbol, "source": "yahoo_finance", "error": "insufficient_data", "data_points": len(df)}

    dates = [d.strftime("%Y-%m-%d") for d in df["Date"]]
    opens = df["Open"].tolist()
    highs = df["High"].tolist()
    lows = df["Low"].tolist()
    closes = df["Close"].tolist()
    volumes = df["Volume"].tolist()
    n = len(df)

    vol_sma20 = _rolling_mean(volumes, 20)

    candles = []
    for i in range(n):
        is_spike = vol_sma20[i] is not None and volumes[i] > 2.0 * vol_sma20[i]
        candles.append({
            "date": dates[i], "open": float(opens[i]), "high": float(highs[i]),
            "low": float(lows[i]), "close": float(closes[i]), "volume": float(volumes[i]),
            "vol_sma20": float(vol_sma20[i]) if vol_sma20[i] is not None else None,
            "is_spike": bool(is_spike),
        })

    # --- 1. Deteksi Trading Range (kandidat Phase B Wyckoff) ---
    # Cari window 15 hari dengan rentang (high-low) tersempit dibanding
    # rentang rata-rata keseluruhan periode -- indikasi konsolidasi.
    range_window = 15
    avg_range_all = sum(highs[i] - lows[i] for i in range(n)) / n
    best_window_start = None
    best_window_score = None
    for i in range(0, n - range_window):
        window_high = max(highs[i:i + range_window])
        window_low = min(lows[i:i + range_window])
        window_range = window_high - window_low
        avg_close = sum(closes[i:i + range_window]) / range_window
        relative_range = window_range / avg_close if avg_close else 999
        if best_window_score is None or relative_range < best_window_score:
            best_window_score = relative_range
            best_window_start = i

    trading_range = None
    if best_window_start is not None:
        end_idx = min(best_window_start + range_window, n - 1)
        range_high = max(highs[best_window_start:end_idx + 1])
        range_low = min(lows[best_window_start:end_idx + 1])
        trading_range = {
            "start_idx": best_window_start, "end_idx": end_idx,
            "start_date": dates[best_window_start], "end_date": dates[end_idx],
            "range_high": range_high, "range_low": range_low,
        }

    markers = []

    # --- 2. Deteksi Spring (Phase C): breakdown di bawah range_low lalu rebound ---
    if trading_range:
        search_start = trading_range["end_idx"]
        search_end = min(search_start + 20, n - 1)
        for i in range(search_start, search_end):
            if lows[i] < trading_range["range_low"] * 0.995:
                # Cek apakah dalam 3 hari berikutnya harga close kembali di atas range_low
                for j in range(i + 1, min(i + 4, n)):
                    if closes[j] > trading_range["range_low"]:
                        markers.append({
                            "idx": i, "type": "SPRING",
                            "label": "Spring (Phase C)",
                            "desc": f"Harga sempat tembus di bawah support Rp{trading_range['range_low']:,.0f} pada {dates[i]}, lalu ditutup kembali naik di atas support pada {dates[j]} -- pola klasik Spring/Shakeout Wyckoff Phase C."
                        })
                        break
                break

    # --- 3. Deteksi Sign of Strength (SOS): breakout di atas range_high + volume ---
    if trading_range:
        search_start = trading_range["end_idx"]
        search_end = min(search_start + 25, n - 1)
        for i in range(search_start, search_end):
            if closes[i] > trading_range["range_high"] * 1.005 and vol_sma20[i] and volumes[i] > 1.3 * vol_sma20[i]:
                markers.append({
                    "idx": i, "type": "SOS",
                    "label": "Sign of Strength (SOS)",
                    "desc": f"Harga breakout di atas resistance Rp{trading_range['range_high']:,.0f} pada {dates[i]} disertai volume di atas rata-rata -- indikasi Sign of Strength (Phase D/E)."
                })
                break

    # --- 4. Deteksi Selling Climax (VPA): drop tajam + volume ultra tinggi ---
    for i in range(1, n):
        daily_change_pct = ((closes[i] - closes[i - 1]) / closes[i - 1]) * 100 if closes[i - 1] else 0
        if daily_change_pct <= -3.0 and vol_sma20[i] and volumes[i] > 2.5 * vol_sma20[i]:
            markers.append({
                "idx": i, "type": "CLIMAX",
                "label": "Selling Climax (VPA)",
                "desc": f"Penurunan tajam {daily_change_pct:.1f}% pada {dates[i]} dengan volume {volumes[i] / vol_sma20[i]:.1f}x rata-rata -- pola Selling Climax, berpotensi titik balik jangka pendek."
            })

    # --- 5. Deteksi Buying Climax (VPA): naik tajam + volume ultra tinggi (potensi distribusi) ---
    for i in range(1, n):
        daily_change_pct = ((closes[i] - closes[i - 1]) / closes[i - 1]) * 100 if closes[i - 1] else 0
        if daily_change_pct >= 4.0 and vol_sma20[i] and volumes[i] > 2.5 * vol_sma20[i]:
            markers.append({
                "idx": i, "type": "BUYING_CLIMAX",
                "label": "Buying Climax (VPA)",
                "desc": f"Kenaikan tajam {daily_change_pct:+.1f}% pada {dates[i]} dengan volume {volumes[i] / vol_sma20[i]:.1f}x rata-rata -- waspada potensi distribusi/profit taking."
            })

    markers.sort(key=lambda m: m["idx"])

    # --- 6. Ringkasan interpretasi otomatis (tetap disclaimer heuristik) ---
    marker_types = set(m["type"] for m in markers)
    if "SPRING" in marker_types and "SOS" in marker_types:
        interpretation = "Terdeteksi pola akumulasi Wyckoff yang cukup lengkap (Trading Range → Spring → Sign of Strength). Ini POLA HEURISTIK, perlu dikonfirmasi analisis lanjutan."
    elif "SPRING" in marker_types:
        interpretation = "Terdeteksi kemungkinan Spring (Phase C) di dalam trading range. Belum ada konfirmasi Sign of Strength lanjutan."
    elif "CLIMAX" in marker_types:
        interpretation = "Terdeteksi Selling Climax (volume ultra tinggi saat harga jatuh tajam) -- pola VPA yang umum mendahului rebound jangka pendek, namun tidak selalu."
    elif trading_range:
        interpretation = "Saham sedang berada dalam fase konsolidasi/trading range, belum ada sinyal breakout (Spring/SOS) yang terdeteksi heuristik."
    else:
        interpretation = "Tidak ada pola trading range/Spring/Climax yang signifikan terdeteksi dalam periode ini berdasarkan aturan heuristik yang digunakan."

    return {
        "symbol": symbol,
        "period": period,
        "data_points": n,
        "candles": candles,
        "trading_range": trading_range,
        "markers": markers,
        "interpretation": interpretation,
        "source": "yahoo_finance",
        "method": "heuristic_auto_detection",
    }
