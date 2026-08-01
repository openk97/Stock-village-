from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from app.database import engine, Base, get_db
from app.models import NewsArticle, SectorPerformance, IHSGHistory
from app.services.scraper import IHSGScraper
from app.services.screener import analyze_strategy, scan_strategy, build_stockpick, LIQUID_UNIVERSE

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

@app.get("/api/datasource/status", response_model=Dict[str, Any])
def get_datasource_status():
    """
    Status rantai prioritas sumber data saat ini: GoAPI.io -> Yahoo Finance ->
    simulasi/demo. Dipakai frontend untuk menampilkan status koneksi provider
    secara jujur (mis. badge sidebar "Live DB Connected (Yfinance)" vs
    "(GoAPI.io + Yfinance)"), TANPA pernah mengklaim GoAPI.io aktif jika API
    key belum diset.
    """
    from app.services import goapi_provider
    return {
        "goapi_configured": goapi_provider.is_goapi_configured(),
        "yfinance_available": True,
        "priority_chain": ["goapi_io", "yahoo_finance", "simulasi_internal"]
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
    Mengambil berita finansial terkini.

    PRIORITAS SUMBER (sesuai permintaan user: yfinance & google):
      1. REAL: RSS Yahoo Finance (headline per saham) + RSS Google News (bahasa
         Indonesia) -- diambil langsung, tanpa API key. Sentimen diklasifikasi
         heuristik (kamus kata), labelnya "Deteksi Otomatis (Heuristik)".
      2. FALLBACK: berita ter-seed di Database (simulasi internal demo) jika
         kedua sumber di atas gagal/offline.
    """
    # 1) Coba sumber real terlebih dahulu
    try:
        from app.services.news_provider import fetch_combined_news
        real_news = fetch_combined_news(limit=8)
        if real_news:
            # Tambahkan id urut agar kompatibel dengan DTO lama
            for i, n in enumerate(real_news, start=1):
                n["id"] = i
            return real_news
    except Exception as e:
        print(f"[news] Provider Yahoo/Google gagal, fallback ke DB seed: {e}")

    # 2) Fallback ke data seed (simulasi internal)
    articles = db.query(NewsArticle).order_by(NewsArticle.id.asc()).all()
    return [
        {
            "id": a.id,
            "title": a.title,
            "url": a.url,
            "source": a.source,
            "sentiment": a.sentiment,
            "score": a.score,
            "published_at": a.published_at,
            "data_source": "simulasi"
        }
        for a in articles
    ]

@app.get("/api/sectors", response_model=List[Dict[str, Any]])
def get_sectors(db: Session = Depends(get_db)):
    """
    Performa 11 sektor IDX.

    PRIORITAS: hitung RIIL (rata-rata % perubahan harga konstituen dari
    Yahoo Finance) -> jika konstituen gagal semua, fallback ke data
    ter-seed di DB (simulasi internal, frontend wajib memberi label jujur).
    """
    try:
        real = IHSGScraper.get_sector_performance()
        # frontend memakai field sector_name & change_percent; sektor tanpa
        # data riil diberi change_percent None agar tampil "n/a" jujur
        return [
            {"sector_name": r["sector_name"], "change_percent": r["change_percent"],
             "source": r["source"] if r.get("change_percent") is not None else "simulasi"}
            for r in real
        ]
    except Exception as e:
        print(f"[sectors] Real gagal, fallback DB seed: {e}")

    sectors = db.query(SectorPerformance).order_by(SectorPerformance.change_percent.desc()).all()
    return [
        {
            "sector_name": s.sector_name,
            "change_percent": s.change_percent,
            "source": "simulasi"
        }
        for s in sectors
    ]


@app.get("/api/market/marquee", response_model=List[Dict[str, Any]])
def get_market_marquee():
    """Quote RIIL ticker makro/komoditas/global untuk marquee atas (Yahoo Finance)."""
    return IHSGScraper.get_macro_quotes()


@app.get("/api/market/breadth", response_model=Dict[str, Any])
def get_market_breadth():
    """Market breadth (naik/tetap/turun) dari quote RIIL universe saham likuid."""
    return IHSGScraper.get_market_breadth()

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

@app.get("/api/stocks/profile", response_model=Dict[str, Any])
def get_stock_profile(
    symbol: str = Query(..., description="Kode saham tunggal, contoh: BBCA")
):
    """
    Profil lengkap satu saham untuk halaman Detail Saham: info transaksi
    harian (open/high/low/prev close/volume/avg volume/52-week range/market
    cap) DAN fundamental riil (PER/PBV/EPS/BVPS) dari Yahoo Finance -- bukan
    simulasi. Field yang tidak tersedia di Yahoo Finance dikembalikan null.
    """
    symbol = (symbol or "").strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="Parameter 'symbol' tidak boleh kosong.")
    try:
        data = IHSGScraper.get_stock_profile(symbol)
        return data
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gagal mengambil profil saham {symbol} dari Yahoo Finance: {str(e)}")

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


# ============================================================================
# SCREENER BERBASIS SINYAL RIIL (indikator dihitung dari data Yahoo Finance)
# ============================================================================
@app.get("/api/screener/analyze", response_model=Dict[str, Any])
def screener_analyze(symbol: str, strategy: str = "teknikal"):
    """
    Menganalisis SATU saham untuk satu strategi, dengan indikator RIIL
    (SMA/RSI/MACD/volume/momentum) yang dihitung dari riwayat harga
    Yahoo Finance. Tidak ada angka hash/simulasi.
    """
    if not symbol.strip():
        raise HTTPException(status_code=400, detail="Parameter 'symbol' tidak boleh kosong.")
    row = analyze_strategy(symbol.strip().upper(), strategy)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Data riil untuk {symbol} tidak tersedia (offline/simbol tidak dikenal).")
    return row


@app.get("/api/screener/scan", response_model=List[Dict[str, Any]])
def screener_scan(strategy: str = "teknikal", symbols: str = ""):
    """
    Memindai daftar saham (koma terpisah) untuk satu strategi memakai sinyal
    riil. Jika symbols kosong, memakai universe saham likuid terkurasi.
    CATATAN JUJUR: memindai universe likuid (bukan seluruh 951 emiten) karena
    keterbatasan sumber data & kecepatan -- frontend wajib menyebut ini.
    """
    if symbols.strip():
        sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    else:
        sym_list = LIQUID_UNIVERSE
    if not sym_list:
        return []
    return scan_strategy(strategy, sym_list)


@app.get("/api/screener/stockpick", response_model=Dict[str, Any])
def screener_stockpick(mode: str = "harian", symbols: str = ""):
    """
    Stock Pick berbasis sinyal riil: harian (momentum hari ini + volume) atau
    swing (uptrend harga > SMA20 > SMA50 + momentum). Narasi memakai angka
    riil yang dihitung server. Universe default = saham likuid.
    """
    mode = mode if mode in ("harian", "swing") else "harian"
    if symbols.strip():
        sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    else:
        sym_list = LIQUID_UNIVERSE
    return build_stockpick(mode, sym_list)


if __name__ == "__main__":

    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
