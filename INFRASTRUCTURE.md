# PRODUCTION INFRASTRUCTURE — Stock Village

**Peran:** Senior Systems Architect · **Tujuan:** rancang arsitektur produksi yang bisa di-scale untuk startup bertumbuh, lalu implementasi minimal yang realistis. **Perilaku produk tidak berubah** — infrastruktur ditambahkan/dirapikan.

---

## 1. System Architecture

```
                        ┌─────────────────────────────┐
   Internet ───────────▶│  API GATEWAY (nginx :80)    │
   (CDN opsional di    │  - TLS termination (prod)   │
    depan aset statis) │  - rate limit per-IP        │
                        │  - gzip · security headers  │
                        └──────┬──────────┬──────────┘
                               │          │
               /               │          │ /api/web/*
        ┌──────▼──────┐        │          └──────────────┐
        │  FRONTEND   │        └──────────────────────┐   │
        │ (statis)    │                               ▼   ▼
        └─────────────┘                     ┌──────────────────────┐
                                            │  BFF (Node/TS :3000) │
                                            │  - agregasi dashboard│
                                            │  - proxy /api/web/*  │
                                            │  - timeout + retry   │
                                            └──────────┬───────────┘
                                                       │
                                            ┌──────────▼───────────┐
                                            │ ihsg-data-service    │
                                            │ (FastAPI :8000)      │
                                            │  - domain modules    │
                                            │  - rate limit        │
                                            │  - circuit breaker   │
                                            └───┬───────┬──────┬───┘
                                                │       │      │
                                      ┌─────────▼──┐ ┌──▼────┐ ┌▼───────────┐
                                      │ PostgreSQL │ │ Redis │ │ providers  │
                                      │ (persist)  │ │cache  │ │ Yahoo/     │
                                      │            │ │+limit │ │ Google/    │
                                      │            │ │+lock  │ │ GoAPI      │
                                      └────────────┘ └───────┘ └────────────┘
```

### Prinsip
1. **Satu pintu masuk** — semua traffic lewat nginx; microservice internal tidak terekspos (location /api/internal/ → 403).
2. **BFF sebagai agregator** — browser hanya bicara ke `/api/web/*`; BFF mengatur 5+ upstream menjadi 1 respons.
3. **Stateless backend** — FastAPI tanpa state sesi; state di Redis/PG → bisa di-scale horizontal (`--workers N` + Redis shared cache).
4. **Degradasi bertingkat** — setiap lapisan punya fallback (stale-cache, simulasi berlabel, fail-open) → tidak pernah error massal saat 1 dependency down.

---

## 2. Component Structure

| Component | Runtime | Peran | Scale unit |
|---|---|---|---|
| api-gateway | nginx | routing, rate-limit edge, gzip, security | +replica di belakang LB |
| frontend | static files | UI (html/css/js) | CDN / object storage |
| web-bff | Node/TS | agregasi + proxy | +replica (stateless) |
| ihsg-data-service | FastAPI (uvicorn) | domain data | +worker (Redis shared) |
| postgres | PG 15 | persistensi history/news/seed | +replica (read) |
| redis | Redis 7 | cache, rate-limit, single-flight lock | +cluster (sentinel) |

---

## 3. Data Flow

### 3.1 Dashboard (paling sering)
```
Browser ──GET /api/web/dashboard?period=1y──▶ BFF
   BFF ── paralel ──▶ ihsg-data-service:
        ├─ /ihsg/realtime        (harga IHSG)
        ├─ /ihsg/history?period  (chart)
        ├─ /news                 (berita real RSS, cache 180s)
        ├─ /sectors              (proksi sektor, cache 60s)
        └─ /sentiment
   BFF ── 1 respons DTO ──▶ Browser (gzip ≥1KB)
```

### 3.2 Real-time polling (30s)
```
Browser ──GET /api/web/ihsg/realtime──▶ BFF ──▶ /ihsg/realtime
   (endpoint ringan 283B; polling pause saat tab hidden)
```

### 3.3 Screener / Stock Pick (mahal)
```
Browser ──GET /api/web/screener/scan──▶ BFF ──▶ FastAPI
   FastAPI: rate-limit(IP) → single-flight(batch lock) → Yahoo batch → cache history
   (N user minta simbol sama = 1 panggilan Yahoo)
```

---

## 4. API Design

### 4.1 Response envelope (konsisten, semua endpoint)
```json
{ "success": true, "message": "...", "data": { ... } }
{ "success": false, "message": "...", "error": "..." }
```
- HTTP: 200 sukses · 400 input · 404 data · 429 rate-limit · 5xx upstream
- Semua angka numerik; label sumber data (source) disertakan untuk transparansi.

### 4.2 Versi & namespace
```
/api/web/*       BFF (browser)      — stabil, breaking-change via versi baru
/api/mobile/*    (cadangan)         — dihapus dari nginx (tidak dipakai)
/api/internal/*  BLOKIR di gateway  — 403 (anti-bypass)
```

### 4.3 Health & readiness
```
GET /healthz   (backend) — liveness: proses hidup
GET /readyz    (backend) — readiness: DB terjangkau (+ opsi cek provider)
GET /healthz   (BFF)     — agregat: ping tiap upstream dengan timeout singkat
```
Kontrak: `200 {"status":"ok","deps":{...}}` atau `503` saat dependency gagal.

---

## 5. Database Schema

### 5.1 Saat ini (models.py — minimal, disengaja)
```sql
ihsg_history      (id, date UNIQUE, open, high, low, close, volume, sma_50, sma_200, rsi_14)
news_articles     (id, title, url UNIQUE, source, sentiment, score, published_at)
sector_performance(id, sector_name UNIQUE, change_percent, last_updated)
```
> Catatan: mayoritas data live TIDAK lewat DB — DB hanya menyimpan history IHSG + seed fallback. Kueri hot di-serve dari Redis.

### 5.2 Indeks yang direkomendasikan (migrasi produksi)
```sql
CREATE INDEX IF NOT EXISTS ix_ihsg_history_date     ON ihsg_history (date);
CREATE INDEX IF NOT EXISTS ix_news_articles_source  ON news_articles (source);
CREATE INDEX IF NOT EXISTS ix_news_published        ON news_articles (published_at);
```

### 5.3 Evolusi (bila fitur tumbuh)
- `users`, `watchlists`, `portfolios` → relasional (PG).
- `audit_log` (siapa akses apa) → append-only, archive ke object storage.
- `provider_calls` (metrik panggilan Yahoo/GoAPI) → tabel counter harian untuk budget & rate.

---

## 6. Caching Strategy

### 6.1 Key namespace & TTL
| Namespace | Contoh key | TTL | Catatan |
|---|---|---|---|
| quote | `quote:BBCA` | 20s | harga saham |
| profile | `profile:BBCA` | 600s | info transaksi+fundamental |
| market | `market:sectors\|marquee\|breadth` | 60s | agregat pasar |
| history | `history:BBCA\|1y` | 600s | frame OHLCV (non-JSON di memory) |
| news | `news:combined` | 180s | RSS gabungan |
| ratelimit | `ratelimit:scan:<ip>` | 60s | counter atomik (INCR) |
| lock | `quote_batch:<symbols>` | — | single-flight (hanya lock, bukan data) |

### 6.2 Aturan
- **Single source of truth** = cache terpusat (`get_cache()`), backend memory/redis via `CACHE_BACKEND`.
- **Single-flight** — 1 fetch per set-simbol untuk N user (thundering herd).
- **Stale-while-revalidate** — saat fetch gagal, sajikan nilai basi (`allow_stale=True`) daripada kosong/error.
- **Redis** untuk produksi multi-worker: quote/profile/market/news/ratelimit (JSON-serializable); history DataFrame tetap di memory per-worker (dilewati Redis dengan log).
- **Rate limit** di edge (nginx `limit_req`) + aplikasi (FastAPI counter atomik) — pertahanan berlapis.

---

## 7. Production-Ready Implementation (yang dibangun sesi ini)

1. **nginx.conf dirapikan** — buang upstream mati (mobile 4000), aktifkan `limit_req` (screener/API), tambah `health_check`, `keepalive` ke upstream, cache header statis, security header tambahan.
2. **docker-compose** — healthcheck untuk postgres/redis/backend/bff, resource limits, restart policy, jalur `.env`.
3. **Backend `/healthz` & `/readyz`** — liveness & readiness (cek DB; opsi cek upstream).
4. **BFF `/healthz` agregat** — ping tiap upstream dengan timeout singkat (memakai `fetchWithTimeout`).
5. **`.env.production.example`** — template env produksi (PG/Redis/CORS/rate-limit/workers).
6. **DB pool tuning** (SQLAlchemy) — pool_size/max_overflow untuk PG produksi; tetap default untuk SQLite dev.
7. **Circuit breaker sederhana untuk provider eksternal** — counter gagal di Redis dengan cooldown (fail-open), mencegah bombardir Yahoo saat rate-limit.

---

## 8. Deployment Path (dev → produksi)

| Tahap | Cara | Catatan |
|---|---|---|
| Dev/Termux | `bash start_all.sh` | SQLite + memory cache + 1 worker |
| VPS kecil | `docker compose up -d` | PG + Redis + 4 worker |
| Scale-up | nginx replica + LB; `WORKERS=8`; CDN untuk aset | Redis shared cache wajib |
| Scale-out | container orchestrator (k8s/compose-swarm) | healthcheck siap; stateless |

---

## 9. Observability & Security (rekomendasi jalan)
- **Log terstruktur** — JSON log di BFF/backend (saat ini print; pindah ke logging lib bila naik kelas).
- **Metrik** — `/metrics` (Prometheus) di BFF: latency per route, error rate, cache hit-ratio.
- **Healthcheck di orchestrator** — `/readyz` sudah siap; pastikan probe `periodSeconds=10, timeoutSeconds=3`.
- **Secrets** — jangan commit `GOAPI_API_KEY`/`DATABASE_URL`; pakai env/secrets manager.
- **TLS** — terminate di gateway (atau LB eksternal); HSTS setelah HTTPS aktif.
- **CORS** — `CORS_ORIGINS` dibatasi domain sendiri di produksi (default `*` hanya dev).
