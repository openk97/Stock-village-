"""
history.py — Domain: riwayat harga IHSG + realtime (sync ke DB & fallback).

CLEAN ARCHITECTURE: dipisah dari god-class scraper.py. Menangani sinkronisasi
history ^JKSE ke database & pembacaan realtime; tidak tahu soal HTTP.
"""
import yfinance as yf
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models import IHSGHistory

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