"""
GOAPI.IO PROVIDER -- Rantai prioritas sumber data: GoAPI.io -> Yahoo Finance ->
pihak ketiga lain (jika ada) -> simulasi/demo.

Modul ini HANYA berisi klien tipis untuk GoAPI.io (https://goapi.io), dipakai
sebagai TIER 1 (prioritas utama) oleh scraper.py sebelum jatuh ke Yahoo Finance
(TIER 2) dan simulasi internal (TIER TERAKHIR, ditangani di frontend).

DESAIN PENTING -- AMAN TANPA API KEY:
Selama GOAPI_API_KEY belum diset di environment (mis. karena user belum
berlangganan), setiap pemanggilan fungsi di modul ini akan LANGSUNG melempar
GoApiUnavailable tanpa pernah melakukan HTTP request sama sekali. Pemanggil
(scraper.py) WAJIB menangkap exception ini dan lanjut ke tier berikutnya --
TIDAK PERNAH membiarkan kegagalan/absennya GoAPI.io menjadi error yang
ditampilkan ke user.
"""

import requests
from typing import Any, Dict, List, Optional

from app.config import settings  # konfigurasi terpusat (default identik)

GOAPI_BASE_URL = settings.goapi_base_url.rstrip("/")
GOAPI_API_KEY = settings.goapi_api_key.strip()
GOAPI_TIMEOUT_SECONDS = 6


class GoApiUnavailable(Exception):
    """
    Dilempar setiap kali GoAPI.io tidak bisa dipakai untuk request ini --
    baik karena API key belum diset, key tidak valid, timeout, error jaringan,
    atau response tidak sesuai format yang diharapkan. Pemanggil HARUS
    menangkap ini dan diam-diam lanjut ke tier fallback berikutnya (Yahoo
    Finance / demo), BUKAN meneruskan sebagai error ke endpoint FastAPI.
    """
    pass


def is_goapi_configured() -> bool:
    """True jika GOAPI_API_KEY sudah diset (tidak kosong)."""
    return bool(GOAPI_API_KEY)


def _goapi_get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Helper request generik ke GoAPI.io. Melempar GoApiUnavailable untuk SEMUA
    jenis kegagalan (key kosong, 401, timeout, network error, JSON tidak
    valid, status bukan "success") supaya pemanggil cukup menangkap satu
    jenis exception saja.
    """
    if not GOAPI_API_KEY:
        raise GoApiUnavailable("GOAPI_API_KEY belum diset (fitur GoAPI.io belum aktif)")

    url = f"{GOAPI_BASE_URL}{path}"
    try:
        resp = requests.get(
            url,
            headers={"X-API-KEY": GOAPI_API_KEY},
            params=params or {},
            timeout=GOAPI_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as e:
        raise GoApiUnavailable(f"GoAPI.io request gagal (network/timeout): {str(e)}")

    if resp.status_code == 401:
        raise GoApiUnavailable("GoAPI.io API key tidak valid atau kedaluwarsa (401 Unauthorized)")
    if resp.status_code == 429:
        raise GoApiUnavailable("GoAPI.io rate limit tercapai (429 Too Many Requests)")
    if resp.status_code >= 400:
        raise GoApiUnavailable(f"GoAPI.io mengembalikan HTTP {resp.status_code}")

    try:
        payload = resp.json()
    except ValueError:
        raise GoApiUnavailable("GoAPI.io mengembalikan response bukan JSON")

    if not isinstance(payload, dict) or payload.get("status") != "success":
        raise GoApiUnavailable(f"GoAPI.io response tidak sukses: {payload.get('message', 'unknown') if isinstance(payload, dict) else 'invalid'}")

    return payload


def get_batch_prices(symbols: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    GET /stock/idx/prices?symbols=A,B,C (maks 50 simbol per request menurut
    dokumentasi GoAPI.io). Mengembalikan dict {symbol: {date, open, high, low,
    close, volume, change, change_pct}}.
    """
    if not symbols:
        return {}
    # Batasi 50 simbol per panggilan sesuai batas resmi GoAPI.io
    symbols = symbols[:50]
    payload = _goapi_get("/stock/idx/prices", {"symbols": ",".join(symbols)})
    raw_list = payload.get("data")
    if isinstance(raw_list, dict):
        raw_list = raw_list.get("results", [])
    if not isinstance(raw_list, list):
        raise GoApiUnavailable("GoAPI.io /stock/idx/prices: format data tidak dikenal")

    results: Dict[str, Dict[str, Any]] = {}
    for item in raw_list:
        sym = item.get("symbol") or item.get("ticker")
        if sym:
            results[sym.upper()] = item
    return results


def get_company_profile(symbol: str) -> Dict[str, Any]:
    """
    GET /stock/idx/{symbol}/profile -- profil perusahaan (sektor, sub-sektor,
    data IPO, dewan komisaris/direksi, pemegang saham). TIDAK berisi rasio
    fundamental siap pakai (EPS/BVPS/PER/PBV) -- untuk itu tetap dipakai
    Yahoo Finance sebagai sumber, GoAPI.io di sini hanya melengkapi profil
    deskriptif perusahaan & (jika tersedia) harga transaksi terakhir.
    """
    payload = _goapi_get(f"/stock/idx/{symbol.upper()}/profile")
    results = payload.get("results") or payload.get("data") or {}
    company_detail = results.get("result") if isinstance(results, dict) else None
    if not company_detail:
        raise GoApiUnavailable(f"GoAPI.io /stock/idx/{symbol}/profile: data profil kosong")
    return company_detail


def get_broker_summary(symbol: str, date: str, investor: str = "ALL") -> List[Dict[str, Any]]:
    """
    GET /stock/idx/{symbol}/broker_summary?date=YYYY-MM-DD&investor=ALL --
    DATA RIIL top broker buyer/seller & net foreign/local flow harian dari
    BEI. Ini satu-satunya sumber RIIL untuk Broker Summary/Bandar Detector
    di aplikasi ini (Yahoo Finance tidak punya data broker summary Indonesia
    sama sekali) -- jika GoAPI.io tidak tersedia, fitur ini WAJIB fallback
    langsung ke simulasi (tidak ada tier Yahoo Finance di antaranya).
    """
    payload = _goapi_get(f"/stock/idx/{symbol.upper()}/broker_summary", {"date": date, "investor": investor})
    data = payload.get("data")
    if isinstance(data, dict):
        rows = data.get("results", [])
    elif isinstance(data, list):
        rows = data
    else:
        rows = []
    if not rows:
        raise GoApiUnavailable(f"GoAPI.io broker_summary untuk {symbol} tanggal {date} kosong")
    return rows


def get_companies() -> List[Dict[str, Any]]:
    """GET /stock/idx/companies -- daftar seluruh emiten IDX (ticker, name, logo)."""
    payload = _goapi_get("/stock/idx/companies")
    data = payload.get("data")
    if isinstance(data, dict):
        return data.get("results", [])
    if isinstance(data, list):
        return data
    raise GoApiUnavailable("GoAPI.io /stock/idx/companies: format data tidak dikenal")
