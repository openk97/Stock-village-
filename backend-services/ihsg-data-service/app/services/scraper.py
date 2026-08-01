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
from app.services.cache import get_cache, TTL

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


class IHSGScraper:
    @staticmethod
    def fetch_and_sync_history(db: Session, period: str = "1y") -> List[Dict[str, Any]]:
        """
        Mengambil data historis IHSG (^JKSE) dari Yahoo Finance, menghitung indikator teknikal,
        menyimpannya (atau memperbarui) di database SQLite/PostgreSQL, dan mengembalikan data yang bersih.
        """
        ticker = "^JKSE"
        try:
            df = yf.download(tickers=ticker, period=period, interval="1d")
            if df.empty:
                # Fallback ke database jika Yahoo Finance gagal/offline
                return IHSGScraper.get_history_from_db(db)

            # Perbaikan bug kompatibilitas: versi yfinance terbaru mengembalikan
            # kolom MultiIndex (Price, Ticker) meskipun hanya 1 ticker diminta.
            # Ini menyebabkan row['Date'] menjadi Series, bukan scalar Timestamp,
            # sehingga .strftime() gagal (AttributeError: 'Series' object has no
            # attribute 'strftime'). Kita ratakan (flatten) kolomnya di sini.
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            df = df.reset_index()

            # Menghitung indikator teknikal menggunakan Pandas
            df['SMA_50'] = df['Close'].rolling(window=50).mean()
            df['SMA_200'] = df['Close'].rolling(window=200).mean()
            
            # Relative Strength Index (RSI)
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / (loss + 1e-10)
            df['RSI_14'] = 100 - (100 / (1 + rs))

            df = df.fillna(0)

            # Menyimpan/Sinkronisasi ke Database
            for _, row in df.iterrows():
                date_str = row['Date'].strftime('%Y-%m-%d')
                
                # Cek apakah record sudah ada di database
                db_record = db.query(IHSGHistory).filter(IHSGHistory.date == date_str).first()
                
                if db_record:
                    # Update jika sudah ada
                    db_record.open = float(row['Open'])
                    db_record.high = float(row['High'])
                    db_record.low = float(row['Low'])
                    db_record.close = float(row['Close'])
                    db_record.volume = float(row['Volume'])
                    db_record.sma_50 = float(row['SMA_50'])
                    db_record.sma_200 = float(row['SMA_200'])
                    db_record.rsi_14 = float(row['RSI_14'])
                else:
                    # Buat baru jika belum ada
                    new_record = IHSGHistory(
                        date=date_str,
                        open=float(row['Open']),
                        high=float(row['High']),
                        low=float(row['Low']),
                        close=float(row['Close']),
                        volume=float(row['Volume']),
                        sma_50=float(row['SMA_50']),
                        sma_200=float(row['SMA_200']),
                        rsi_14=float(row['RSI_14'])
                    )
                    db.add(new_record)
            
            db.commit()
            return IHSGScraper.get_history_from_db(db, period=period)

        except Exception as e:
            print(f"Error syncing IHSG history: {str(e)}")
            return IHSGScraper.get_history_from_db(db, period=period)

    @staticmethod
    def get_history_from_db(db: Session, period: str = "1y") -> List[Dict[str, Any]]:
        """
        Mengambil data historis langsung dari Database lokal.
        Bug lama: parameter 'period' tidak pernah dipakai untuk memfilter hasil,
        sehingga endpoint /api/ihsg/history selalu mengembalikan SELURUH data,
        membuat filter periode di frontend (1mo/3mo/6mo/1y/5y) tidak berfungsi.
        Sekarang kita batasi hasil sesuai jumlah hari yang sesuai dengan period.
        """
        records = db.query(IHSGHistory).order_by(IHSGHistory.date.asc()).all()

        period_to_days = {
            "5d": 5,
            "1mo": 30,
            "3mo": 90,
            "6mo": 180,
            "1y": 365,
            "5y": 365 * 5,
        }
        days = period_to_days.get(period)
        if days is not None and len(records) > days:
            records = records[-days:]

        return [
            {
                "date": r.date,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
                "sma_50": r.sma_50,
                "sma_200": r.sma_200,
                "rsi_14": r.rsi_14
            }
            for r in records
        ]

    @staticmethod
    def get_realtime_status() -> Dict[str, Any]:
        """
        Mengambil status pasar IHSG real-time / delayed 15 menit dari Yahoo Finance.
        """
        ticker = yf.Ticker("^JKSE")
        try:
            history = ticker.history(period="5d")
            if len(history) < 2:
                # Mock fallback jika bursa belum buka/error
                return IHSGScraper._get_mock_realtime()

            last_close = history['Close'].iloc[-1]
            prev_close = history['Close'].iloc[-2]
            change = last_close - prev_close
            change_percent = (change / prev_close) * 100

            return {
                "name": "Indeks Harga Saham Gabungan (IHSG)",
                "symbol": "^JKSE",
                "current_price": float(last_close),
                "previous_close": float(prev_close),
                "open": float(history['Open'].iloc[-1]),
                "high": float(history['High'].iloc[-1]),
                "low": float(history['Low'].iloc[-1]),
                "volume": int(history['Volume'].iloc[-1]),
                "change": float(change),
                "change_percent": float(change_percent),
                "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        except Exception as e:
            print(f"Error getting real-time status: {str(e)}")
            return IHSGScraper._get_mock_realtime()

    @staticmethod
    def _get_mock_realtime() -> Dict[str, Any]:
        """Fallback mock data jika koneksi internet terganggu."""
        return {
            "name": "Indeks Harga Saham Gabungan (IHSG)",
            "symbol": "^JKSE",
            "current_price": 7245.50,
            "previous_close": 7211.30,
            "open": 7211.30,
            "high": 7260.10,
            "low": 7208.50,
            "volume": 14200000000,
            "change": 34.20,
            "change_percent": 0.47,
            "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

    # ------------------------------------------------------------------
    # DATA PASAR RIIL UNTUK MARQUEE, SEKTOR HEATMAP & MARKET BREADTH
    # Semua dihitung dari quote Yahoo Finance (cache 60 detik).
    # ------------------------------------------------------------------
    @classmethod
    def get_sector_performance(cls) -> List[Dict[str, Any]]:
        """Performa 11 sektor IDX = rata-rata % perubahan harga RIIL konstituen
        (proksi jujur, bukan indeks resmi BEI). Fallback None per sektor bila
        semua konstituen gagal diambil."""
        cached = get_cache().get("market:sectors")
        if cached is not None:
            return cached

        result = []
        for code, info in SECTOR_BASKETS.items():
            quotes = cls.get_stock_quotes(info["stocks"])
            changes = [q["change_percent"] for q in quotes if isinstance(q.get("change_percent"), (int, float))]
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

    @classmethod
    def get_macro_quotes(cls) -> List[Dict[str, Any]]:
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

    @classmethod
    def get_market_breadth(cls) -> Dict[str, Any]:
        """Market breadth (naik/tetap/turun) dihitung dari quote RIIL universe
        saham likuid -- proksi jujur, bukan seluruh bursa."""
        from app.services.screener import LIQUID_UNIVERSE
        cached = get_cache().get("market:breadth")
        if cached is not None:
            return cached

        quotes = cls.get_stock_quotes(LIQUID_UNIVERSE)
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

    @staticmethod
    def seed_initial_data(db: Session):
        """
        Inisialisasi data awal (seeding) untuk Berita dan Sektor jika database masih kosong.
        Ini memastikan user langsung melihat data dinamis di dashboard.
        """
        # 1. Seeding Berita (News Seeding)
        if db.query(NewsArticle).count() == 0:
            news_items = [
                NewsArticle(
                    title="BI Pertahankan Suku Bunga di 6.00%, Pasar Merespon Positif",
                    url="https://cnbcindonesia.com/market/bi-suku-bunga-6",
                    source="CNBC Indonesia",
                    sentiment="Positive",
                    score=0.85,
                    published_at="10 Menit Lalu"
                ),
                NewsArticle(
                    title="Laba Bersih BCA (BBCA) Kuartal II Melampaui Estimasi Konsensus",
                    url="https://bisnis.com/market/laba-bca-q2",
                    source="Bisnis.com",
                    sentiment="Positive",
                    score=0.90,
                    published_at="1 Jam Lalu"
                ),
                NewsArticle(
                    title="Bursa Saham Wall Street Ditutup Koreksi Imbas Rilis Data Tenaga Kerja AS",
                    url="https://kontan.co.id/global/wall-street-koreksi",
                    source="Kontan",
                    sentiment="Negative",
                    score=-0.65,
                    published_at="3 Jam Lalu"
                ),
                NewsArticle(
                    title="Sektor Energi Tertekan Penurunan Harga Komoditas Minyak Mentah Global",
                    url="https://kontan.co.id/market/sektor-energi-turun",
                    source="Kontan",
                    sentiment="Negative",
                    score=-0.45,
                    published_at="5 Jam Lalu"
                ),
                NewsArticle(
                    title="Asing Catat Net Buy Rp 500 Miliar Terutama di Saham Big Banks",
                    url="https://cnbcindonesia.com/market/net-buy-asing-big-banks",
                    source="CNBC Indonesia",
                    sentiment="Positive",
                    score=0.78,
                    published_at="6 Jam Lalu"
                )
            ]
            db.bulk_save_objects(news_items)

        # 2. Seeding Sektoral (Sector Seeding)
        # CATATAN KEJUJURAN DATA: ini adalah data SIMULASI/DEMO statis (bukan
        # data live dari BEI), diberi label "Simulasi Internal (Demo)" jujur
        # di frontend. Sebelumnya hanya 6 dari 11 sektor resmi IDX yang
        # di-seed di sini padahal UI menampilkan badge "11 SEKTOR" -- bug ini
        # sudah diperbaiki dengan melengkapi seluruh 11 sektor resmi IDX
        # (IDXFIN, IDXINFRA, IDXENERGY, IDXBASIC, IDXNONCYC, IDXCYCLIC,
        # IDXHEALTH, IDXINDUST, IDXPROPERT, IDXTECHNO, IDXTRANS).
        if db.query(SectorPerformance).count() == 0:
            sectors = [
                SectorPerformance(sector_name="1. Finansial (IDXFIN)", change_percent=1.24),
                SectorPerformance(sector_name="2. Infrastruktur (IDXINFRA)", change_percent=0.87),
                SectorPerformance(sector_name="3. Energi (IDXENERGY)", change_percent=-0.42),
                SectorPerformance(sector_name="4. Barang Baku (IDXBASIC)", change_percent=-0.72),
                SectorPerformance(sector_name="5. Konsumer Primer (IDXNONCYC)", change_percent=0.12),
                SectorPerformance(sector_name="6. Konsumer Non-Primer (IDXCYCLIC)", change_percent=0.54),
                SectorPerformance(sector_name="7. Kesehatan (IDXHEALTH)", change_percent=-0.15),
                SectorPerformance(sector_name="8. Industri (IDXINDUST)", change_percent=0.32),
                SectorPerformance(sector_name="9. Properti (IDXPROPERT)", change_percent=0.45),
                SectorPerformance(sector_name="10. Teknologi (IDXTECHNO)", change_percent=-1.15),
                SectorPerformance(sector_name="11. Transportasi (IDXTRANS)", change_percent=0.95)
            ]
            db.bulk_save_objects(sectors)
        
        db.commit()

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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

    @staticmethod
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

    @classmethod
    def get_correlation_matrix(cls, symbols: List[str], period: str = "1y", method: str = "pearson") -> Dict[str, Any]:
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
        factors = cls.CORRELATION_MATRIX_FACTORS
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
            close = cls._extract_close_series(df, f["ticker"])
            factor_returns[f["key"]] = close.pct_change().dropna() if close is not None else None

        rows = []
        for symbol, ticker in zip(symbols, stock_tickers):
            close = cls._extract_close_series(df, ticker)
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

    @classmethod
    def get_correlation_detail(cls, symbol: str, period: str = "1y", peers: List[str] = None, method: str = "pearson") -> Dict[str, Any]:
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

        factor_defs = list(cls.CORRELATION_FACTORS)

        sector_info = cls.STOCK_SECTOR_MAP.get(symbol)
        sector_basket_symbols: List[str] = []
        if sector_info:
            sector_basket_symbols = [
                s for s, info in cls.STOCK_SECTOR_MAP.items()
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

        target_close = cls._extract_close_series(df, target_ticker)
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
            other_close = cls._extract_close_series(df, other_ticker)
            other_ret = other_close.pct_change().dropna() if other_close is not None else None
            return compute_corr_from_return(other_ret)

        factors_result = []
        for f in factor_defs:
            corr, n = compute_corr(f["ticker"])
            factors_result.append({
                "key": f["key"], "label": f["label"], "ticker": f["ticker"], "category": f["category"],
                "correlation": corr, "data_points": n, "interpretation": cls._interpret_correlation(corr)
            })

        # Basket sektor (rata-rata return harian beberapa saham sejenis lain)
        if sector_basket_tickers:
            basket_returns = []
            for bt in sector_basket_tickers:
                bclose = cls._extract_close_series(df, bt)
                if bclose is not None:
                    basket_returns.append(bclose.pct_change().dropna())
            if basket_returns:
                combined = pd.concat(basket_returns, axis=1, join="outer")
                sector_avg_ret = combined.mean(axis=1, skipna=True).dropna()
                corr, n = compute_corr_from_return(sector_avg_ret)
                factors_result.append({
                    "key": "sector", "label": f"{sector_info['label']} (Rata-rata {len(basket_returns)} Saham Sejenis)",
                    "ticker": None, "category": "sektor",
                    "correlation": corr, "data_points": n, "interpretation": cls._interpret_correlation(corr),
                    "basket_symbols": sector_basket_symbols
                })
            else:
                factors_result.append({
                    "key": "sector", "label": sector_info["label"], "ticker": None, "category": "sektor",
                    "correlation": None, "data_points": 0, "interpretation": cls._interpret_correlation(None),
                    "basket_symbols": []
                })

        peers_result = []
        for p, pt in zip(peers, peer_tickers):
            corr, n = compute_corr(pt)
            peers_result.append({
                "symbol": p, "correlation": corr, "data_points": n,
                "interpretation": cls._interpret_correlation(corr)
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

    @classmethod
    def _resolve_asset_ticker(cls, asset_code: str, asset_type: str):
        """
        Menerjemahkan 1 input asset (dipakai fitur Lead-Lag) menjadi ticker
        Yahoo Finance & label tampilan. asset_type "factor" mengacu pada daftar
        CORRELATION_FACTORS (mis. "gold", "brent", "usdidr"); selain itu
        diperlakukan sebagai kode saham IDX biasa (otomatis + ".JK").
        """
        asset_code = asset_code.strip().upper()
        if asset_type == "factor":
            match = next((f for f in cls.CORRELATION_FACTORS if f["key"] == asset_code.lower()), None)
            if match:
                return match["ticker"], match["label"]
            return None, asset_code
        return f"{asset_code}.JK", asset_code

    @classmethod
    def get_lead_lag_analysis(cls, asset_a: str, asset_a_type: str, asset_b: str, asset_b_type: str,
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

        ticker_a, label_a = cls._resolve_asset_ticker(asset_a, asset_a_type)
        ticker_b, label_b = cls._resolve_asset_ticker(asset_b, asset_b_type)

        if not ticker_a or not ticker_b:
            return {"error": "invalid_asset", "source": "yahoo_finance"}

        try:
            df = yf.download(tickers=f"{ticker_a} {ticker_b}", period=period, interval="1d",
                              group_by="ticker", progress=False, threads=True)
        except Exception as e:
            print(f"Error fetching lead-lag data: {str(e)}")
            return {"error": "fetch_failed", "source": "yahoo_finance"}

        close_a = cls._extract_close_series(df, ticker_a)
        close_b = cls._extract_close_series(df, ticker_b)
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
    @staticmethod
    def _rolling_mean(values: List[float], window: int) -> List[Any]:
        result = []
        for i in range(len(values)):
            if i < window:
                result.append(None)
            else:
                window_vals = values[i - window:i]
                result.append(sum(window_vals) / window)
        return result

    @classmethod
    def analyze_wyckoff_vpa(cls, symbol: str, period: str = "6mo") -> Dict[str, Any]:
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

        vol_sma20 = cls._rolling_mean(volumes, 20)

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
