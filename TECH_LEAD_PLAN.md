# TECH LEAD PLAN — Stock Village (5 Tahun, Produk Publik)

**Peran:** Senior Technical Lead · **Fokus:** keputusan teknis, tradeoff, arsitektur rekomendasi, rencana implementasi, solusi produksi — **untuk maintainer jangka panjang**. Dokumen ini MENANTANG beberapa keputusan, bukan sekadar mengeksekusi.

---

## 0. Konteks & Asumsi (dari jawaban)

| Dimensi | Keputusan | Konsekuensi teknis |
|---|---|---|
| Produk | **Publik/komersial** (ribuan user) | butuh auth, infra publik, monitoring, SLA, keamanan |
| Data | **Bersedia bayar API IDX** (GoAPI.io) | data riil stabil; kurangi ketergantungan Yahoo |
| Frontend | **Migrasi framework** | risiko tertinggi → perlu strategi bertahap |
| Prioritas | **Mobile-first** | PWA, performance budget, responsive |

---

## 1. Technical Decisions (termasuk yang saya TANTANG)

### D1. ✅ SETUJU: GoAPI.io berbayar sebagai TIER 1 (data riil)
- Keputusan paling penting & tepat. Untuk produk **publik/komersial**, scraping Yahoo berisiko **hukum (ToS) & kestabilan** — tidak bisa jadi tulang punggung produk publik.
- **Architecture:** provider abstraction sudah ada (`quotes.py` tiered + circuit breaker) → tinggal mengaktifkan GoAPI penuh + tambah endpoint broker riil.
- **Sisa risiko:** berita RSS Yahoo/Google untuk produk publik juga berisiko lisensi → gunakan sebagai **agregator link** (sudah begitu: judul + tautan ke sumber) atau langganan feed berlisensi.

### D2. ⚠️ TANTANGAN: "Migrasi framework sekarang" — ini keputusan paling berisiko
**Kenapa saya tantang:**
- `app.js` ~7.000 baris, tanpa test E2E otomatis, maintainer non-IT → rewrite React/Vue = **bulan-bulan tanpa rilis + regresi tinggi**.
- Produk mau **mobile-first & segera publik** → meluncur lebih cepat dengan yang sudah berfungsi lebih berharga daripada migrasi.
- Nilai framework (state management, reusability) **sudah sebagian didapat** dari `lib.js` + `ui.js`.

**Alternatif yang saya rekomendasikan (langkah bertahap):**
1. **Vite + ES modules** (bulan 1–2) — tanpa rewrite: code-split, minify, DX modern, tetap vanilla. Risiko rendah.
2. **Framework ringan untuk VIEW BARU** (strangler pattern) — pilih **Lit** (web components, vanilla-like, kecil) atau **Preact** (mirip React, ringan) — BUKAN React langsung, kecuali Anda berniat merekrut engineer React.
3. **React hanya jika tim bertumbuh** — jangan sekarang.

> **Tradeoff framework:** React (ekosistem besar, tapi berat & learning curve) vs Lit/Preact (ringan, cocok vanilla→modern) vs tetap vanilla+Vite (paling sederhana untuk maintainer tunggal). Untuk Anda: **Vite + vanilla dulu, Lit untuk view baru** = sweet spot 5 tahun.

### D3. ✅ SETUJU: produk publik → Auth & multi-tenancy dasar
- **JWT + refresh token**, users table, watchlist/portfolio **sync ke PostgreSQL** (bukan localStorage) → data user aman & lintas perangkat.
- Rate-limit **per-user + per-IP** (sudah ada per-IP; tambah per-user).

### D4. ⚠️ TANTANGAN: cakupan fitur terlalu lebar untuk produk publik
- 8 screener + kalkulator + korelasi + edukasi + stock pick = permukaan besar.
- **Rekomendasi:** pisahkan **jalur publik (data riil, dirawat)** vs **Demo/simulasi (jelas ditandai, bisa diarsipkan)**. Broker/Bandar yang masih simulasi → gating di belakang GoAPI (jadi riil) atau di-arsipkan dari jalur publik.

### D5. ✅ SETUJU: mobile-first → PWA + performance budget
- Manifest + service worker (app-shell offline untuk shell, data tetap online), installable di HP.
- Budget: **LCP < 2,5s (4G)**, JS < 200KB gzip di halaman pertama, semua view 360px tanpa overflow (sudah jadi standar tim).

---

## 2. Tradeoff Analysis

| Keputusan | Opsi A | Opsi B | Opsi C | Rekomendasi |
|---|---|---|---|---|
| Frontend build | vanilla polos (now) | **Vite + vanilla** | React rewrite | **B** dulu, framework ringan per-view nanti |
| Framework | — | Lit/Preact | React | **Lit/Preact** bila framework; React hanya jika tim |
| Data quotes | Yahoo gratis | **GoAPI berbayar** | keduanya (fallback) | **GoAPI TIER 1 + Yahoo fallback** (sudah arsitekturnya) |
| Berita | RSS Yahoo/Google | RSS + agregator link | API berlisensi | **agregator link** (tetap) → pertimbangkan lisensi saat skala |
| DB | SQLite | **PostgreSQL** | — | **PG** untuk publik (user data, multi-writer) |
| Auth | none | **JWT** | OAuth/SSO | **JWT** dulu; OAuth bila integrasi pihak ketiga |
| Simulasi fitur | campur di alur utama | **jalur Demo terpisah** | hapus | **pisah jalur Demo** (jujur & rapi) |
| Skala | 1 server | **multi-worker + Redis** | k8s | **multi-worker + Redis** dulu; k8s bila >100k user |

---

## 3. Recommended Architecture (target)

```
[CDN] -> [nginx/WAF] -> [frontend app (PWA, Vite build)]
                            |
                     [BFF (Node/TS)]  --auth check---> [Auth service (JWT)]
                            |
              [ihsg-data-service (FastAPI, modular)]
                 |  GoAPI.io (TIER1)  |  Yahoo (fallback)  |  news (RSS)
                 |  Redis (cache+limit+lock)  |  PostgreSQL (users/watchlist/portfolio)
```

Prinsip tetap: satu pintu (nginx), BFF agregator, backend stateless modular, degradasi bertingkat, cache terpusat.

**Perubahan utama dari sekarang:**
1. **`users` + auth (JWT)** — data user pindah ke PG.
2. **GoAPI aktif penuh** — quotes TIER1, broker riil; Yahoo jadi fallback.
3. **Frontend: Vite build** → `src/` modules (lib/ui/pages), code-split; **PWA shell**.
4. **Monitoring** — metrik (latency, error, cache-hit, GoAPI usage/quota).

---

## 4. Implementation Plan (bertahap, 5 tahun)

### Fase 0 — Keputusan & fondasi (1–2 bulan)  ← mulai di sini
- Freeze scope publik vs demo; arsipkan/kasih label jalur simulasi.
- RFC teknis (dokumen ini jadi dasar); pilih GoAPI plan; setup repo CI (lint+test otomatis).

### Fase 1 — Data & auth (2–4 bulan)
- Aktifkan GoAPI penuh (quotes TIER1, broker riil, gating demo).
- Auth JWT + users; watchlist/portfolio sync ke PG.
- Provider abstraction diperkuat (contract antar provider).

### Fase 2 — Frontend modern & mobile (3–6 bulan)
- Vite + ES modules (tanpa rewrite fungsional).
- PWA (manifest + service worker), performance budget, audit aksesibilitas.
- Strangler: view baru memakai Lit/Preact.

### Fase 3 — Publik & observability (6–12 bulan)
- TLS + domain + CDN; WAF; per-user quota & rate-limit.
- Monitoring (latency/error/usage) + alerting; SLA dasar.
- Backup PG terjadwal + DR sederhana.

### Fase 4 — Skala (12+ bulan)
- Read-replica PG, autoscaling worker, Redis cluster.
- Keputusan fitur berbasis analytics; i18n bila perlu.
- **Aturan: tidak menambah fitur sebelum yang ada stabil & ter-monitor.**

---

## 5. Production-Ready Solution (poin kunci)

- **Auth:** JWT (access + refresh), password hashed (argon2), rate-limit per-user; rotasi refresh token.
- **Data:** GoAPI TIER1 dengan cache 20s (quote) / 600s (profile); circuit breaker tetap; **quota monitoring** (GoAPI billing).
- **Frontend:** Vite + code-split; PWA; komponen `ui.js` jadi dasar; loading/empty/error state (sudah ada) → terpakai semua view.
- **Infra:** PG (WAL + backup) + Redis + nginx (rate-limit edge) + CDN; Docker Compose → orchestrator saat skala.
- **Monitoring:** metrik request/latency/error/cache-hit/GoAPI-quota; healthz/readyz (sudah ada) di probe.
- **Keamanan:** TLS, WAF, CORS ketat (domain sendiri), X-Forwarded-For di-trust, no secrets di repo.

---

## 6. 5-Year Risks & Mitigations

| Risiko | Mitigasi |
|---|---|
| Yahoo mati/di-blokir | GoAPI TIER1 + fallback berlabel; provider abstraction |
| Lisensi berita publik | agregator link; langganan berlisensi saat skala |
| Maintainer tunggal (non-IT) | kesederhanaan (Vite+vanilla, bukan React); docs; CI otomatis; test |
| Public abuse/DDoS | WAF + rate-limit edge + auth + quota |
| Fitur melebar | aturan: stabil & ter-monitor sebelum fitur baru |
| Utang teknis app.js | strangler pattern (view baru framework ringan); freeze scope |

---

## 7. Rekomendasi Langkah Berikutnya (sebagai tech lead)

1. **Setujui/menolak** D2 (migrasi framework → saya sarankan Vite+vanilla dulu, Lit untuk view baru).
2. **Putuskan jalur publik vs demo** — fitur mana yang masuk jalur publik (data riil), mana di-arsipkan.
3. **Daftar GoAPI plan** & siapkan API key → saya aktifkan TIER1 penuh + broker riil.
4. Fase 0 dimulai: **RFC singkat** + CI (lint + test otomatis) + freeze scope.
