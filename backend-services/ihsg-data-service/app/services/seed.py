"""
seed.py — Data: seed awal (berita demo & sektor) saat DB kosong.

CLEAN ARCHITECTURE: dipisah dari god-class scraper.py. Data demo jujur
(ditandai simulasi di frontend); hanya dipakai saat sumber riil tidak ada.
"""
from sqlalchemy.orm import Session
from app.models import NewsArticle, SectorPerformance

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
