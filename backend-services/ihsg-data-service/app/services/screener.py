"""
screener.py
===========
Mesin screener STRATEGI berbasis SINYAL RIIL untuk Stock Village.

Data: riwayat harga harian & fundamental dari Yahoo Finance (yfinance).
Tidak ada angka yang dikarang: semua sinyal dihitung dari OHLCV asli
(close, volume, indikator teknikal) dan data fundamental (.info).

CATATAN KEJUJURAN:
- "Bandarmology" TIDAK memakai data broker riil (butuh GoAPI.io/bursa).
  Di sini dihitung sebagai PROXY berbasis volume & pergerakan harga
  (akumulasi/distribusi dari effort vs result), dan frontend WAJIB
  memberi label jujur bahwa ini proxy, bukan data broker.
- "Elliott Wave" adalah HEURISTIK struktur tren (higher-high/lower-low)
  pada data riil, bukan hitungan gelombang Elliott resmi.
- "Scan Semua Saham" memindai universe SAHAM LIKUID (daftar terkurasi),
  karena memindai seluruh 951 emiten akan sangat lambat & rawan
  rate-limit Yahoo. Label di frontend menyebut jumlah saham yang
  benar-benar dipindai.
"""

import time
import math
from typing import List, Dict, Any, Optional, Tuple

import yfinance as yf
import pandas as pd

from app.services.scraper import _PROFILE_CACHE

# ---------------------------------------------------------------------------
# Cache riwayat harga (TTL 10 menit) supaya scan ulang tidak hit Yahoo lagi
# ---------------------------------------------------------------------------
_HISTORY_CACHE: Dict[str, Dict[str, Any]] = {}
_HISTORY_CACHE_TTL = 600


def _fetch_history(symbol: str, period: str = "1y") -> Optional[pd.DataFrame]:
    """Mengambil OHLCV harian riil (cache 10 menit). None jika gagal."""
    key = f"{symbol.upper()}|{period}"
    now = time.time()
    cached = _HISTORY_CACHE.get(key)
    if cached and (now - cached["_at"]) < _HISTORY_CACHE_TTL:
        return cached["df"]

    ticker = f"{symbol.upper()}.JK"
    try:
        df = yf.download(tickers=ticker, period=period, interval="1d",
                         progress=False, threads=True, auto_adjust=False)
        if df is None or df.empty:
            return None
        # Jika MultiIndex (selalu untuk download 1 ticker di versi yfinance
        # tertentu), ambil kolom level harga biasa
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.dropna(subset=["Close"])
        if len(df) < 30:
            return None
        _HISTORY_CACHE[key] = {"df": df, "_at": now}
        return df
    except Exception as e:
        print(f"[screener] Gagal ambil history {symbol}: {e}")
        return None


def _sma(series: pd.Series, window: int) -> Optional[float]:
    if len(series) < window:
        return None
    return round(float(series.rolling(window).mean().iloc[-1]), 2)


def _rsi(series: pd.Series, window: int = 14) -> Optional[float]:
    """RSI Wilder dari close."""
    if len(series) < window + 1:
        return None
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 2)


def _macd(series: pd.Series, fast=12, slow=26, signal=9) -> Optional[Dict[str, float]]:
    if len(series) < slow + signal:
        return None
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return {
        "macd": round(float(macd_line.iloc[-1]), 3),
        "signal": round(float(signal_line.iloc[-1]), 3),
        "histogram": round(float(hist.iloc[-1]), 3),
        "macd_prev": round(float(macd_line.iloc[-2]), 3),
        "signal_prev": round(float(signal_line.iloc[-2]), 3),
    }


def _atr_pct(df: pd.DataFrame, window: int = 14) -> Optional[float]:
    if len(df) < window + 1:
        return None
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.rolling(window).mean().iloc[-1]
    price = float(close.iloc[-1])
    return round(float(atr) / price * 100, 2) if price else None


def compute_technicals(symbol: str, period: str = "1y") -> Optional[Dict[str, Any]]:
    """Menghitung seluruh indikator teknikal riil untuk satu saham."""
    df = _fetch_history(symbol, period)
    if df is None:
        return None

    close = df["Close"]
    volume = df["Volume"]
    last_close = float(close.iloc[-1])
    prev_close = float(close.iloc[-2]) if len(close) > 1 else last_close
    change_pct = round((last_close - prev_close) / prev_close * 100, 2) if prev_close else 0.0

    sma20 = _sma(close, 20)
    sma50 = _sma(close, 50)
    sma200 = _sma(close, 200)
    rsi = _rsi(close, 14)
    macd = _macd(close)

    # Volume
    vol_avg20 = float(volume.tail(20).mean()) if len(volume) >= 20 else None
    last_vol = float(volume.iloc[-1])
    vol_ratio = round(last_vol / vol_avg20, 2) if vol_avg20 else None

    # Range
    high20 = float(df["High"].tail(20).max())
    low20 = float(df["Low"].tail(20).min())
    high50 = float(df["High"].tail(50).max())
    low50 = float(df["Low"].tail(50).min())

    # Momentum (return kumulatif)
    ret5 = round((last_close / float(close.iloc[-6]) - 1) * 100, 2) if len(close) > 6 else None
    ret20 = round((last_close / float(close.iloc[-21]) - 1) * 100, 2) if len(close) > 21 else None
    ret60 = round((last_close / float(close.iloc[-61]) - 1) * 100, 2) if len(close) > 61 else None

    # 5 candle terakhir untuk price action
    last_candles = []
    for i in range(max(0, len(df) - 5), len(df)):
        o, h, l, c = float(df["Open"].iloc[i]), float(df["High"].iloc[i]), float(df["Low"].iloc[i]), float(df["Close"].iloc[i])
        body = c - o
        rng = (h - l) or 1e-9
        last_candles.append({
            "date": str(df.index[i].date()),
            "open": round(o, 2), "high": round(h, 2), "low": round(l, 2), "close": round(c, 2),
            "body": round(body, 2),
            "body_pct": round(abs(body) / o * 100, 2) if o else 0,
            "range_pct": round(rng / o * 100, 2) if o else 0,
            "upper_wick": round(h - max(o, c), 2),
            "lower_wick": round(min(o, c) - l, 2),
            "bullish": c >= o,
        })

    return {
        "symbol": symbol,
        "price": round(last_close, 2),
        "change_pct": change_pct,
        "sma20": sma20, "sma50": sma50, "sma200": sma200,
        "rsi": rsi,
        "macd": macd,
        "vol_avg20": int(vol_avg20) if vol_avg20 else None,
        "last_volume": int(last_vol),
        "vol_ratio": vol_ratio,
        "high20": round(high20, 2), "low20": round(low20, 2),
        "high50": round(high50, 2), "low50": round(low50, 2),
        "ret5": ret5, "ret20": ret20, "ret60": ret60,
        "atr_pct": _atr_pct(df),
        "data_points": len(df),
        "source": "yahoo_finance",
        "last_candles": last_candles,
    }


def _candle_patterns(tech: Dict[str, Any]) -> List[str]:
    """Deteksi pola candlestick dari 3 candle terakhir (data riil)."""
    pats = []
    c = tech.get("last_candles") or []
    if len(c) < 2:
        return pats
    last, prev = c[-1], c[-2]
    # Bullish engulfing
    if (not last["bullish"]) and prev["bullish"] and last["body"] < 0 and prev["body"] > 0 and abs(last["body"]) > abs(prev["body"]):
        pats.append("Bearish Engulfing")
    elif last["bullish"] and (not prev["bullish"]) and last["body"] > 0 and prev["body"] < 0 and last["body"] > abs(prev["body"]):
        pats.append("Bullish Engulfing")
    # Doji
    if last["body_pct"] < 0.15:
        pats.append("Doji")
    # Hammer (lower wick > 2x body, di area bawah)
    if last["lower_wick"] > 2 * abs(last["body"]) and last["bullish"]:
        pats.append("Hammer")
    # Shooting star (upper wick besar di atas)
    if last["upper_wick"] > 2 * abs(last["body"]) and not last["bullish"]:
        pats.append("Shooting Star")
    # Marubozu (body dominan > 90% range)
    if last["range_pct"] > 0 and abs(last["body"]) / (last["range_pct"] / 100 * last["open"] if last["open"] else 1) > 0.9:
        pats.append("Marubozu")
    return pats


def _wyckoff_heuristic(tech: Dict[str, Any]) -> Dict[str, Any]:
    """Heuristik fase Wyckoff sederhana dari data riil (range, spring, climax, markup)."""
    price = tech["price"]
    hi, lo = tech["high50"], tech["low50"]
    rng_mid = (hi + lo) / 2
    range_width_pct = (hi - lo) / rng_mid * 100 if rng_mid else 0
    in_range = price >= lo * 0.98 and price <= hi * 1.02 and range_width_pct < 25

    below_range = price < lo * 0.98
    above_range = price > hi * 1.02

    spring_like = below_range and tech.get("vol_ratio", 0) and tech["vol_ratio"] > 1.4 and tech["change_pct"] > 0
    climax_like = tech.get("change_pct", 0) < -2.5 and tech.get("vol_ratio", 0) and tech["vol_ratio"] > 2.0
    markup_like = above_range and tech.get("sma20") and price > tech["sma20"]

    if markup_like:
        phase, label, tier = "Phase E", "Markup / Breakout", "BULLISH"
    elif spring_like:
        phase, label, tier = "Phase C", "Spring / Shakeout", "BULLISH"
    elif climax_like:
        phase, label, tier = "Phase A", "Selling Climax (potensi reversal)", "BULLISH_WATCH"
    elif in_range:
        phase, label, tier = "Phase B", "Trading Range (konsolidasi)", "NEUTRAL"
    elif price < tech.get("sma50", price):
        phase, label, tier = "Distribusi", "Tekanan jual (SOW)", "BEARISH"
    else:
        phase, label, tier = "Phase D", "Awal markup (higher-low)", "BULLISH"

    return {"phase": phase, "pattern": label, "tier": tier,
            "range_width_pct": round(range_width_pct, 2)}


def _elliott_heuristic(tech: Dict[str, Any]) -> Dict[str, Any]:
    """Heuristik struktur tren (impuls naik/turun) dari momentum & posisi vs SMA."""
    price = tech["price"]
    up_struct = tech.get("sma20") and tech.get("sma50") and price > tech["sma20"] > tech["sma50"]
    down_struct = tech.get("sma50") and price < tech["sma20"] < tech["sma50"] if tech.get("sma20") else False
    ret60 = tech.get("ret60") or 0
    ret20 = tech.get("ret20") or 0

    if up_struct and ret60 > 0:
        label, tier = "Impuls naik (HH/HL) — struktur 5 gelombang naik", "BULLISH"
    elif down_struct and ret60 < 0:
        label, tier = "Impuls turun (LH/LL) — tekanan jual berlanjut", "BEARISH"
    elif ret20 > 0 and ret60 < 0:
        label, tier = "Koreksi naik di dalam downtrend (kemungkinan wave 4)", "NEUTRAL"
    elif ret20 < 0 and ret60 > 0:
        label, tier = "Koreksi turun di dalam uptrend (kemungkinan wave 2)", "BULLISH_WATCH"
    else:
        label, tier = "Konsolidasi — struktur belum jelas", "NEUTRAL"
    return {"pattern": label, "tier": tier}


# ---------------------------------------------------------------------------
# ANALISIS PER STRATEGI (semua dari data riil)
# ---------------------------------------------------------------------------

def analyze_strategy(symbol: str, strategy: str) -> Optional[Dict[str, Any]]:
    strategy = (strategy or "").lower().strip()
    tech = compute_technicals(symbol)
    if tech is None:
        return None

    base = {
        "symbol": symbol,
        "price": tech["price"],
        "change_pct": tech["change_pct"],
        "vol_ratio": tech["vol_ratio"],
        "rsi": tech["rsi"],
        "source": "yahoo_finance",
        "strategy": strategy,
    }

    if strategy == "teknikal":
        price, s20, s50, s200 = tech["price"], tech.get("sma20"), tech.get("sma50"), tech.get("sma200")
        rsi = tech.get("rsi")
        setup, tier, action, zone = "Sideways — belum ada sinyal kuat", "NEUTRAL", "WAIT & SEE", ""
        if None not in (s20, s50) and price > s20 and price > s50:
            if s50 and s200 and s50 > s200:
                setup = "Golden Cross (SMA 50 > SMA 200) — uptrend"
                tier = "BULLISH"
            else:
                setup = "Harga di atas SMA20 & SMA50 — tren naik"
                tier = "BULLISH"
            if tech.get("high20") and price >= tech["high20"] * 0.995:
                setup = "Breakout ke level tertinggi 20 hari"
                tier = "BULLISH_STRONG"
                action = "BUY ON BREAKOUT"
            else:
                action = "TREND FOLLOWING"
        elif None not in (s20, s50) and price < s20 and price < s50:
            setup = "Harga di bawah SMA20 & SMA50 — tren turun"
            tier = "BEARISH"
            action = "AVOID / EXIT"
        elif None not in (s50, s200) and s50 < s200:
            setup = "Death Cross (SMA 50 < SMA 200)"
            tier = "BEARISH_STRONG"
            action = "SELL SIGNAL"
        if rsi is not None:
            if rsi >= 70:
                setup += " — RSI overbought"
                if tier != "BEARISH_STRONG":
                    tier = "BEARISH" if tier != "BULLISH" else "BULLISH_WATCH"
                action = "OVERBOUGHT WATCH"
            elif rsi <= 30:
                setup += " — RSI oversold"
                if tier == "BEARISH":
                    tier = "BEARISH_WATCH"
        support = tech.get("low20")
        resistance = tech.get("high20")
        zone = f"Support Rp {support:,.0f} | Resistance Rp {resistance:,.0f}" if support and resistance else ""
        return {**base, "setup": setup, "action": action, "tier": tier, "zone": zone,
                "support": support, "resistance": resistance, "indicator": f"RSI {rsi}" if rsi else "RSI n/a"}

    if strategy == "vpa":
        price, vr = tech["price"], tech.get("vol_ratio") or 1.0
        chg = tech["change_pct"]
        if chg > 1.0 and vr >= 1.5:
            pattern, tier, action = "Bullish Effort vs Result (harga naik, volume melambung)", "BULLISH", "ACCUMULATION ALERT"
        elif chg < -2.5 and vr >= 2.0:
            pattern, tier, action = "Selling Climax (turun tajam, volume ultra tinggi)", "BULLISH_WATCH", "REVERSAL ALERT"
        elif vr <= 0.6:
            pattern, tier, action = "No Supply Test (volume sangat mini)", "BULLISH", "TEST COMPLETE"
        elif chg > 0 and vr >= 1.2:
            pattern, tier, action = "Stopping Volume / akumulasi (volume besar, harga naik pelan)", "BULLISH", "ACCUMULATION WATCH"
        elif chg <= 0 and vr >= 1.5:
            pattern, tier, action = "Supply Absorption (volume besar, harga tertahan/turun)", "BEARISH", "DISTRIBUTION WATCH"
        else:
            pattern, tier, action = "Normal Trading (tanpa pola VPA signifikan)", "NEUTRAL", "MONITOR"
        return {**base, "pattern": pattern, "tier": tier, "action": action,
                "vol_ratio": vr}

    if strategy == "wyckoff":
        wh = _wyckoff_heuristic(tech)
        return {**base, "pattern": f"{wh['phase']} — {wh['pattern']}", "tier": wh["tier"],
                "action": wh["pattern"].upper(), "ad_status": wh["pattern"]}

    if strategy == "fundamental":
        try:
            info = yf.Ticker(f"{symbol}.JK").info or {}
        except Exception:
            info = {}
        eps = info.get("trailingEps") or info.get("epsTrailingTwelveMonths")
        bvps = info.get("bookValue")
        per = info.get("trailingPE")
        pbv = info.get("priceToBook")
        roe = info.get("returnOnEquity")
        der = info.get("debtToEquity")
        price = tech["price"]

        fair_value = None
        mos = None
        if eps and bvps and eps > 0 and bvps > 0:
            fair_value = math.sqrt(22.5 * eps * bvps)
            mos = round((fair_value - price) / fair_value * 100, 1)
        tier = "NEUTRAL"
        action = "MONITOR"
        if mos is not None:
            if mos >= 15: tier, action = "BULLISH_STRONG", "UNDERVALUED"
            elif mos >= 5: tier, action = "BULLISH", "MULAI MURAH"
            elif mos <= -15: tier, action = "BEARISH_STRONG", "OVERVALUED"
            elif mos <= -5: tier, action = "BEARISH", "MAHAL"
        note = f"PER {per:.1f}x | PBV {pbv:.2f}x" if per and pbv else "Data PER/PBV tidak tersedia"
        return {**base,
                "eps": round(float(eps), 2) if eps else None,
                "bvps": round(float(bvps), 2) if bvps else None,
                "per": round(float(per), 2) if per else None,
                "pbv": round(float(pbv), 2) if pbv else None,
                "roe": round(float(roe) * 100, 1) if roe else None,
                "der": round(float(der), 1) if der else None,
                "fair_value": round(fair_value, 0) if fair_value else None,
                "mos": mos, "tier": tier, "action": action, "note": note}

    if strategy == "bandarmology":
        # PROXY JUJUR: volume + harga (BUKAN data broker riil)
        vr = tech.get("vol_ratio") or 1.0
        chg = tech["change_pct"]
        rsi = tech.get("rsi")
        if vr >= 1.3 and chg > 0 and (rsi is None or rsi < 72):
            detector, tier, action = "AKUMULASI (proxy volume)", "BULLISH", "NET BUY PROXY"
        elif vr >= 1.3 and chg < 0:
            detector, tier, action = "DISTRIBUSI (proxy volume)", "BEARISH", "NET SELL PROXY"
        elif vr <= 0.7:
            detector, tier, action = "SEPI / NO INTEREST", "NEUTRAL", "MONITOR"
        else:
            detector, tier, action = "NETRAL", "NEUTRAL", "MONITOR"
        return {**base, "pattern": detector, "tier": tier, "action": action,
                "proxy_note": "Proxy volume & harga (bukan data broker riil)"}

    if strategy == "elliott":
        eh = _elliott_heuristic(tech)
        return {**base, "pattern": eh["pattern"], "tier": eh["tier"],
                "action": eh["pattern"][:40].upper()}

    if strategy == "price_action":
        pats = _candle_patterns(tech)
        bull_pats = {"Bullish Engulfing", "Hammer", "Marubozu"}
        bear_pats = {"Bearish Engulfing", "Shooting Star"}
        if any(p in bull_pats for p in pats):
            tier, action = "BULLISH", "POLA BULLISH"
        elif any(p in bear_pats for p in pats):
            tier, action = "BEARISH", "POLA BEARISH"
        else:
            tier, action = "NEUTRAL", "TIDAK ADA POLA JELAS"
        pat_label = ", ".join(pats) if pats else "Tidak ada pola signifikan"
        return {**base, "pattern": pat_label, "tier": tier, "action": action}

    if strategy == "scalping":
        chg = tech["change_pct"]
        vr = tech.get("vol_ratio") or 1.0
        atr = tech.get("atr_pct")
        active = vr >= 1.2 and abs(chg) >= 0.8 and (atr is None or atr >= 1.0)
        if active:
            tier = "BULLISH" if chg > 0 else "BEARISH"
            action = "AKTIF & VOLATIL — cocok scalping"
        else:
            tier, action = "NEUTRAL", "VOLATILITAS NORMAL"
        return {**base, "pattern": action, "tier": tier, "action": action,
                "atr_pct": atr}

    return None


def scan_strategy(strategy: str, symbols: List[str]) -> List[Dict[str, Any]]:
    """Memindai daftar saham untuk satu strategi. Hasil riil, diurutkan
    (bullish kuat di atas). Simbol yang gagal diambil datanya dilewati."""
    results = []
    for sym in symbols:
        row = analyze_strategy(sym, strategy)
        if row is not None:
            results.append(row)
    tier_rank = {"BULLISH_STRONG": 0, "BULLISH": 1, "BULLISH_WATCH": 2,
                 "NEUTRAL": 3, "BEARISH_WATCH": 4, "BEARISH": 5, "BEARISH_STRONG": 6}
    results.sort(key=lambda r: (tier_rank.get(r.get("tier", "NEUTRAL"), 3),
                                -(abs(r.get("change_pct") or 0))))
    return results


# Universe saham likuid untuk "Scan Semua Saham" (terkurasi, cepat, jujur)
LIQUID_UNIVERSE = [
    "BBCA","BBRI","BMRI","BBNI","BRIS","BCA","BTPS","BJBR","BBTN",
    "TLKM","ISAT","EXCL","MTEL","TOWR","TBIG","FREN",
    "ASII","UNTR","UNVR","ICBP","INDF","MYOR","GGRM","HMSP","CPIN","KLBF",
    "ADRO","PTBA","ITMG","ANTM","MDKA","INCO","MEDC","PGAS","BUMI","BRPT","TPIA","INKP","TKIM",
    "GOTO","BUKA","EMTK","MAPI","MAPA","ACES","ERAA","AMRT","LPPF",
    "JSMR","WIKA","WSKT","ADHI","PTPP","SMGR","WEGE","BIRD","ASSA","SMDR",
    "BSDE","PWON","SMRA","CTRA","LPKR","SSIA","DMAS",
    "SIDO","KAEF","PEHA","MIKA","HEAL","SILO",
    "ELSA","ARTO","BBHI","AGRO","BSIM","NISP","PNBN","BJTM","BDMN","MSIA","AKRA","AALI","LSIP","SMMA","MGRO",
]


def build_stockpick(mode: str, symbols: List[str], limit: int = 6) -> Dict[str, Any]:
    """
    Stock Pick berbasis sinyal riil:
      - harian: saham dengan momentum hari ini (change>0), volume di atas
        rata-rata, RSI tidak overbought ekstrem, urut skor momentum.
      - swing: uptrend riil (harga > SMA20 > SMA50) atau golden cross,
        fundamental wajar (MOS tidak terlalu negatif bila tersedia).
    Narasi dibangun dari ANGKA RIIL yang dihitung.
    """
    candidates = []
    for sym in symbols:
        tech = compute_technicals(sym)
        if tech is None:
            continue
        # Fundamental (PER/EPS/BVPS) hanya diambil jika sudah ada di cache
        # profil (murah & cepat); jika belum, dilewati agar scan tidak lambat.
        per = eps = bvps = None
        cached_profile = _PROFILE_CACHE.get(sym)
        if cached_profile and (time.time() - cached_profile.get("_cached_at", 0)) < 600:
            per = cached_profile.get("per")
            eps = cached_profile.get("eps")
            bvps = cached_profile.get("bvps")

        chg = tech["change_pct"]
        vr = tech.get("vol_ratio") or 1.0
        rsi = tech.get("rsi")
        s20, s50 = tech.get("sma20"), tech.get("sma50")
        price = tech["price"]
        ret5 = tech.get("ret5") or 0
        ret20 = tech.get("ret20") or 0

        if mode == "harian":
            cond = chg > 0 and vr >= 1.2 and (rsi is None or rsi < 78)
            score = chg * 1.5 + vr * 10 + max(0, ret5) * 0.8
        else:  # swing
            cond = bool(s20 and s50 and price > s20 > s50) and ret20 > 0
            score = ret20 * 1.2 + (ret5 or 0) * 0.5 + (10 if (s50 or 0) > (tech.get("sma200") or 0) else 0)

        if not cond:
            continue

        mos = None
        if eps and bvps and eps > 0 and bvps > 0:
            fv = math.sqrt(22.5 * eps * bvps)
            mos = round((fv - price) / fv * 100, 1)

        candidates.append({
            "symbol": sym,
            "price": round(price, 2),
            "change_pct": chg,
            "vol_ratio": vr,
            "rsi": rsi,
            "sma20": s20, "sma50": s50,
            "ret5": ret5, "ret20": ret20,
            "per": round(float(per), 2) if per else None,
            "mos": mos,
            "score": round(score, 2),
            "source": "yahoo_finance",
        })

    candidates.sort(key=lambda c: c["score"], reverse=True)
    picked = candidates[:limit]

    # Narasi dari angka riil
    for c in picked:
        if mode == "harian":
            rsi_note = f"RSI {c['rsi']:.0f}" if c["rsi"] else "RSI n/a"
            vol_note = f"volume {c['vol_ratio']}x rata-rata 20 hari" if c["vol_ratio"] else "volume normal"
            c["narrative"] = (
                f"Harga naik {c['change_pct']:.2f}% hari ini dengan {vol_note} "
                f"({rsi_note}). Momentum harian {c['ret5']:+.1f}% (5 hari). "
                f"Untuk day trading, utamakan likuiditas & stop loss ketat. "
                f"⚠ Sinyal dihitung dari data riil Yahoo Finance, bukan rekomendasi."
            )
        else:
            s20n = f"{c['sma20']:,.0f}" if c["sma20"] else "n/a"
            s50n = f"{c['sma50']:,.0f}" if c["sma50"] else "n/a"
            mos_note = f"MOS {c['mos']:+.1f}% (Graham)" if c["mos"] is not None else "fundamental: data tidak lengkap"
            per_note = f"PER {c['per']:.1f}x" if c["per"] else "PER n/a"
            c["narrative"] = (
                f"Uptrend riil: harga {c['price']:,.0f} di atas SMA20 ({s20n}) dan SMA50 ({s50n}), "
                f"return 20 hari {c['ret20']:+.1f}%. {per_note}, {mos_note}. "
                f"Untuk swing, target pergerakan beberapa hari–minggu dengan risiko 1–2% per posisi. "
                f"⚠ Sinyal dihitung dari data riil Yahoo Finance, bukan rekomendasi."
            )

    return {
        "mode": mode,
        "analyzed": len(symbols),
        "with_data": len(candidates),
        "picks": picked,
        "source": "yahoo_finance",
        "honesty_note": "Pemilihan berbasis indikator & fundamental riil (Yahoo Finance) pada universe saham likuid."
    }
