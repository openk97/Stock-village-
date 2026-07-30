from sqlalchemy import Column, Integer, Float, String, DateTime, UniqueConstraint
from datetime import datetime
from app.database import Base

class IHSGHistory(Base):
    __tablename__ = "ihsg_history"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(String, unique=True, index=True, nullable=False)  # format: YYYY-MM-DD
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    sma_50 = Column(Float, nullable=True)
    sma_200 = Column(Float, nullable=True)
    rsi_14 = Column(Float, nullable=True)

class NewsArticle(Base):
    __tablename__ = "news_articles"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    url = Column(String, unique=True, nullable=False)
    source = Column(String, nullable=False)  # e.g., CNBC Indonesia, Kontan
    sentiment = Column(String, nullable=False)  # Positive, Neutral, Negative
    score = Column(Float, nullable=False)  # sentiment score e.g., 0.85
    published_at = Column(String, nullable=False)

class SectorPerformance(Base):
    __tablename__ = "sector_performance"

    id = Column(Integer, primary_key=True, index=True)
    sector_name = Column(String, unique=True, nullable=False)  # e.g., Financials, Infrastructure
    change_percent = Column(Float, nullable=False)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
