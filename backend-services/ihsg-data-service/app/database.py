from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.config import settings

# Menggunakan SQLite secara default untuk kemudahan development lokal,
# namun bisa diganti dengan database PostgreSQL produksi melalui env variable.
# Nilai default IDENTIK dengan sebelumnya (os.getenv langsung) -- hanya sumbernya
# dipindah ke config.py agar konfigurasi terpusat (quick win refactor).
DATABASE_URL = settings.database_url

# Menyesuaikan argumen koneksi khusus untuk SQLite jika digunakan.
# PERF/SQLITE: WAL mode memungkinkan reader berjalan paralel dengan writer
# (mengurangi lock contention di dev/self-host/Termux); busy_timeout mencegah
# "database is locked" saat ada writer aktif. Produksi tetap PostgreSQL.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["timeout"] = 15  # busy_timeout = 15 detik menunggu lock DB

# POOL TUNING (produksi PostgreSQL): koneksi pooling yang wajar untuk beberapa
# worker. pool_size=10 per worker + max_overflow=10 -> maks ~20 koneksi/worker;
# sesuaikan dengan max_connections PostgreSQL & jumlah worker.
# SQLite tidak mendukung pooling (gunakan NullPool).
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args=connect_args)
else:
    engine = create_engine(
        DATABASE_URL,
        connect_args=connect_args,
        pool_size=int(settings.db_pool_size),
        max_overflow=int(settings.db_max_overflow),
        pool_pre_ping=True,   # cek koneksi sebelum pakai (hindari stale connection)
        pool_recycle=1800,    # recycle koneksi 30 menit (hindari timeout LB/DB)
    )

if DATABASE_URL.startswith("sqlite"):
    from sqlalchemy import event
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=15000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency untuk mendapatkan DB Session di endpoint FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
