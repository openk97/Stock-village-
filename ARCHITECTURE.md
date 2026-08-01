# CLEAN ARCHITECTURE — Stock Village

**Peran:** Senior Software Architect · **Tujuan:** pisahkan concern, naikkan modularitas, turunkan coupling, siap scale — **tanpa mengubah perilaku produk**.

> Dokumen ini mendeskripsikan struktur & keputusan arsitektur setelah refactor. Semua perilaku endpoint/UI diverifikasi identik (pytest + Playwright).

---

## 1. Folder Structure Baru

```
Stock-village-/
├── start_all.sh                     # launcher satu perintah (PC/Termux)
├── serve_with_proxy.py              # static server + proxy /api -> BFF (gzip+cache)
├── docker-compose.yml               # prod: postgres + redis + service + gateway
│
├── frontend/                        # PRESENTATION (client)
│   ├── index.html                   # layout + markup (2.034 baris, dulu 10.250)
│   ├── css/styles.css               # tema & komponen (diekstrak dari inline)
│   └── js/
│       ├── lib.js                   # fungsi MURNI (tanpa DOM) — unit-testable
│       └── app.js                   # logika DOM/UI (closure DOMContentLoaded)
│
├── bff-layer/                       # APPLICATION LAYER (BFF)
│   ├── config.ts                    # konfigurasi terpusat (URL, timeout, port)
│   ├── server.ts                    # bootstrap + middleware (gzip)
│   └── web-bff/
│       ├── web.routes.ts            # presentation: routing HTTP
│       ├── web.controller.ts        # presentation: parse request/response
│       ├── web.service.ts           # application: agregasi & proxy upstream
│       └── web.dto.ts               # contract: tipe data antar lapisan
│
└── backend-services/
    ├── ihsg-data-service/           # CORE DOMAIN + INFRA (FastAPI)
    │   ├── app/
    │   │   ├── main.py              # presentation: routes (thin)
    │   │   ├── config.py            # configuration
    │   │   ├── database.py          # infra: DB engine (SQLite WAL / PG)
    │   │   ├── models.py            # infra: ORM
    │   │   └── services/            # DOMAIN + INFRA SERVICES
    │   │       ├── cache.py         # infra: cache terpusat (memory/redis) + lock
    │   │       ├── rate_limit.py    # infra: rate limiter atomik
    │   │       ├── quotes.py        # domain: kutipan & profil (tiered provider)
    │   │       ├── history.py       # domain: riwayat IHSG & realtime
    │   │       ├── market.py        # domain: sektor heatmap, marquee, breadth
    │   │       ├── correlation.py   # domain: mesin korelasi + konstanta
    │   │       ├── wyckoff.py       # domain: heuristik Wyckoff/VPA
    │   │       ├── screener.py      # domain: mesin screener sinyal riil
    │   │       ├── seed.py          # data: seed demo (jujur berlabel)
    │   │       ├── news_provider.py # domain: berita Yahoo+Google (heuristik)
    │   │       ├── goapi_provider.py# infra: provider GoAPI (opsional)
    │   │       └── scraper.py       # FACADE: kompatibilitas IHSGScraper
    │   └── tests/                   # unit test (25 test, fungsi murni)
    └── (archive/news-service)       # diarsipkan (berita pindah ke core)
```

---

## 2. Clean Architecture Breakdown (per lapisan)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ PRESENTATION (bisa diganti tanpa menyentuh domain)                      │
│   frontend/  ·  bff/web-bff/{routes,controller}  ·  app/main.py         │
│   = routing, parse request/response, render UI. TIDAK berisi logika     │
│     bisnis; hanya meneruskan ke application/domain.                     │
├─────────────────────────────────────────────────────────────────────────┤
│ APPLICATION (orchestrasi use-case)                                      │
│   bff/web-bff/web.service.ts  ·  app/main.py (aggregasi dashboard)      │
│   = memanggil beberapa domain service & menyusun respons DTO.           │
├─────────────────────────────────────────────────────────────────────────┤
│ DOMAIN (inti bisnis, framework-agnostic)                                │
│   app/services/{quotes,history,market,correlation,wyckoff,screener,     │
│   news_provider,seed}.py                                                │
│   = logika data & analisis murni; bergantung pada infra abstrak         │
│     (cache, provider) — bukan pada FastAPI/Express.                     │
├─────────────────────────────────────────────────────────────────────────┤
│ INFRASTRUCTURE (bisa ditukar: Yahoo↔GoAPI, memory↔Redis, SQLite↔PG)     │
│   app/services/{cache,rate_limit,goapi_provider}.py  ·  database.py     │
│   = caching, rate limit, provider eksternal, DB engine.                 │
└─────────────────────────────────────────────────────────────────────────┘
```

**Aliran dependensi:** presentation → application → domain → infrastructure.
Domain **tidak pernah** mengimpor presentation. Infra **dapat ditukar** tanpa
mengubah domain (mis. `CACHE_BACKEND=redis` memakai RedisCache yang sama
interface-nya dengan MemoryCache).

---

## 3. Refactored Production-Grade Code (contoh kunci)

### 3.1 Facade — god class dipecah, perilaku dipertahankan
`scraper.py` dulu **1.274 baris** mencampur 6 tanggung jawab. Kini:

```python
# app/services/scraper.py — FACADE TIPIS (89 baris)
from app.services.quotes import get_stock_quotes, get_stock_profile
from app.services.market import (SECTOR_BASKETS, MARQUEE_TICKERS,
                                 get_sector_performance, get_macro_quotes, get_market_breadth)
from app.services.correlation import (STOCK_SECTOR_MAP, get_correlation_matrix, ...)
from app.services.wyckoff import analyze_wyckoff_vpa
from app.services.seed import seed_initial_data

class IHSGScraper:
    """Facade — delegasi murni; main.py & test lama TIDAK berubah."""
    SECTOR_BASKETS = SECTOR_BASKETS
    get_stock_quotes = staticmethod(get_stock_quotes)
    get_sector_performance = staticmethod(get_sector_performance)
    get_correlation_matrix = staticmethod(get_correlation_matrix)
    analyze_wyckoff_vpa = staticmethod(analyze_wyckoff_vpa)
    # ... dst (semua metode ekspos)
```

### 3.2 Modul domain — satu tanggung jawab, dependensi eksplisit
```python
# app/services/quotes.py — DOMAIN: kutipan & profil
# Bergantung pada: cache (infra), goapi_provider (infra).
# Tidak tahu soal FastAPI/Express/HTTP routing.
def get_stock_quotes(symbols): ...        # GoAPI -> Yahoo -> stale-cache (single-flight)
def get_stock_profile(symbol): ...

# app/services/market.py — DOMAIN: data pasar agregat
from app.services.quotes import get_stock_quotes   # dependensi domain->domain
def get_sector_performance(): ...                  # 1 batch untuk semua konstituen
def get_macro_quotes(): ...
def get_market_breadth(): ...

# app/services/correlation.py — DOMAIN: engine korelasi
from app.services.market import SECTOR_BASKETS     # konstanta berasal dari market
def get_correlation_matrix(...): ...
def get_lead_lag_analysis(...): ...
```

### 3.3 Infra abstrak — cache & provider bisa ditukar
```python
# app/services/cache.py — INFRA: satu interface, dua backend
cache = get_cache()          # MemoryCache | RedisCache (via CACHE_BACKEND)
cache.get(key) / set(key, value, ttl) / increment(key, ttl)   # antarmuka sama
# app/services/goapi_provider.py — INFRA: provider opsional; gagal -> fallback Yahoo
```

---

## 4. Explanation of Architectural Improvements

| Aspek | Sebelum | Sesudah |
|---|---|---|
| **Separation of concerns** | `scraper.py` god class 1.274 baris: provider+cache+market+korelasi+wyckoff+seed+history | 7 modul domain fokus (maks 373 baris) + infra (cache/rate_limit) + facade 89 baris |
| **Modularity** | logika terkunci di satu file → sulit diuji/dirawat | tiap modul bisa diuji sendiri; `tests/` menutup fungsi murni |
| **Coupling** | `screener.py` sempat impor cache dari scraper; main.py memanggil god class | dependensi eksplisit & acyclic: market→quotes, correlation→market, wyckoff→correlation; presentation hanya memanggil facade/domain |
| **Scalability** | 1 worker, cache memory terpisah | cache/rate-limit Redis-ready; `WORKERS` env; docker-compose 4 worker + Redis |
| **Maintainability** | god class = "jangan sentuh" | facade menjaga kompatibilitas; modul baru tinggal ditambah tanpa menyentuh main.py |
| **Behavior** | — | **Identik**: 25/25 pytest, semua endpoint 200, Playwright 7/7, 0 JS error |

### Keputusan arsitektur penting
1. **Facade, bukan rewrite total** — menjaga `main.py` & test lama tetap valid → risiko migrasi ≈ 0, nilai refactor langsung terasa.
2. **Infra terisolasi** — ganti Yahoo↔GoAPI atau memory↔Redis tanpa menyentuh domain.
3. **Konstanta satu sumber** — `SECTOR_BASKETS` di `market.py`; `correlation.py` menurunkannya (tak ada lagi duplikasi sektor).
4. **Presentation tipis** — `main.py` & controller BFF hanya parse & delegasi; semua logika di domain.
5. **Test sebagai jaring** — `tests/` (25) + frontend `lib.test.js` + Playwright → refactor berikutnya aman.

### Sisa yang bisa dilanjutkan
- Pindahkan `app/services/screener.py` internals ke sub-modul bila tumbuh (sudah 590 baris).
- Pisahkan provider Yahoo menjadi `providers/yahoo.py` bila menambah sumber lain.
- Frontend: modularisasi `app.js` (7.000 baris) per-view — langkah jangka panjang berikutnya.
