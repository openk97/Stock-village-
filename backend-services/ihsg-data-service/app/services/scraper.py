import yfinance as yf
import pandas as pd
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models import IHSGHistory, NewsArticle, SectorPerformance

# Cache sederhana in-memory untuk kutipan saham individual (batch quote), supaya
# permintaan berulang dalam rentang waktu singkat (mis. beberapa user membuka
# Watchlist bersamaan) tidak memicu banyak panggilan berlebih ke Yahoo Finance,
# yang bisa menyebabkan rate-limit/pemblokiran sementara oleh Yahoo.
_QUOTE_CACHE: Dict[str, Dict[str, Any]] = {}
_QUOTE_CACHE_TTL_SECONDS = 20

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
        if db.query(SectorPerformance).count() == 0:
            sectors = [
                SectorPerformance(sector_name="1. Finansial (IDXFIN)", change_percent=1.24),
                SectorPerformance(sector_name="2. Infrastruktur (IDXINFRA)", change_percent=0.87),
                SectorPerformance(sector_name="3. Properti (IDXPROPERT)", change_percent=0.45),
                SectorPerformance(sector_name="4. Konsumer Primer (IDXNONCYC)", change_percent=0.12),
                SectorPerformance(sector_name="5. Energi (IDXENERGY)", change_percent=-0.42),
                SectorPerformance(sector_name="6. Teknologi (IDXTECHNO)", change_percent=-1.15)
            ]
            db.bulk_save_objects(sectors)
        
        db.commit()

    @staticmethod
    def get_stock_quotes(symbols: List[str]) -> List[Dict[str, Any]]:
        """
        Mengambil kutipan harga real-time/delayed untuk banyak saham individual
        sekaligus (mis. untuk Watchlist & Portofolio) dari Yahoo Finance.

        Kode saham Indonesia di Yahoo Finance memakai akhiran ".JK" (mis. BBCA.JK).
        Fungsi ini menerima kode polos (BBCA) dan otomatis menambahkan akhiran
        tersebut, lalu mengembalikannya kembali sebagai kode polos di response.

        Menggunakan cache in-memory singkat (20 detik) per simbol untuk mengurangi
        beban permintaan berulang ke Yahoo Finance dan risiko rate-limiting.
        """
        if not symbols:
            return []

        now = time.time()
        results: Dict[str, Dict[str, Any]] = {}
        symbols_to_fetch: List[str] = []

        # Cek cache dulu, kumpulkan simbol yang perlu di-fetch ulang
        for symbol in symbols:
            cached = _QUOTE_CACHE.get(symbol)
            if cached and (now - cached["_cached_at"]) < _QUOTE_CACHE_TTL_SECONDS:
                results[symbol] = cached
            else:
                symbols_to_fetch.append(symbol)

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
                        _QUOTE_CACHE[symbol] = quote
                        results[symbol] = quote
                    except Exception as inner_e:
                        print(f"Error parsing quote for {symbol}: {str(inner_e)}")
                        # Fallback: pertahankan cache lama jika ada, walau sudah kedaluwarsa,
                        # supaya frontend tetap dapat nilai yang masuk akal alih-alih kosong.
                        stale = _QUOTE_CACHE.get(symbol)
                        if stale:
                            results[symbol] = stale
            except Exception as e:
                print(f"Error fetching batch quotes from Yahoo Finance: {str(e)}")
                # Kalau seluruh batch gagal (mis. tidak ada koneksi internet),
                # tetap kembalikan apa pun yang ada di cache lama untuk simbol tsb.
                for symbol in symbols_to_fetch:
                    stale = _QUOTE_CACHE.get(symbol)
                    if stale:
                        results[symbol] = stale

        # Kembalikan dalam urutan yang sama seperti input, tanpa field internal _cached_at
        ordered_results = []
        for symbol in symbols:
            quote = results.get(symbol)
            if quote:
                ordered_results.append({k: v for k, v in quote.items() if not k.startswith("_")})
        return ordered_results

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
    STOCK_SECTOR_MAP = {
        "BBCA": {"ticker": "IDXFINANCE.JK", "label": "Sektor Keuangan"},
        "BBRI": {"ticker": "IDXFINANCE.JK", "label": "Sektor Keuangan"},
        "BMRI": {"ticker": "IDXFINANCE.JK", "label": "Sektor Keuangan"},
        "BBNI": {"ticker": "IDXFINANCE.JK", "label": "Sektor Keuangan"},
        "BRIS": {"ticker": "IDXFINANCE.JK", "label": "Sektor Keuangan"},
        "ARTO": {"ticker": "IDXFINANCE.JK", "label": "Sektor Keuangan"},
        "TLKM": {"ticker": "IDXINFRA.JK", "label": "Sektor Infrastruktur"},
        "EXCL": {"ticker": "IDXINFRA.JK", "label": "Sektor Infrastruktur"},
        "ISAT": {"ticker": "IDXINFRA.JK", "label": "Sektor Infrastruktur"},
        "JSMR": {"ticker": "IDXINFRA.JK", "label": "Sektor Infrastruktur"},
        "WIFI": {"ticker": "IDXINFRA.JK", "label": "Sektor Infrastruktur"},
        "ASII": {"ticker": "IDXCYCLIC.JK", "label": "Sektor Konsumer Non-Primer"},
        "GOTO": {"ticker": "IDXTECHNO.JK", "label": "Sektor Teknologi"},
        "BUKA": {"ticker": "IDXTECHNO.JK", "label": "Sektor Teknologi"},
        "ADRO": {"ticker": "IDXENERGY.JK", "label": "Sektor Energi"},
        "PGAS": {"ticker": "IDXENERGY.JK", "label": "Sektor Energi"},
        "PTBA": {"ticker": "IDXENERGY.JK", "label": "Sektor Energi"},
        "MEDC": {"ticker": "IDXENERGY.JK", "label": "Sektor Energi"},
        "HRUM": {"ticker": "IDXENERGY.JK", "label": "Sektor Energi"},
        "ITMG": {"ticker": "IDXENERGY.JK", "label": "Sektor Energi"},
        "BUMI": {"ticker": "IDXENERGY.JK", "label": "Sektor Energi"},
        "AKRA": {"ticker": "IDXENERGY.JK", "label": "Sektor Energi"},
        "ANTM": {"ticker": "IDXBASIC.JK", "label": "Sektor Barang Baku"},
        "TPIA": {"ticker": "IDXBASIC.JK", "label": "Sektor Barang Baku"},
        "AMMN": {"ticker": "IDXBASIC.JK", "label": "Sektor Barang Baku"},
        "MDKA": {"ticker": "IDXBASIC.JK", "label": "Sektor Barang Baku"},
        "INCO": {"ticker": "IDXBASIC.JK", "label": "Sektor Barang Baku"},
        "SMGR": {"ticker": "IDXBASIC.JK", "label": "Sektor Barang Baku"},
        "UNTR": {"ticker": "IDXINDUST.JK", "label": "Sektor Perindustrian"},
        "UNVR": {"ticker": "IDXNONCYC.JK", "label": "Sektor Konsumer Primer"},
        "ICBP": {"ticker": "IDXNONCYC.JK", "label": "Sektor Konsumer Primer"},
        "INDF": {"ticker": "IDXNONCYC.JK", "label": "Sektor Konsumer Primer"},
        "CPIN": {"ticker": "IDXNONCYC.JK", "label": "Sektor Konsumer Primer"},
        "SIDO": {"ticker": "IDXNONCYC.JK", "label": "Sektor Konsumer Primer"},
        "KLBF": {"ticker": "IDXHEALTH.JK", "label": "Sektor Kesehatan"},
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


