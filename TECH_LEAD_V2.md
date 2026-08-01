# TECH LEAD V2 — Pivot: Pribadi/Komunitas Kecil di VPS

**Peran:** Senior Technical Lead · **Konteks:** keputusan ulang arah dari user —
bukan lagi "produk publik komersial", tapi **pemakaian pribadi/komunitas kecil,
tanpa login, di-host di VPS**. Prioritas: kesederhanaan & stabil jangka panjang
untuk maintainer non-IT.

> V2 ini MENGGANTI asumsi V1 (publik/komersial). Konsekuensinya: banyak rencana
> V1 (auth publik, GoAPI berbayar wajib, compliance, skala besar) **ditunda** —
> bukan dibuang, tapi tidak perlu sekarang.

---

## 0. Keputusan User (dasar V2)

| Dimensi | Keputusan | Konsekuensi teknis |
|---|---|---|
| Milestone | **Pribadi/komunitas kecil dulu** | fokus ke deploy yang bisa dipakai, bukan skala |
| Data | **Riset alternatif dulu** (ragu bayar) | Yahoo tetap untuk sekarang; GoAPI ditunda |
| Auth | **Tanpa login** | watchlist/portfolio tetap di browser (localStorage) — tidak perlu DB user |
| Hosting | **VPS + Docker** | deploy via docker compose (sudah 90% siap) |

---

## 1. Technical Decisions (yang saya setujui & tantang)

### D1. ✅ SETUJU: tanpa login untuk sekarang
- Data pribadi (watchlist/portfolio) hanya di browser masing-masing — **tidak ada
  data user sensitif di server** → risiko keamanan kecil.
- Tidak perlu auth publik, user table, JWT → **scope jauh lebih kecil & cepat rilis**.
- **Catatan lead:** ini keputusan *fase* — kalau komunitas tumbuh & butuh sync
  antar perangkat, auth ringan bisa ditambahkan nanti tanpa rombak (BFF sudah terpisah).

### D2. ✅ SETUJU: pribadi/komunitas kecil → Yahoo bisa dipakai dulu
- Risiko ToS/rate-limit **jauh lebih kecil** untuk pemakaian skala kecil dibanding
  produk publik komersial.
- Perlindungan sudah ada: **cache + single-flight + circuit breaker + rate-limit edge**.
- **Tetap riset alternatif** (lihat §5) sebagai keputusan *informed* nanti, bukan karena panik.

### D3. ⚠️ TANTANGAN (minor): "tanpa login" + "dibagikan ke komunitas" = siapa pun dengan URL bisa akses
- Kalau hanya Anda + beberapa orang tepercaya → tidak masalah.
- Kalau URL menyebar → orang asing bisa pakai (dan menambah beban Yahoo/VPS).
- **Saran:** opsional **gating sederhana (1 password aplikasi)** di nginx
  (`auth_basic`) — bisa diaktifkan 1 baris, bisa dimatikan. Murni opsional, bukan auth penuh.

### D4. ✅ SETUJU: VPS + Docker Compose — dan kita sudah 90% siap
- `docker-compose.yml` lengkap: PG + Redis + backend (4 worker) + BFF + frontend + nginx,
  semua dengan healthcheck + resource limit + env rahasia.
- Yang kurang untuk "bisa dipakai": **TLS/domain** + **firewall** + **backup**.

---

## 2. Tradeoff Analysis (V2)

| Keputusan | Opsi A | Opsi B | Rekomendasi |
|---|---|---|---|
| Auth | tanpa login | **gating 1 password (nginx auth_basic)** | **B opsional** — 1 baris, bisa nonaktif |
| Data | Yahoo (sekarang) | GoAPI (nanti) | **Yahoo dulu** + riset alternatif |
| TLS | nginx + certbot | **Caddy (auto-TLS)** | **nginx + certbot** (kita sudah punya nginx.conf; perubahan minimal) |
| Skala | 1 VPS kecil | multi-node | **1 VPS** (2GB cukup) — sederhana, biaya rendah |
| Backup | manual | **cron pg_dump** | **cron pg_dump** (10 menit setup) |
| Frontend build | source langsung | **dist (Vite build)** | **dist** di VPS (lebih kecil & cepat) |

---

## 3. Recommended Architecture (V2 — target deploy)

```
Internet ──▶ VPS (1 node)
              ├─ firewall: hanya 80/443 (ufw)
              ├─ nginx (:443 TLS + :80→https redirect)
              │    ├─ rate-limit edge (sudah ada)
              │    ├─ [opsional] auth_basic 1-password
              │    └─ serve frontend/dist/ (statis) + /api/web/* → BFF
              ├─ web-bff (:3000, internal)
              ├─ ihsg-data-service (:8000, 4 worker, Redis cache)
              ├─ Redis (:6379, internal, cache+limit+lock)
              └─ PostgreSQL (:5432, internal, WAL + backup cron)
```
Prinsip: **satu node, semua internal kecuali nginx**. Tidak perlu LB/k8s — itu
keputusan skala nanti, bukan sekarang.

---

## 4. Implementation Plan (4 fase kecil — total ~1–2 minggu)

### Fase A — Deploy VPS (3–5 hari) ← MULAI DI SINI
1. Beli VPS kecil (2GB RAM, 1 vCPU — mis. Hetzner/DigitalOcean/Linode ~$6/bln).
2. `apt install docker docker-compose-v2 certbot` + firewall `ufw` (buka 80/443).
3. Clone repo → `cp .env.production.example .env` (isi rahasia) →
   `docker compose up -d --build`.
4. Domain (atau subdomain) → DNS A ke IP VPS → `certbot --nginx` (TLS otomatis).
5. Verifikasi: `https://domain/` → app hidup, healthcheck hijau.

### Fase B — Validasi di lingkungan publik (2–3 hari)
- Cek data Yahoo dari IP VPS (rate-limit?) — cache/circuit-breaker sudah melindungi.
- Verifikasi budget performa + PWA di HP lewat URL publik.
- **Opsional:** aktifkan `auth_basic` jika mau dibatasi.

### Fase C — Riset alternatif data (paralel, 1 minggu)
- Saya bantu kumpulkan daftar alternatif (lihat §5) + rekomendasi berdasar
  kebutuhan: gratis-resmi vs berbayar-stabil. Keputusan *informed*, bukan karena panik.

### Fase D — Operasional dasar (1 hari)
- Cron backup PG (pg_dump → file) + retensi 7 hari.
- Log rotation (docker logs / journald).
- Catatan rilis: `git pull && docker compose up -d --build` = deploy ulang.

---

## 5. Riset Alternatif Data (yang saya cek untuk Anda)

| Sumber | Jenis | Biaya | Catatan |
|---|---|---|---|
| **Yahoo Finance** (kini) | harga/history/berita | gratis | ToS abu-abu, rate-limit; OK utk skala kecil |
| **GoAPI.io** | data IDX lengkap + broker | berbayar (ada free tier) | paling siap pakai utk Indonesia |
| **IDX resmi (idx.co.id)** | statistik/resume | gratis | data resmi, tapi bentuknya publikasi/PDF, bukan API terstruktur |
| **Bursa API komunitas** | harga IDX | gratis | kualitas/tidak resmi bervariasi |
| **financenews/berita RSS** | berita | gratis | sudah dipakai (Yahoo+Google RSS) |

> **Rekomendasi lead:** pakai Yahoo sekarang (skala kecil aman). Saat komunitas
> tumbuh / butuh broker riil → GoAPI (free tier dulu). IDX resmi tidak praktis
> sebagai API real-time.

---

## 6. Production-Ready Solution (V2 — checklist konkret)

- **Deploy:** `docker compose up -d --build` di VPS; semua healthcheck sudah siap.
- **TLS:** certbot + nginx (auto-renew cron).
- **Keamanan:** ufw (80/443 saja), `.env` tidak di-commit, CORS dibatasi domain.
- **Data:** Yahoo + cache/single-flight/circuit-breaker (sudah); label kejujuran tetap.
- **Frontend:** serve `frontend/dist/` (Vite build) — lebih kecil & cache-busted.
- **Backup:** cron `pg_dump` → `/var/backups` (retensi 7 hari).
- **Update:** `git pull && docker compose up -d --build` (dokumentasikan di README).
- **Rollback:** `git checkout <commit-lama> && up -d --build`.

---

## 7. Keputusan yang saya butuhkan (sebelum Fase A)

1. **Domain**: punya domain/subdomain? (atau pakai IP dulu — TLS via IP tidak
   gratis/standar; domain ~$10/thn sangat disarankan).
2. **VPS**: sudah punya pilihan provider / sudah beli?
3. **Gating**: mau aktifkan 1-password (`auth_basic`) atau terbuka dulu?
4. **Dokumen ini**: commit ke repo sebagai keputusan tim?

---

## 8. Rekomendasi Domain & VPS (per request user)

### Domain (~$8–12/tahun)
| Provider | Harga indikatif | Catatan |
|---|---|---|
| **Cloudflare Registrar** | ~$10/thn (.com) | harga at-cost (tanpa markup); DNS + CDN gratis di satu tempat; butuh kartu kredit internasional |
| **Namecheap** | ~$9–12/thn | murah & umum; panel sederhana |
| **Niagahoster / Domainesia** (ID) | ~Rp 200–300rb/thn | bisa bayar lokal (transfer/QRIS); cocok kalau mau bayar pakai metode lokal |

> **Rekomendasi lead:** kalau bisa kartu kredit internasional → **Cloudflare Registrar**
> (at-cost + DNS di Cloudflare, bagus untuk nanti). Kalau mau bayar lokal → Niagahoster/Domainesia.

### VPS (~$6–12/bln, cukup 2GB RAM)
| Provider | Spesifikasi dasar | Harga | Catatan |
|---|---|---|---|
| **Hetzner CX22** | 2 vCPU, 4GB | ~€5/bln | paling murah & reliable (butuh kartu kredit/PayPal) |
| **DigitalOcean** | 1 vCPU, 2GB | $12/bln | populer, panel bagus, dokumentasi banyak |
| **Vultr** | 1 vCPU, 2GB | ~$12/bln | mirip DO |
| **Contabo** | 4 vCPU, 8GB | ~€5–6/bln | murah & besar, tapi support/netcode kadang lebih lambat |
| **IDCloudHost / Niagahoster Cloud** (ID) | 2–4 vCPU, 2–4GB | ~Rp 100–200rb/bln | bayar lokal; latensi ke Indonesia bagus |

> **Rekomendasi lead:** **Hetzner CX22** (nilai terbaik) atau **DigitalOcean $12** (mudah untuk
> pemula non-IT, banyak tutorial). Kalau fokus bayar lokal & akses Indonesia: IDCloudHost.

### Urutan setup Fase A (ringkas)
1. Beli VPS → buka 80/443 (ufw).
2. `apt install docker docker-compose-v2 certbot` → clone repo → `.env` → `up -d --build`.
3. Beli domain → DNS A → VPS IP → `certbot --nginx` (TLS).
4. Jalankan `generate_htpasswd.sh` → restart api-gateway (gating aktif).
