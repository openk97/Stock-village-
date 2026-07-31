from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from app.database import engine, Base, get_db
from app.models import NewsArticle, SectorPerformance, IHSGHistory
from app.services.scraper import IHSGScraper

# Inisialisasi Tabel Database SQLite pada saat startup aplikasi
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Stock Village Web Dashboard API",
    description="API Komprehensif terintegrasi database untuk menyajikan data IHSG, Berita Sentimen, & Performa Sektoral.",
    version="2.0.0"
)

# CORS Policy untuk komunikasi lancar dengan Next.js Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Seeding data awal saat aplikasi pertama kali dinyalakan
@app.on_event("startup")
def startup_populate_data():
    db = next(get_db())
    try:
        # Lakukan sinkronisasi data bursa dasar jika database kosong
        print("Initializing database and seeding default news & sectors...")
        IHSGScraper.seed_initial_data(db)
        
        # Prefetch historical data untuk mempercepat respon pertama
        print("Prefetching and syncing historical data with Database...")
        IHSGScraper.fetch_and_sync_history(db, period="1y")
        print("Database initialization successfully complete!")
    except Exception as e:
        print(f"Error seeding startup data: {str(e)}")

@app.get("/")
def read_root():
    return {
        "status": "online",
        "message": "Welcome to IHSG Comprehensive Database-backed API. Swagger docs available at /docs."
    }

@app.get("/api/ihsg/realtime", response_model=Dict[str, Any])
def get_ihsg_realtime():
    """
    Mengambil data real-time / delayed 15 menit dari IHSG (Yahoo Finance).
    """
    data = IHSGScraper.get_realtime_status()
    if not data:
        raise HTTPException(status_code=500, detail="Gagal mengambil data real-time.")
    return data

@app.get("/api/ihsg/history", response_model=List[Dict[str, Any]])
def get_ihsg_history(
    period: str = Query("1y", description="Periode data historis (e.g., 5d, 1mo, 3mo, 6mo, 1y, 5y)"),
    db: Session = Depends(get_db)
):
    """
    Mengambil data historis IHSG dari Database lokal (disinkronisasikan berkala dengan Yahoo Finance).
    Otomatis menyertakan indikator teknikal SMA 50, SMA 200, dan RSI 14.
    """
    data = IHSGScraper.fetch_and_sync_history(db, period=period)
    if not data:
        raise HTTPException(status_code=500, detail="Gagal mengambil data historis dari bursa.")
    return data

@app.get("/api/news", response_model=List[Dict[str, Any]])
def get_news(db: Session = Depends(get_db)):
    """
    Mengambil berita finansial terkini lengkap beserta analisis sentimen AI dari Database.
    """
    articles = db.query(NewsArticle).order_by(NewsArticle.id.asc()).all()
    return [
        {
            "id": a.id,
            "title": a.title,
            "url": a.url,
            "source": a.source,
            "sentiment": a.sentiment,
            "score": a.score,
            "published_at": a.published_at
        }
        for a in articles
    ]

@app.get("/api/sectors", response_model=List[Dict[str, Any]])
def get_sectors(db: Session = Depends(get_db)):
    """
    Mengambil performa sektoral Bursa Efek Indonesia (IDX) harian dari Database.
    """
    sectors = db.query(SectorPerformance).order_by(SectorPerformance.change_percent.desc()).all()
    return [
        {
            "sector_name": s.sector_name,
            "change_percent": s.change_percent
        }
        for s in sectors
    ]

@app.get("/api/sentiment", response_model=Dict[str, Any])
def get_market_sentiment(db: Session = Depends(get_db)):
    """
    Menghitung skor indeks ketakutan & ketamakan (Fear & Greed Index) berdasarkan analisis sentimen berita bursa terbaru.
    """
    articles = db.query(NewsArticle).all()
    if not articles:
        return {"sentiment_label": "Neutral", "score": 50}
    
    # Hitung rata-rata sentimen berita (-1.0 s/d 1.0) dikonversikan ke skala 0 s/d 100
    total_score = sum(a.score for a in articles)
    avg_score = total_score / len(articles) # range: -1.0 s/d 1.0
    
    # Konversi skala: -1.0 -> 10 (Extreme Fear), 0.0 -> 50 (Neutral), 1.0 -> 90 (Extreme Greed)
    sentiment_score = int(((avg_score + 1.0) / 2.0) * 80) + 10
    
    if sentiment_score >= 70:
        label = "Greed"
    elif sentiment_score <= 30:
        label = "Fear"
    else:
        label = "Neutral"
        
    return {
        "sentiment_label": label,
        "score": sentiment_score
    }

@app.get("/api/stocks/quotes", response_model=List[Dict[str, Any]])
def get_stock_quotes(
    symbols: str = Query(..., description="Daftar kode saham dipisah koma, contoh: BBCA,BBRI,TLKM")
):
    """
    Mengambil kutipan harga real-time/delayed untuk banyak saham individual
    sekaligus dari Yahoo Finance (dipakai oleh Watchlist & Portofolio agar
    harga yang ditampilkan adalah data pasar sungguhan, bukan simulasi acak).
    """
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        raise HTTPException(status_code=400, detail="Parameter 'symbols' tidak boleh kosong.")

    data = IHSGScraper.get_stock_quotes(symbol_list)
    return data

@app.get("/api/correlation/matrix", response_model=Dict[str, Any])
def get_correlation_matrix(
    symbols: str = Query(..., description="Daftar kode saham dipisah koma, contoh: BBCA,BBRI,TLKM"),
    period: str = Query("1y", description="Periode data historis untuk hitung korelasi (e.g., 3mo, 6mo, 1y, 2y)"),
    method: str = Query("pearson", description="Metode korelasi: 'pearson' (default, standar untuk return) atau 'spearman' (rank, tahan outlier)")
):
    """
    Menghitung matrix korelasi return harian sejumlah saham terhadap faktor
    makro/komoditas/global inti (IHSG, Kurs USD/IDR, Emas, Brent, Nasdaq),
    berdasarkan data historis real Yahoo Finance.
    """
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        raise HTTPException(status_code=400, detail="Parameter 'symbols' tidak boleh kosong.")

    data = IHSGScraper.get_correlation_matrix(symbol_list, period=period, method=method)
    return data

@app.get("/api/correlation/detail", response_model=Dict[str, Any])
def get_correlation_detail(
    symbol: str = Query(..., description="Kode saham, contoh: BBCA"),
    period: str = Query("1y", description="Periode data historis untuk hitung korelasi (e.g., 3mo, 6mo, 1y, 2y)"),
    peers: str = Query("", description="Daftar kode saham pembanding (peer) dipisah koma, opsional"),
    method: str = Query("pearson", description="Metode korelasi: 'pearson' (default, standar untuk return) atau 'spearman' (rank, tahan outlier)")
):
    """
    Menghitung detail korelasi 1 saham terhadap seluruh faktor makro/komoditas
    /indeks global, sektor proksinya, dan sejumlah saham peer, berdasarkan data
    historis real Yahoo Finance (bukan simulasi).
    """
    if not symbol.strip():
        raise HTTPException(status_code=400, detail="Parameter 'symbol' tidak boleh kosong.")

    peer_list = [p.strip().upper() for p in peers.split(",") if p.strip()]
    data = IHSGScraper.get_correlation_detail(symbol, period=period, peers=peer_list, method=method)
    return data

@app.get("/api/correlation/leadlag", response_model=Dict[str, Any])
def get_correlation_leadlag(
    asset_a: str = Query(..., description="Kode aset pertama (saham atau kunci faktor, mis. BBCA atau brent)"),
    asset_a_type: str = Query("stock", description="'stock' atau 'factor'"),
    asset_b: str = Query(..., description="Kode aset kedua (saham atau kunci faktor)"),
    asset_b_type: str = Query("stock", description="'stock' atau 'factor'"),
    period: str = Query("1y", description="Periode data historis"),
    max_lag: int = Query(10, description="Jumlah hari maksimum yang diuji untuk efek jeda waktu (lag), 1-20")
):
    """
    Menghitung Cross-Correlation Function (CCF) / analisis lead-lag antara 2
    aset (saham atau faktor makro/komoditas/global), untuk menguji apakah
    salah satu variabel baru memengaruhi variabel lain setelah jeda waktu
    tertentu (mis. harga minyak dunia hari ini vs saham maskapai 2 hari
    kemudian). Data historis real Yahoo Finance (bukan simulasi).
    """
    if not asset_a.strip() or not asset_b.strip():
        raise HTTPException(status_code=400, detail="Parameter 'asset_a' dan 'asset_b' tidak boleh kosong.")

    data = IHSGScraper.get_lead_lag_analysis(
        asset_a, asset_a_type, asset_b, asset_b_type, period=period, max_lag=max_lag
    )
    return data

@app.get("/api/analysis/wyckoff", response_model=Dict[str, Any])
def get_wyckoff_vpa_analysis(
    symbol: str = Query(..., description="Kode saham, contoh: BBCA"),
    period: str = Query("6mo", description="Periode data historis (e.g., 3mo, 6mo, 1y)")
):
    """
    Menjalankan deteksi heuristik Wyckoff (Trading Range, Spring, Sign of
    Strength) dan VPA (Selling/Buying Climax, Volume Spike) pada data harga
    historis REAL dari Yahoo Finance.

    PENTING (kejujuran metodologi): Wyckoff Method & VPA pada dasarnya
    interpretatif (dibaca manusia dari bentuk chart), bukan rumus matematika
    baku. Endpoint ini menerapkan aturan kuantitatif heuristik yang mendekati
    logika tsb, BUKAN analisis pasti seorang ahli -- hasil harus dilabeli
    "Deteksi Otomatis (Heuristik)" di sisi klien, bukan "Live DB" definitif.
    """
    if not symbol.strip():
        raise HTTPException(status_code=400, detail="Parameter 'symbol' tidak boleh kosong.")

    data = IHSGScraper.analyze_wyckoff_vpa(symbol, period=period)
    return data

if __name__ == "__main__":

    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
