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
