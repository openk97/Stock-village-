import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Menggunakan SQLite secara default untuk kemudahan development lokal, 
# namun bisa diganti dengan database PostgreSQL produksi melalui env variable.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ihsg.db")

# Menyesuaikan argumen koneksi khusus untuk SQLite jika digunakan
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency untuk mendapatkan DB Session di endpoint FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
