# DEVOPS_PLAN.md — Rencana Deploy Produksi Stock Village

> Status: **RENCANA + artefak siap pakai** (bukan sudah ter-deploy). Semua file
> CI/CD & skrip deploy sudah ditulis dan diuji di lokal, tapi **belum berjalan
> di VPS** karena VPS & domain belum dibeli. Detail di "Checklist Produksi".

---

## 0. Ringkasan Eksekutif

Aplikasi ini untuk **pemakaian pribadi/komunitas kecil** (keputusan Fase 2,
lihat `TECH_LEAD_V2.md`). Karena itu rencana deploy-nya satu kalimat:

> **Satu VPS kecil + Docker Compose + GitHub Actions (CI) + deploy manual via
> SSH + monitoring cron ringan + backup harian. Selesai. Tidak lebih.**

Keputusan kunci:

| Topik | Keputusan | Alasan singkat |
|---|---|---|
| Orkestrasi | **Docker Compose** (bukan Kubernetes) | 6 container, 1 mesin, 1 admin. K8s = biaya + beban operasi tanpa manfaat di skala ini |
| Hosting | **1 VPS** (Hetzner CX22 / setara) | ~€5/bulan; cukup 5+ tahun utk pemakaian ini |
| CI | **GitHub Actions** (repo sudah publik → gratis) | Test otomatis: pytest, unit test, build Vite, perf budget, build Docker |
| CD | **Deploy manual via SSH** (workflow dengan tombol) | Anda kontrol kapan rilis; auto-deploy bisa diaktifkan nanti (tinggal uncomment) |
| TLS | **Let's Encrypt (certbot webroot)** | Gratis, renewal otomatis, tanpa downtime |
| Monitoring | **Cron tiap menit + alert Telegram** (opsional) | Tanpa infrastruktur tambahan; Uptime Kuma hanya jika mau UI |
| Backup | **pg_dump harian + retensi 14 hari** (+ opsional off-site rclone) | Murah, restore < 10 menit |

**Data yang jujur perlu dicatat:**
- Single VPS = **single point of failure**. Untuk pemakaian pribadi ini wajar;
  konsekuensinya hanya "down beberapa jam saat VPS mati", dan pemulihan = deploy
  ulang dalam ±15 menit dari backup.
- Database isinya **sebagian besar cache data publik + data portofolio** — bukan
  aset yang tidak bisa diganti. Itu sebabnya backup-nya sederhana saja.
- Sumber data eksternal (Yahoo Finance / GoAPI / Google News RSS) adalah
  dependensi terbesar yang **tidak bisa kita kendalikan**. Monitoring utama
  sebenarnya adalah memastikan fallback & label kejujuran data tetap benar
  (fitur `Source:` di UI sudah menangani ini).

---

## 1. "Ini tempat di mana AI menjadi berbahaya" — jawaban langsung

Betul. Godaan terbesar saat diminta "siapkan production deployment" adalah
menghasilkan arsitektur raksasa: Kubernetes, microservices, service mesh,
Prometheus + Grafana, IaC Terraform, multi-region, blue-green, GitOps ArgoCD...

**Semuanya itu KEPUTUSAN YANG SALAH untuk aplikasi ini**, dan akan jadi beban
nyata (uang + waktu + kerumitan) setiap bulan selama bertahun-tahun:

- **Kubernetes** → butuh minimal 3 node agar wajar, kontrol plane yang dirawat,
  belajar `kubectl`/Helm. Untuk 6 container di 1 mesin, itu memperkenalkan
  ratusan failure mode baru tanpa menambah satu pun keandalan yang berarti.
  Aturan praktis: **pakai K8s saat Anda punya ≥ 3 service yang perlu di-scale
  independen ATAU ≥ 2 developer yang terus deploy**. Tidak ada yang terpenuhi.
- **Prometheus/Grafana** → dashboard 20 panel yang tidak akan pernah dibuka.
  Yang dibutuhkan: tahu "app mati / disk penuh / container restart" → 1 skrip
  cron + notifikasi sudah cukup.
- **IaC (Terraform)** → VPS-nya 1, config-nya 1 file compose yang sudah
  version-controlled di git. Terraform menambah satu tool lagi untuk hal yang
  bisa dilakukan `git clone && docker compose up`.
- **GitOps/ArgoCD/blue-green** → butuh registry image, ingress controller,
  staging. Untuk 1 pengguna, deploy manual dengan rollback satu perintah lebih
  sederhana dan lebih mudah dipahami.

Ukuran benar dari "production-grade" untuk proyek ini adalah: **dapat
di-deploy ulang dari nol dalam < 30 menit, otomatis diuji sebelum rilis, tahu
seketika kalau mati, dan tidak kehilangan data.** Bukan: memakai teknologi
terbaru. Rencana di bawah melakukan persis itu.

---

## 2. Arsitektur Target

```
                        Internet (HTTPS 443 / HTTP 80)
                                   │
                                   ▼
        ┌─────────────────────────────────────────────────┐
        │  VPS (1 node, Ubuntu 24.04 LTS)                 │
        │  ufw: hanya 22 (SSH), 80, 443                   │
        │  unattended-upgrades: patch keamanan otomatis   │
        │                                                 │
        │  ┌───────────────────────────────────────────┐  │
        │  │  api-gateway  (nginx:alpine)   [PUBLIK]   │  │
        │  │  • auth_basic 1-password (gating)         │  │
        │  │  • rate limit: 120r/m umum, 30r/m mahal   │  │
        │  │  • TLS Let's Encrypt (setelah setup_tls)  │  │
        │  │  • security headers, blokir /api/internal │  │
        │  └───────┬──────────────────────┬────────────┘  │
        │          ▼                      ▼               │
        │  ┌──────────────┐     ┌──────────────────┐      │
        │  │ frontend-web │     │ web-bff          │      │
        │  │ (nginx statis│     │ (Express/Node)   │      │
        │  │  hasil Vite) │     │ /api/web/*       │      │
        │  └──────────────┘     └───────┬──────────┘      │
        │                               ▼                 │
        │  ┌─────────────────────────────────────────┐    │
        │  │ ihsg-data-service (FastAPI, 4 workers)  │    │
        │  │ • rate limit • single-flight • circuit  │    │
        │  │   breaker • cache (Redis) • SQLAlchemy  │    │
        │  └──────────┬───────────────┬──────────────┘    │
        │             ▼               ▼                   │
        │  ┌──────────────┐   ┌──────────────┐            │
        │  │ db (Postgres)│   │ redis        │            │
        │  │ volume lokal │   │ volume lokal │            │
        │  └──────────────┘   └──────────────┘            │
        │                                                 │
        │  Hanya api-gateway yang punya port publik.      │
        │  Backend/BFF: loopback 127.0.0.1 utk monitoring.│
        └─────────────────────────────────────────────────┘
```

Alur satu request: browser → (HTTPS) → nginx gateway (auth + rate limit) →
`/api/web/*` → BFF → backend → (Redis cache / Postgres / Yahoo/GoAPI).

**Data keluar ke internet hanya dari `ihsg-data-service`** (Yahoo/GoAPI/Google
News RSS). Ini satu-satunya titik yang tidak bisa kita kendalikan — di-monitor
lewat `Source:` label di UI dan endpoint `/api/datasource/status`.

**Kapasitas (perhitungan jujur):**
- VPS Hetzner CX22: 2 vCPU, 4 GB RAM → penggunaan diperkirakan ~2,4 GB
  (backend 1 GB + db 512 MB + redis 320 MB + bff 384 MB + 2× nginx 128 MB).
- Pemakaian pribadi/komunitas: 1–20 pengguna bersamaan. Nginx + 4 worker
  FastAPI + rate limit 120r/m per IP menangani ini dengan **jauh di bawah
  10% kapasitas**. Tidak ada kebutuhan scaling horizontal; yang dibutuhkan
  hanya cadangan RAM bila `perf_budget.py` atau `docker stats` menunjukkan
  tekanan.
- Batas sebenarnya bukan server kita, tapi **kuota API data eksternal**
  (Yahoo/GoAPI). Sudah dimitigasi: cache (Redis), single-flight, rate limit,
  circuit breaker.

---

## 3. Perbaikan Infrastruktur yang Sudah Dilakukan di Repo Ini

Saat menyiapkan rencana ini, saya menemukan **3 bug nyata** yang akan membuat
deploy Docker GAGAL atau tidak aman. Semua sudah diperbaiki & diverifikasi:

| # | Temuan | Dampak jika dibiarkan | Perbaikan |
|---|---|---|---|
| 1 | `nginx.conf` memakai upstream `127.0.0.1:3000/3001` | Di Docker tiap service punya network sendiri → gateway **tidak bisa routing**, app 502 | `infrastructure/api-gateway/nginx.conf.docker` (upstream via nama service `web-bff`/`frontend-web`) |
| 2 | Dockerfile frontend meng-copy file mentah (tanpa build Vite) | App **rusak** (module `/src/lit/main.js` tidak ada), PWA/sw/manifest/icons **hilang** | Dockerfile multi-stage: `npm ci && vite build` → serve `dist/` + cache header benar |
| 3 | Semua port internal dibuka ke host (5432, 6379, 8000, 3000, 3001) | Postgres/Redis/API bisa diakses langsung dari internet | Hanya gateway (80/443) publik; sisanya jaringan internal + loopback ops |

Perbaikan lain yang sekalian dibereskan:
- **`.env` di root** (template `.env.example`), `POSTGRES_PASSWORD` di-wajib-kan
  compose (`:?` guard) → tidak mungkin start dengan password default.
- **Logging rotasi** per service (`json-file`, max 10 MB × 3) → log tidak
  menggembung disk.
- **`/healthz` tanpa auth** di gateway (monitor bisa cek tanpa kredensial);
  `/.well-known/acme-challenge/` tanpa auth (certbot bisa validasi).
- **HSTS/security headers** siap diaktifkan di config TLS.
- `.gitignore` + `.dockerignore` ditambah (`.env`, `certbot-webroot/`, dll).

**Bukti verifikasi (dijalankan sesi ini, mesin lokal):**
- `pytest tests` → **27 passed**
- `node tests/lib.test.js` + `node tests/ui.test.js` → PASS
- `npm run build` (Vite) → sukses
- `perf_budget.py` → **PASS** (FCP 124 ms, JS gzip 107,6 KB, CSS 5,4 KB, HTML 183,8 KB, 0 error, 0 overflow mobile)
- `nginx -t` terhadap `nginx.conf.docker` → OK (lihat sesi verifikasi)

---

## 4. Deployment Workflow

```
[develop] ──► push / PR ke main
                  │
                  ▼
         CI (GitHub Actions) ── 4 gerbang wajib hijau ──► ✗ tolak
                  │ hijau
                  ▼
         Anda klik "Deploy ke VPS" (workflow_dispatch)
                  │
                  ▼
         SSH ke VPS ──► git fetch + checkout commit ──► deploy.sh
                                                          │
                    docker compose up -d --build          │
                    tunggu /healthz 200 (max 3 menit)     │
                    sukses? ──► selesai, laporan status   │
                       │ gagal ──► diagnosa + rollback     │
                                                          ▼
         Rollback (jika perlu):  git checkout <commit-oke> && bash infrastructure/deploy/deploy.sh
```

Prinsip yang dipilih (dengan alasan):
- **Rilis = commit tertentu di main.** Versi app = versi di git. Tidak ada
  "state tersembunyi" di server.
- **Deploy manual, bukan auto** — Anda yang memutuskan kapan rilis. Auto-deploy
  tinggal uncomment 3 baris di `deploy.yml` kalau suatu saat mau.
- **Rollback = checkout commit lama + deploy ulang** (satu perintah). Karena
  image di-build di VPS dari commit itu, rollback selalu konsisten.
- **Nol downtime saat deploy**: nginx gateway (container lama) terus melayani
  selama image baru di-build; `docker compose up` mengganti container berurutan.

---

## 5. CI/CD

### CI — `.github/workflows/ci.yml` (4 gerbang, semua wajib hijau)

1. **Backend pytest** — 27 unit test (`backend-services/ihsg-data-service`).
2. **Frontend test + build** — `lib.test.js`, `ui.test.js`, lalu `vite build`.
3. **BFF build** — `tsc` (memastikan TypeScript tetap kompil).
4. **Perf budget** — `perf_budget.py` dengan Playwright (full chromium) di atas
   hasil build: FCP ≤ 1500 ms, JS gzip ≤ 150 KB, CSS ≤ 15 KB, HTML ≤ 200 KB,
   0 JS error, 0 overflow di 8 view @390px. **Ini pagar performa** — sesi Fase 2
   memutuskan setiap rilis harus melewatinya.
5. **Docker compose build** — memastikan semua Dockerfile & compose valid
   (meng-catch bug seperti temuan #1/#2 di atas di masa depan).

### CD — `.github/workflows/deploy.yml`

- Tombol **"Run workflow"** di GitHub → SSH ke VPS → `git fetch && checkout
  <commit> && deploy.sh`.
- **Secrets yang perlu di-set sekali** (Settings → Secrets and variables):
  `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_KEY` (private key SSH). Variable
  opsional: `DEPLOY_PATH` (default `/opt/stock-village`).
- Dipakai **raw `ssh`**, bukan action pihak ketiga → rantai supply chain lebih
  pendek (aman, dan jujur: tidak perlu percaya pada kode orang lain).

### Alur praktis sehari-hari (untuk non-IT)

1. Kerjakan perubahan → `git push` → GitHub otomatis menjalankan CI.
2. Kalau ada yang merah, cek tab Actions, perbaiki, push lagi.
3. Kalau hijau & mau dirilis: buka tab **Actions → Deploy ke VPS → Run
   workflow** → tunggu ±3–5 menit → selesai.

---

## 6. Docker Setup (detail produksi)

`docker-compose.yml` (di repo, sudah diperbaiki):

- **6 service** dengan `restart: always`, healthcheck tiap service, dan
  `depends_on: condition: service_healthy` → urutan start benar
  (db → redis → backend → bff → frontend → gateway).
- **Resource limit** per container (deploy.resources.limits) → satu container
  liar tidak bisa memakan RAM VPS.
- **Jaringan**: default bridge compose. Hanya gateway yang publik. Backend &
  BFF dibuka di `127.0.0.1` (loopback) untuk monitoring/diagnosa dari VPS.
- **Volume bernama**: `postgres_data`, `redis_data` → data tetap ada saat
  container diganti.
- **Logging rotasi**: `json-file`, 10 MB × 3 per service.

Image yang di-build: backend (`python:3.10-slim`, non-root `USER 10001`),
BFF (`node:18-alpine`, non-root), frontend (multi-stage Vite → nginx).
Gateway memakai `nginx:alpine` + config yang di-mount.

### TLS (setelah domain ada)

`bash infrastructure/deploy/setup_tls.sh app.domain.com [email]`
→ menerbitkan sertifikat Let's Encrypt **tanpa downtime** (webroot, nginx tetap
jalan), mengganti config gateway ke HTTPS + redirect, renewal otomatis via
timer `certbot.timer`. Setelah itu jangan lupa `CORS_ORIGINS`/`CORS_ORIGIN` di
`.env` diarahkan ke `https://domain`.

---

## 7. Monitoring & Logging

**Strategi: sesederhana mungkin, tapi efektif.**

- **Health endpoints yang sudah ada**: gateway `/healthz` (end-to-end:
  nginx → BFF → backend) dan backend `/readyz` (cek DB/Redis). Dipakai oleh
  healthcheck Docker **dan** monitor eksternal.
- **`infrastructure/deploy/monitor.sh`** — cron tiap menit, cek 4 hal:
  1. `/healthz` gateway (app hidup?)
  2. `/readyz` backend (DB/Redis terjangkau?)
  3. disk > 85% (peringatan awal sebelum penuh)
  4. ada container compose unhealthy?
  Alert Telegram (opsional; set `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` di
  `.env`). **Anti-spam**: notifikasi hanya saat status berubah, bukan tiap menit.
- **Logging**: semua container → stdout → rotasi Docker (10 MB × 3). BFF sudah
  log tiap request (`[BFF LOG] ... (durasi ms)`). Akses log: `docker compose
  logs -f --tail=100 <service>`.
- **Uptime Kuma** (opsional, kalau mau UI + status page): 1 container tambahan,
  cek HTTP tiap menit dari luar VPS. Tidak wajib.
- **Yang TIDAK dipasang**: Prometheus/Grafana, ELK, Sentry. Tidak sepadan
  untuk pemakaian ini. Jika nanti butuh tracing → cukup tambah logging
  terstruktur JSON di BFF/backend, tanpa infra baru.

---

## 8. Backup & Recovery

- **`infrastructure/deploy/backup.sh`** — cron harian 03:15:
  - `pg_dump` (Postgres) → gzip → `/var/backups/stock-village/`
  - config penting (`.env`, `.htpasswd`, `docker-compose.yml`) → tar
  - retensi 14 hari
  - opsional off-site via `rclone` (Backblaze B2 / Google Drive) — set
    `BACKUP_RCLONE_REMOTE` di `.env`. **Disarankan** — backup lokal di VPS yang
    sama tidak melindungi dari VPS mati total.
- **Restore** (dokumentasi di dalam file script):
  `gunzip < backup.sql.gz | docker exec -i ihsg-postgres-db psql -U ihsg_admin ihsg_insight_db`
- Catatan jujur: data yang benar-benar penting di app ini adalah (a) `.env`
  (rahasia), (b) portofolio/watchlist pengguna (di browser, bukan server), (c)
  data historis yang di-cache (bisa di-fetch ulang dari sumber). Jadi worst
  case tetap < 1 jam untuk kembali normal.

---

## 9. Security Hardening (ringkas; detail di `SECURITY_REPORT.md`)

- Sudah ada: gating 1-password (auth_basic), rate limit 2 level, security
  headers, blokir `/api/internal/`, container non-root, body limit 1 MB, CORS
  dari env, `RATE_LIMIT_TRUST_PROXY`.
- Tambahan saat setup VPS (di checklist): `ufw` (hanya 22/80/443), SSH key
  saja (nonaktifkan password login & root login), `unattended-upgrades`
  (patch keamanan otomatis), user deploy non-root dengan grup `docker`.
- Sertifikat: TLS aktif (HTTPS) setelah `setup_tls.sh`. HSTS menyala otomatis
  di config TLS.
- (Opsional) `fail2ban` untuk brute-force SSH bila IP publik mulai di-scan.

---

## 10. Checklist Produksi (urutkan eksekusi dari atas)

### Fase 0 — Prasyarat (sebelum beli apa pun)
- [ ] Cek kembali keputusan: pribadi/komunitas kecil → 1 VPS + compose (bukan K8s) — **keputusan sudah diambil**
- [ ] (Opsional) Aktifkan GoAPI.io API key — memperbaiki data broker/bandar dari simulasi ke riil
- [ ] Push repo ke GitHub (butuh token baru — token lama expired; minta di https://github.com/settings/tokens)

### Fase 1 — Beli domain & VPS
- [ ] Beli domain (~$10/thn): Cloudflare Registrar / Namecheap / Niagahoster
- [ ] Beli VPS (~€5/bln): Hetzner CX22 / DigitalOcean $12 / Contabo / IDCloudHost
- [ ] Arahkan DNS: `A` record domain → IP VPS
- [ ] SSH masuk pertama kali, `apt update && apt upgrade`

### Fase 2 — Setup VPS (sekali, ±30 menit)
- [ ] Buat user `deploy` non-root + SSH key; nonaktifkan root login & password login
- [ ] `ufw allow 22/tcp, 80/tcp, 443/tcp` + enable
- [ ] Install: `docker`, `docker compose v2`, `certbot`, `unattended-upgrades` (aktifkan)
- [ ] `git clone` repo ke `/opt/stock-village`
- [ ] `cp .env.example .env` → isi `POSTGRES_PASSWORD` (dan GoAPI key bila ada)
- [ ] `bash infrastructure/api-gateway/generate_htpasswd.sh` → catat password-nya
- [ ] `bash infrastructure/deploy/deploy.sh` → cek output `✅ gateway sehat`
- [ ] Uji di browser: `http://IP` → minta password → dashboard muncul, data real

### Fase 3 — HTTPS & monitoring
- [ ] `bash infrastructure/deploy/setup_tls.sh app.domain.com email@anda.com`
- [ ] Uji `https://domain` + redirect HTTP→HTTPS
- [ ] Set `CORS_ORIGINS`/`CORS_ORIGIN` di `.env` = `https://domain` → `deploy.sh` ulang
- [ ] Set `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` di `.env`
- [ ] Pasang cron: `monitor.sh` tiap menit, `backup.sh` 03:15
- [ ] (Opsional) `rclone` + `BACKUP_RCLONE_REMOTE` untuk backup off-site

### Fase 4 — CI/CD & serah terima
- [ ] Set GitHub secrets: `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_KEY` (+ variable `DEPLOY_PATH`)
- [ ] Trigger workflow "Deploy ke VPS" sekali → pastikan hijau
- [ ] Uji rollback di waktu luang: deploy commit lama → `deploy.sh`
- [ ] Verifikasi PWA di HP: instal ke home screen, buka offline (shell termuat)
- [ ] Verifikasi perf: `python3 frontend/tests/perf_budget.py` (pagar tetap hijau)

---

## 11. Biaya (jujur, per bulan)

| Item | Biaya | Catatan |
|---|---|---|
| VPS (Hetzner CX22 setara) | ~€5 / bln (~Rp 90rb) | 2 vCPU / 4 GB — cukup |
| Domain | ~$10 / tahun (~Rp 8rb/bln) | .com / .id |
| TLS | Rp 0 | Let's Encrypt |
| CI/CD | Rp 0 | GitHub Actions (repo publik) |
| Monitoring | Rp 0 | cron + Telegram |
| GoAPI.io (opsional) | tergantung paket | hanya jika mau broker/bandar riil |
| **Total** | **± Rp 100–110rb / bulan** | di luar GoAPI |

---

## 12. Kapan Perlu Upgrade Arsitektur? (jujur — mungkin tidak pernah)

Rencana ini cukup untuk **5+ tahun** pemakaian pribadi/komunitas. Tanda-tanda
nyata (bukan perasaan) bahwa perlu berubah:

- **Server kekurangan RAM/CPU**: lihat `docker stats` & `perf_budget.py`.
  Solusi pertama: naikkan VPS (CX22 → CX32/CX42). Sampai di sini saja.
- **Traffic publik & butuh CDN**: pasang Cloudflare (free) di depan domain —
  tanpa mengubah arsitektur server.
- **Banyak pengguna (> ~100 bersamaan) & perlu skala horizontal**: baru saat
  itu pertimbangkan 2 VPS + load balancer, atau kubernetes. Itu keputusan
  tahunan yang diambil dengan data, bukan sekarang.
- **Butuh banyak developer & rilis cepat**: baru saat itu GitOps/auto-deploy.

Kapan pun ada keraguan: **kembali ke prinsip — satu VPS + compose adalah
keputusan yang benar sampai ada bukti sebaliknya.**

---

## 13. Yang Sengaja TIDAK Dilakukan (anti over-engineering)

| Hal | Kenapa tidak |
|---|---|
| Kubernetes / k3s | 1 mesin, 6 container, 1 admin → beban tanpa manfaat |
| Microservices tambahan (pecah BFF/backend lagi) | Sudah 3 lapis (gateway/BFF/backend) — cukup |
| Prometheus + Grafana | Dashboard yang tidak akan dibuka; cron+Telegram lebih efektif |
| Terraform / IaC | 1 VPS; compose sudah version-controlled |
| GitOps (ArgoCD/Flux) + registry GHCR | Butuh komponen ekstra; deploy.sh + git cukup |
| Blue-green / canary | Overkill untuk 1 pengguna; rollback 1 perintah sudah ada |
| Multi-region / failover | Biaya >> manfaat di skala ini |
| Sentry / APM | Log + healthcheck sudah menjawab "kenapa mati?" |

---

## Lampiran A — Perintah Penting (cheat sheet VPS)

```bash
# Deploy / update
cd /opt/stock-village && git pull && bash infrastructure/deploy/deploy.sh

# Rollback
cd /opt/stock-village && git checkout <commit-oke> && bash infrastructure/deploy/deploy.sh

# Status & log
docker compose ps
docker compose logs -f --tail=100 ihsg-data-service
docker stats                      # lihat pemakaian RAM/CPU

# Healthcheck manual
curl -fsS http://127.0.0.1/healthz && echo OK        # end-to-end
curl -fsS http://127.0.0.1:8000/readyz && echo OK    # backend + DB

# Backup manual
bash infrastructure/deploy/backup.sh

# Restore DB dari backup terakhir
gunzip < /var/backups/stock-village/db-*.sql.gz | docker exec -i ihsg-postgres-db psql -U ihsg_admin ihsg_insight_db
```

## Lampiran B — File Baru di Repo Ini

| File | Fungsi |
|---|---|
| `.github/workflows/ci.yml` | CI: pytest, unit test frontend, build Vite, build BFF, perf budget, docker build |
| `.github/workflows/deploy.yml` | CD manual: SSH → `deploy.sh` |
| `infrastructure/deploy/deploy.sh` | Deploy idempoten + tunggu healthcheck + laporan |
| `infrastructure/deploy/monitor.sh` | Healthcheck cron tiap menit + alert Telegram |
| `infrastructure/deploy/backup.sh` | Backup pg_dump + config, retensi 14 hari, opsional off-site |
| `infrastructure/deploy/setup_tls.sh` | Aktifkan HTTPS (Let's Encrypt, tanpa downtime) |
| `infrastructure/api-gateway/nginx.conf.docker` | Config gateway untuk compose (upstream via nama service) |
| `infrastructure/api-gateway/nginx.conf.docker.tls` | Template TLS (dipakai setup_tls.sh) |
| `frontend/web-app/Dockerfile` (+ `default.conf`, `.dockerignore`) | Build Vite → serve dist + PWA (perbaikan bug) |
| `docker-compose.yml` (diperbarui) | Port internal ditutup, .env root, logging rotasi |
| `.env.example` (root) | Template rahasia produksi |
| `DEVOPS_PLAN.md` | Dokumen ini |
