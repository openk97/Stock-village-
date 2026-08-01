"""
news_provider.py
================
Provider berita keuangan REAL untuk Stock Village.

Sumber (keduanya RSS publik, TANPA API key, stabil & legal):
  1. Yahoo Finance RSS headline  -> https://feeds.finance.yahoo.com/rss/2.0/headline?s=<TICKER.JK>
  2. Google News RSS (Indonesia)  -> https://news.google.com/rss/search?q=<query>&hl=id&gl=ID&ceid=ID:id

Setiap judul diklasifikasi sentimen dengan HEURISTIK kamus kata (bahasa Indonesia
dan Inggris) yang TIDAK diklaim sebagai AI -- labelnya selalu "Deteksi Otomatis
(Heuristik)" di sisi frontend. Jika kedua sumber gagal/offline, pemanggil wajib
fallback ke data simulasi internal (lihat main.py /api/news).

Format item yang dikembalikan:
{
  "title": str,
  "url": str,
  "source": str,          # nama portal asal (Bisnis.com, Yahoo Finance, dll)
  "provider": "yahoo_finance" | "google_news",
  "published_at": str,    # ISO 8601 UTC (atau "" jika tak terurai)
  "sentiment": "Positive" | "Neutral" | "Negative",
  "score": float,         # -1.0 .. 1.0 (heuristik)
  "data_source": "yahoo_google_news"
}
"""

import re
import requests
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET
from typing import List, Dict, Any, Optional, Tuple

from app.config import settings

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 15

# --- Kamus sentimen (ID + EN) ---
POSITIVE_WORDS = {
    "laba", "untung", "naik", "lonjak", "menguat", "tumbuh", "rekor", "melesat",
    "surplus", "dividen", "akuisisi", "investasi", "optimis", "bullish", "hijau",
    "meningkat", "positif", "buy", "beli", "akumulasi", "moncer", "cerah", "melaju",
    "stimulus", "pelonggaran", "sukses", "melampaui", "ekspansi", "kuat", "terbang",
    "naikkan", "gain", "profit", "growth", "rally", "surge", "record", "boost",
    "outperform", "upgrade", "beat", "prospek", "geber", "borong", "berlanjut",
    "penguatan", "kejar", "top", "cuan", "cemerlang", "gemilang", "kinclong",
    "diskon", "all time high", "ath", "melesat", "meroket", "terbang", "cetak rekor",
    "membaik", "pulih", "subur", "prospektif", "menanjak", "menggairahkan", "stabil",
    "kuatkan", "unggul", "andal", "rekomendasi", "beli", "net buy", "mengakuisisi"
}
NEGATIVE_WORDS = {
    "rugi", "turun", "anjlok", "lemah", "tertekan", "ambruk", "koreksi", "merah",
    "pesimis", "bearish", "defisit", "phk", "bangkrut", "pailit", "denda", "sanksi",
    "gugatan", "pangkas", "susut", "melambat", "sell", "jual", "distribusi", "panik",
    "krisis", "resesi", "macet", "gagal", "naikkan bunga", "suku bunga naik",
    "konflik", "perang", "blokir", "suspend", "delisting", "tutup", "drop", "fall",
    "loss", "downgrade", "underperform", "miss", "terkoreksi", "melemah", "menurun",
    "terpuruk", "jeblok", "runtuh", "tekan", "turunkan", "saham turun", "anjok",
    "waswas", "dilepas", "lepas", "outflow", "red", "weak", "slump", "plunge",
    "terpangkas", "terjun", "jatuh", "melorot", "tumbang", "stagnan", "flat",
    "tertekan", "ambles", "terguling", "penurunan", "kekhawatiran", "risiko",
    "gejolak", "guncangan", "ketidakpastian", "terancam", "dipangkas", "terkoreksi",
    "cuci gudang", "panic selling", "net sell", "jualan", "beban", "tertekan"
}
NEGATIONS = {"tidak", "bukan", "belum", "tanpa", "gagal"}

SYMBOLS_MAIN = ["BBCA", "BBRI", "TLKM", "ASII", "GOTO", "ADRO", "ANTM", "BMRI"]
SYMBOL_SUFFIX = ".JK"


def _classify_sentiment(text: str) -> Tuple[str, float]:
    """Heuristik kamus kata. Mengembalikan (label, skor -1..1)."""
    low = (text or "").lower()
    low_clean = re.sub(r"[^\w\s]", " ", low)
    words = set(w for w in low_clean.split() if w)

    # Frasa khusus
    if "suku bunga naik" in low_clean:
        words.add("suku_bunga_naik")

    pos_hits = sum(1 for w in words if w in POSITIVE_WORDS)
    neg_hits = sum(1 for w in words if w in NEGATIVE_WORDS)

    # Negasi sederhana: "tidak turun" -> positif, "tidak naik" -> negatif
    negated_pos = 0
    negated_neg = 0
    tokens = low_clean.split()
    for i, tok in enumerate(tokens):
        if tok in NEGATIONS and i + 1 < len(tokens):
            nxt = tokens[i + 1]
            if nxt in POSITIVE_WORDS:
                negated_pos += 1
            elif nxt in NEGATIVE_WORDS:
                negated_neg += 1

    pos_hits -= negated_pos
    neg_hits -= negated_neg

    if pos_hits > neg_hits:
        score = min(1.0, 0.35 + 0.15 * (pos_hits - neg_hits))
        return ("Positive", round(score, 2))
    if neg_hits > pos_hits:
        score = max(-1.0, -0.35 - 0.15 * (neg_hits - pos_hits))
        return ("Negative", round(score, 2))
    return ("Neutral", 0.0)


def _parse_rfc822_date(raw: Optional[str]) -> str:
    if not raw:
        return ""
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return ""


def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (title or "").lower())


def fetch_yahoo_news(symbols: List[str], per_symbol: int = 3) -> List[Dict[str, Any]]:
    """Berita per saham dari RSS Yahoo Finance headline feed."""
    items: List[Dict[str, Any]] = []
    for sym in symbols[:8]:
        url = (
            "https://feeds.finance.yahoo.com/rss/2.0/headline"
            f"?s={sym}{SYMBOL_SUFFIX}&region=US&lang=en-US"
        )
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                continue
            root = ET.fromstring(resp.content)
            for item in root.iter("item"):
                title = item.findtext("title", "").strip()
                link = item.findtext("link", "").strip()
                pub = _parse_rfc822_date(item.findtext("pubDate", ""))
                if not title or not link:
                    continue
                if title.startswith("Yahoo!"):
                    continue
                label, score = _classify_sentiment(title)
                items.append({
                    "title": title,
                    "url": link,
                    "source": "Yahoo Finance",
                    "provider": "yahoo_finance",
                    "published_at": pub,
                    "sentiment": label,
                    "score": score,
                    "data_source": "yahoo_google_news",
                })
                if len([i for i in items if i["provider"] == "yahoo_finance"]) >= per_symbol * len(symbols[:8]):
                    break
        except Exception as e:
            print(f"[news_provider] Yahoo RSS {sym} gagal: {e}")
    return items


def fetch_google_news(query: str, limit: int = 5, hl: str = "id", gl: str = "ID") -> List[Dict[str, Any]]:
    """Berita dari Google News RSS (pencarian query)."""
    items: List[Dict[str, Any]] = []
    try:
        url = "https://news.google.com/rss/search"
        resp = requests.get(
            url,
            params={"q": query, "hl": hl, "gl": gl, "ceid": f"{gl}:{hl}"},
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            return items
        root = ET.fromstring(resp.content)
        for item in root.iter("item"):
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            source_raw = item.findtext("source", "") or ""
            # Google News menaruh nama portal di atribut url <source url=...>
            source = re.sub(r"<[^>]+>", "", source_raw).strip() or "Google News"
            pub = _parse_rfc822_date(item.findtext("pubDate", ""))
            if not title or not link or title.startswith("Google Berita"):
                continue
            label, score = _classify_sentiment(title)
            items.append({
                "title": title,
                "url": link,
                "source": source,
                "provider": "google_news",
                "published_at": pub,
                "sentiment": label,
                "score": score,
                "data_source": "yahoo_google_news",
            })
            if len(items) >= limit:
                break
    except Exception as e:
        print(f"[news_provider] Google News RSS gagal: {e}")
    return items


# Cache hasil gabungan berita (TTL 3 menit, via lapisan cache terpusat) --
# QUICK WIN: dashboard polling (tiap 30s) tidak lagi memukul RSS Yahoo/Google.


def fetch_combined_news(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Gabungan Yahoo Finance + Google News:
      - Yahoo: headline per 6 saham utama (maks 3/saham)
      - Google: query "IHSG saham" + 3 saham utama (maks 3/query)
    Dedupe berdasarkan judul normalisasi, urut dari terbaru, batasi `limit`.
    Hasil penuh di-cache 3 menit; `limit` hanya memengaruhi slicing return.
    """
    from app.services.cache import get_cache, TTL
    cached = get_cache().get("news:combined")
    if cached is not None:
        return cached[:limit]

    combined: List[Dict[str, Any]] = []
    combined.extend(fetch_yahoo_news(SYMBOLS_MAIN[:6], per_symbol=2))

    for q in ["IHSG saham", "saham BBCA", "saham BBRI", "saham TLKM", "saham GOTO"]:
        combined.extend(fetch_google_news(q, limit=3))

    # Dedupe
    seen = set()
    unique: List[Dict[str, Any]] = []
    for item in combined:
        key = _normalize_title(item["title"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    # Kuota campuran supaya KEDUA sumber terwakili (bukan hanya yang paling baru):
    # minimal 2 berita Yahoo Finance + sisanya Google News (yang umumnya lebih baru).
    yahoo_sorted = sorted(
        [i for i in unique if i["provider"] == "yahoo_finance"],
        key=lambda x: x.get("published_at") or "", reverse=True
    )
    google_sorted = sorted(
        [i for i in unique if i["provider"] == "google_news"],
        key=lambda x: x.get("published_at") or "", reverse=True
    )

    mixed: List[Dict[str, Any]] = []
    seen2 = set()
    def push(item):
        if item and item["title"] not in seen2:
            seen2.add(item["title"])
            mixed.append(item)
    for y in yahoo_sorted[:2]:
        push(y)
    for g in google_sorted:
        push(g)
        if len(mixed) >= limit:
            break
    if len(mixed) < limit:
        for y in yahoo_sorted[2:]:
            push(y)
            if len(mixed) >= limit:
                break

    # Urutkan hasil akhir dari terbaru ke terlama
    mixed.sort(key=lambda x: x.get("published_at") or "", reverse=True)
    get_cache().set("news:combined", mixed, settings.news_cache_ttl)
    return mixed[:limit]
