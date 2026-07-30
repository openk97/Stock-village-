from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
from app.scraper import FinancialNewsScraper
from app.sentiment import IndofinancialSentiment

app = FastAPI(
    title="AI Financial News Sentiment Microservice",
    description="Microservice Python untuk mengikis berita keuangan Indonesia secara real-time dan menganalisis sentimen sentimen AI.",
    version="1.0.0"
)

# CORS Policy
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inisialisasi Analis Sentimen Leksikon Keuangan
sentiment_analyzer = IndofinancialSentiment()

@app.get("/")
def read_root():
    return {
        "service": "AI News Sentiment Analysis Service",
        "status": "online",
        "endpoints": {
            "GET /api/news": "Mengambil berita terbaru dan menganalisis sentimen AI",
            "POST /api/news/analyze": "Menganalisis sentimen teks kustom secara instan",
            "GET /api/sentiment": "Menghitung skor indeks sentimen pasar (Fear & Greed)"
        }
    }

@app.get("/api/news", response_model=List[Dict[str, Any]])
def get_scraped_and_analyzed_news():
    """
    Mengambil berita finansial terkini melalui scraper dan menganalisis setiap judul
    berita secara asinkron menggunakan mesin AI sentimen finansial.
    """
    try:
        raw_news = FinancialNewsScraper.scrape_cnbc_indonesia()
        analyzed_news = []
        
        for idx, item in enumerate(raw_news):
            # Analisis sentimen terhadap judul berita
            analysis = sentiment_analyzer.analyze_headline(item["title"])
            
            analyzed_news.append({
                "id": idx + 1,
                "title": item["title"],
                "url": item["url"],
                "source": item["source"],
                "published_at": item["published_at"],
                "sentiment": analysis["sentiment"],
                "score": float(analysis["score"]),
                "details": {
                    "matched_positives": analysis["matched_positives"],
                    "matched_negatives": analysis["matched_negatives"]
                }
            })
            
        return analyzed_news
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal mengikis dan menganalisis berita: {str(e)}")

@app.post("/api/news/analyze")
def analyze_custom_text(payload: Dict[str, str] = Body(..., example={"text": "IHSG anjlok drastis imbas resesi global"})):
    """
    Endpoint untuk menganalisis teks judul keuangan kustom secara instan.
    """
    text = payload.get("text")
    if not text:
        raise HTTPException(status_code=400, detail="Masukkan teks judul yang ingin dianalisis.")
        
    analysis = sentiment_analyzer.analyze_headline(text)
    return analysis

@app.get("/api/sentiment")
def calculate_fear_and_greed_score():
    """
    Menghitung skor indeks Fear & Greed pasar modal berdasarkan sentimen agregat berita bursa terbaru.
    """
    try:
        raw_news = FinancialNewsScraper.scrape_cnbc_indonesia()
        if not raw_news:
            return {"sentiment_label": "Neutral", "score": 50}
            
        scores = []
        for item in raw_news:
            analysis = sentiment_analyzer.analyze_headline(item["title"])
            scores.append(analysis["score"])
            
        avg_score = sum(scores) / len(scores) if scores else 0.0
        
        # Konversi skala dari [-1.0 s/d 1.0] ke rentang [0 s/d 100]
        sentiment_score = int(((avg_score + 1.0) / 2.0) * 80) + 10
        
        if sentiment_score >= 70:
            label = "Greed"
        elif sentiment_score <= 30:
            label = "Fear"
        else:
            label = "Neutral"
            
        return {
            "sentiment_label": label,
            "score": sentiment_score,
            "average_sentiment_raw": round(avg_score, 2),
            "total_news_analyzed": len(raw_news)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gagal menghitung skor sentimen agregat: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8002, reload=True)
