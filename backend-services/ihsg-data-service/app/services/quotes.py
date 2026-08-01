"""
quotes.py — Domain: kutipan harga & profil saham (rantai prioritas provider).

CLEAN ARCHITECTURE: dipisah dari god-class scraper.py. Menyatukan tiering
GoAPI.io -> Yahoo Finance -> stale-cache, dengan cache terpusat. Tidak tahu
tentang routing/presentation.
"""
import time
import yfinance as yf
import pandas as pd
from typing import List, Dict, Any

from app.services import goapi_provider
from app.services.goapi_provider import GoApiUnavailable
from app.services.cache import get_cache, TTL, lock_for

def get_stock_quotes(symbols: List[str]) -> List[Dict[str, Any]]:
    """
    Mengambil kutipan harga real-time/delayed untuk banyak saham individual
    sekaligus (mis. untuk Watchlist & Portofolio).

    RANTAI PRIORITAS SUMBER DATA (fallback berjenjang, TIDAK PERNAH error
    ke user hanya karena satu tier gagal):
      1. GoAPI.io   (/stock/idx/prices) -- HANYA dicoba jika GOAPI_API_KEY
         sudah diset di environment; jika belum/berlangganan belum aktif,
         tier ini dilewati sepenuhnya tanpa melakukan request apa pun.
      2. Yahoo Finance (yfinance)       -- dipakai untuk simbol mana pun
         yang tidak berhasil didapat dari GoAPI.io.
      3. Cache lama (stale)             -- jika kedua tier live gagal,
         pertahankan nilai cache terakhir yang diketahui daripada kosong.
      4. (Simulasi/demo ditangani di FRONTEND jika array hasil ini kosong
         untuk simbol tsb -- backend tidak pernah mengarang harga.)

    Kode saham Indonesia di Yahoo Finance memakai akhiran ".JK" (mis. BBCA.JK).
    Fungsi ini menerima kode polos (BBCA) dan otomatis menambahkan akhiran
    tersebut, lalu mengembalikannya kembali sebagai kode polos di response.

    Menggunakan cache in-memory singkat (20 detik) per simbol untuk mengurangi
    beban permintaan berulang dan risiko rate-limiting di kedua provider.
    """
    if not symbols:
        return []

    now = time.time()
    results: Dict[str, Dict[str, Any]] = {}
    symbols_to_fetch: List[str] = []

    # Cek cache terpusat dulu, kumpulkan simbol yang perlu di-fetch ulang
    for symbol in symbols:
        cached = get_cache().get(f"quote:{symbol}")
        if cached is not None:
            results[symbol] = cached
        else:
            symbols_to_fetch.append(symbol)

    # PERF (single-flight): jika ada simbol yang perlu di-fetch, amankan batch
    # dengan lock per-set-simbol. Request konkuren dengan simbol yang sama
    # menunggu request pertama mengisi cache, lalu re-check -> cache hit,
    # sehingga tidak memicu N panggilan identik ke Yahoo (thundering herd).
    if symbols_to_fetch:
        batch_key = "|".join(sorted(symbols_to_fetch))
        with lock_for("quote_batch:" + batch_key):
            # Re-check: mungkin sudah terisi oleh requester yang menang lock
            still_missing = [
                s for s in symbols_to_fetch
                if get_cache().get(f"quote:{s}") is None
            ]
            if still_missing:
                symbols_to_fetch = still_missing
            else:
                for s in symbols_to_fetch:
                    cached = get_cache().get(f"quote:{s}")
                    if cached is not None:
                        results[s] = cached
                symbols_to_fetch = []

    # --- TIER 1: GoAPI.io (prioritas utama, jika API key sudah aktif) ---
    if symbols_to_fetch and goapi_provider.is_goapi_configured():
        try:
            goapi_quotes = goapi_provider.get_batch_prices(symbols_to_fetch)
            for symbol in list(symbols_to_fetch):
                item = goapi_quotes.get(symbol)
                if not item:
                    continue
                try:
                    close = float(item.get("close"))
                    change = float(item.get("change", 0) or 0)
                    change_pct = float(item.get("change_pct", 0) or 0)
                    quote = {
                        "symbol": symbol,
                        "price": round(close, 2),
                        "change": round(change, 2),
                        "change_percent": round(change_pct, 2),
                        "volume": int(item.get("volume", 0) or 0),
                        "source": "goapi_io",
                        "_cached_at": now,
                    }
                    get_cache().set(f"quote:{symbol}", quote, TTL.QUOTE)
                    results[symbol] = quote
                    symbols_to_fetch.remove(symbol)
                except (TypeError, ValueError):
                    continue  # data tidak lengkap untuk simbol ini, biarkan fallback ke Yahoo Finance
        except GoApiUnavailable as e:
            print(f"GoAPI.io tidak tersedia untuk batch quotes, fallback ke Yahoo Finance: {str(e)}")

    # --- TIER 2: Yahoo Finance (fallback untuk simbol yang belum didapat) ---
    if symbols_to_fetch:
        yahoo_tickers = [f"{s}.JK" for s in symbols_to_fetch]
        try:
            # yf.download dengan banyak ticker sekaligus jauh lebih efisien
            # (1 request batch) dibanding memanggil yf.Ticker() per saham.
            df = yf.download(tickers=" ".join(yahoo_tickers), period="5d", interval="1d", group_by="ticker", progress=False)

            for symbol, yahoo_symbol in zip(symbols_to_fetch, yahoo_tickers):
                try:
                    # PERBAIKAN: dengan group_by="ticker", yfinance TETAP mengembalikan
                    # kolom MultiIndex (Ticker, Price) meskipun hanya 1 simbol diminta,
                    # sehingga asumsi lama "1 ticker = kolom flat" salah dan menyebabkan
                    # symbol tunggal selalu gagal (endpoint mengembalikan array kosong).
                    # Sekarang selalu cek MultiIndex terlebih dahulu, apa pun jumlah tickernya.
                    if isinstance(df.columns, pd.MultiIndex):
                        stock_df = df[yahoo_symbol] if yahoo_symbol in df.columns.get_level_values(0) else pd.DataFrame()
                    else:
                        stock_df = df

                    stock_df = stock_df.dropna(subset=["Close"]) if not stock_df.empty else stock_df

                    if stock_df.empty or len(stock_df) < 1:
                        raise ValueError("Data kosong dari Yahoo Finance")

                    last_close = float(stock_df["Close"].iloc[-1])
                    prev_close = float(stock_df["Close"].iloc[-2]) if len(stock_df) >= 2 else last_close
                    change = last_close - prev_close
                    change_percent = (change / prev_close) * 100 if prev_close else 0.0

                    quote = {
                        "symbol": symbol,
                        "price": round(last_close, 2),
                        "change": round(change, 2),
                        "change_percent": round(change_percent, 2),
                        "volume": int(stock_df["Volume"].iloc[-1]) if "Volume" in stock_df else 0,
                        "source": "yahoo_finance",
                        "_cached_at": now,
                    }
                    get_cache().set(f"quote:{symbol}", quote, TTL.QUOTE)
                    results[symbol] = quote
                except Exception as inner_e:
                    print(f"Error parsing quote for {symbol}: {str(inner_e)}")
                    # Fallback: pertahankan cache lama jika ada, walau sudah kedaluwarsa,
                    # supaya frontend tetap dapat nilai yang masuk akal alih-alih kosong.
                    stale = get_cache().get(f"quote:{symbol}", allow_stale=True)
                    if stale:
                        results[symbol] = stale
        except Exception as e:
            print(f"Error fetching batch quotes from Yahoo Finance: {str(e)}")
            # Kalau seluruh batch gagal (mis. tidak ada koneksi internet),
            # tetap kembalikan apa pun yang ada di cache lama untuk simbol tsb.
            for symbol in symbols_to_fetch:
                stale = get_cache().get(f"quote:{symbol}", allow_stale=True)
                if stale:
                    results[symbol] = stale

    # Kembalikan dalam urutan yang sama seperti input, tanpa field internal _cached_at
    ordered_results = []
    for symbol in symbols:
        quote = results.get(symbol)
        if quote:
            ordered_results.append({k: v for k, v in quote.items() if not k.startswith("_")})
    return ordered_results

def get_stock_profile(symbol: str) -> Dict[str, Any]:
    """
    Mengambil PROFIL LENGKAP satu saham untuk halaman Detail Saham: info
    transaksi harian (open/high/low/prev close/volume/52-week range/
    market cap) DAN fundamental riil (PER, PBV, EPS, BVPS).

    RANTAI PRIORITAS SUMBER DATA per kelompok field (fallback berjenjang,
    TIDAK PERNAH error ke user hanya karena satu tier gagal):
      - INFO TRANSAKSI (open/high/low/close/volume/change): GoAPI.io
        (/stock/idx/prices) dicoba LEBIH DULU jika API key sudah aktif;
        jika gagal/belum berlangganan, fallback ke Yahoo Finance.
      - FUNDAMENTAL (EPS/BVPS/PER/PBV/52w range/market cap): Yahoo Finance
        (GoAPI.io tidak menyediakan rasio fundamental siap pakai untuk
        tier gratis/dasar saat ini, hanya profil deskriptif perusahaan).
    Response menyertakan field terpisah "transaction_source" &
    "fundamental_source" supaya frontend bisa menampilkan label sumber
    data yang jujur & akurat untuk masing-masing kelompok, alih-alih satu
    label tunggal yang menyamaratakan kedua kelompok data.

    Beberapa saham (terutama yang baru IPO, tidak likuid, atau rugi/EPS
    negatif) mungkin tidak punya sebagian field ini di kedua provider --
    field yang tidak tersedia dikembalikan sebagai None, dan frontend
    WAJIB menampilkan status "Data tidak tersedia" secara jujur untuk
    field tsb, bukan mengarang angka pengganti.

    Cache in-memory 10 menit per simbol karena panggilan info fundamental
    (baik GoAPI maupun yf.Ticker().info) jauh lebih berat dibanding batch
    quote history biasa.
    """
    symbol = (symbol or "").upper().strip()
    if not symbol:
        raise ValueError("Simbol saham tidak boleh kosong")

    now = time.time()
    cached = get_cache().get(f"profile:{symbol}")
    if cached is not None:
        return {k: v for k, v in cached.items() if not k.startswith("_")}

    # --- TIER 1 (Info Transaksi): GoAPI.io, jika API key sudah aktif ---
    goapi_transaction: Dict[str, Any] = {}
    transaction_source = None
    if goapi_provider.is_goapi_configured():
        try:
            goapi_quotes = goapi_provider.get_batch_prices([symbol])
            item = goapi_quotes.get(symbol)
            if item and item.get("close") is not None:
                goapi_transaction = {
                    "price": float(item.get("close")),
                    "open": item.get("open"),
                    "day_high": item.get("high"),
                    "day_low": item.get("low"),
                    "volume": item.get("volume"),
                    "change": item.get("change"),
                    "change_percent": item.get("change_pct"),
                }
                transaction_source = "goapi_io"
        except GoApiUnavailable as e:
            print(f"GoAPI.io tidak tersedia untuk profil {symbol}, fallback ke Yahoo Finance: {str(e)}")

    # --- TIER 2 (Fundamental + fallback Info Transaksi): Yahoo Finance ---
    yahoo_symbol = f"{symbol}.JK"
    try:
        ticker = yf.Ticker(yahoo_symbol)
        info = ticker.info or {}

        # yfinance kadang mengembalikan info nyaris kosong (mis. simbol
        # tidak dikenali/delisted) -- anggap gagal jika tidak ada harga
        # sama sekali DAN GoAPI.io juga tidak memberi harga, supaya
        # frontend bisa fallback dengan jujur.
        yahoo_price = info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose")
        price = goapi_transaction.get("price") or yahoo_price
        if price is None:
            raise ValueError(f"Tidak ada data harga untuk {yahoo_symbol} dari GoAPI.io maupun Yahoo Finance")

        eps = info.get("trailingEps")
        bvps = info.get("bookValue")
        per = info.get("trailingPE")
        pbv = info.get("priceToBook")
        # Fallback hitung manual PER/PBV dari harga & EPS/BVPS riil apabila
        # Yahoo tidak menyediakan rasio siap pakai tapi komponen dasarnya ada.
        if per is None and eps not in (None, 0):
            per = price / eps
        if pbv is None and bvps not in (None, 0):
            pbv = price / bvps

        if not transaction_source:
            transaction_source = "yahoo_finance"

        profile = {
            "symbol": symbol,
            "name": info.get("longName") or info.get("shortName"),
            "currency": info.get("currency", "IDR"),
            # --- INFO TRANSAKSI HARI INI (GoAPI.io jika ada, fallback Yahoo Finance) ---
            "price": round(float(price), 2),
            "previous_close": info.get("previousClose") or info.get("regularMarketPreviousClose"),
            "open": goapi_transaction.get("open") or info.get("open") or info.get("regularMarketOpen"),
            "day_high": goapi_transaction.get("day_high") or info.get("dayHigh") or info.get("regularMarketDayHigh"),
            "day_low": goapi_transaction.get("day_low") or info.get("dayLow") or info.get("regularMarketDayLow"),
            "volume": goapi_transaction.get("volume") or info.get("volume") or info.get("regularMarketVolume"),
            "average_volume_10d": info.get("averageVolume10days"),
            "average_volume_3m": info.get("averageVolume"),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
            "market_cap": info.get("marketCap"),
            "shares_outstanding": info.get("sharesOutstanding"),
            "beta": info.get("beta"),
            # --- FUNDAMENTAL RIIL (selalu dari Yahoo Finance, laporan keuangan terakhir) ---
            "eps": eps,
            "bvps": bvps,
            "per": per,
            "pbv": pbv,
            "dividend_yield": info.get("dividendYield"),
            "roe": info.get("returnOnEquity"),
            "profit_margin": info.get("profitMargins"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "transaction_source": transaction_source,
            "fundamental_source": "yahoo_finance",
            "source": transaction_source,  # dipertahankan untuk kompatibilitas mundur
            "_cached_at": now,
        }
        get_cache().set(f"profile:{symbol}", profile, TTL.PROFILE)
        return {k: v for k, v in profile.items() if not k.startswith("_")}
    except Exception as e:
        print(f"Error fetching stock profile for {symbol}: {str(e)}")

        # Yahoo Finance gagal total -- kalau GoAPI.io setidaknya berhasil
        # memberi info transaksi, tetap kembalikan itu (fundamental kosong
        # apa adanya, jangan dikarang) daripada gagal total.
        if goapi_transaction:
            profile = {
                "symbol": symbol,
                "name": None,
                "currency": "IDR",
                "price": round(float(goapi_transaction["price"]), 2),
                "previous_close": None,
                "open": goapi_transaction.get("open"),
                "day_high": goapi_transaction.get("day_high"),
                "day_low": goapi_transaction.get("day_low"),
                "volume": goapi_transaction.get("volume"),
                "average_volume_10d": None,
                "average_volume_3m": None,
                "fifty_two_week_high": None,
                "fifty_two_week_low": None,
                "market_cap": None,
                "shares_outstanding": None,
                "beta": None,
                "eps": None,
                "bvps": None,
                "per": None,
                "pbv": None,
                "dividend_yield": None,
                "roe": None,
                "profit_margin": None,
                "revenue_growth": None,
                "earnings_growth": None,
                "transaction_source": "goapi_io",
                "fundamental_source": None,
                "source": "goapi_io",
                "_cached_at": now,
            }
            get_cache().set(f"profile:{symbol}", profile, TTL.PROFILE)
            return {k: v for k, v in profile.items() if not k.startswith("_")}

        stale = get_cache().get(f"profile:{symbol}", allow_stale=True)
        if stale:
            result = {k: v for k, v in stale.items() if not k.startswith("_")}
            result["stale"] = True
            return result
        raise

# ------------------------------------------------------------------
# KORELASI: harga saham vs faktor makro/komoditas/global & antar saham
# ------------------------------------------------------------------
# Daftar faktor makro/komoditas/global inti yang dipakai untuk analisis
# korelasi. Semua tersedia gratis & real-time/delayed di Yahoo Finance
# (sudah diverifikasi langsung lewat endpoint chart Yahoo Finance).
