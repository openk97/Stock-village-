"""Unit test: klasifikasi sentimen berita (app/services/news_provider.py)."""
from app.services.news_provider import _classify_sentiment


def test_positive_headline():
    label, score = _classify_sentiment("IHSG melonjak, laba bank naik tajam, pasar optimis")
    assert label == "Positive"
    assert score > 0


def test_negative_headline():
    label, score = _classify_sentiment("Saham anjlok, emiten rugi besar, resesi mengancam")
    assert label == "Negative"
    assert score < 0


def test_neutral():
    label, score = _classify_sentiment("Rapat umum pemegang saham dijadwalkan minggu depan")
    assert label == "Neutral"


def test_negation_flips():
    # "tidak turun" -> bukan negatif
    label, _ = _classify_sentiment("IHSG tidak turun hari ini")
    assert label != "Negative"
