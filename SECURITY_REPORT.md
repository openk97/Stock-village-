# SECURITY REPORT — Stock Village

**Peran:** Senior Security Engineer · **Metode:** inspeksi kode aktual (bukan tebak) · **Scope:** aplikasi produksi + infra

---

## 0. Ringkasan Eksekutif

| # | Temuan | Severity | Status |
|---|---|---|---|
| 1 | Hardcoded token auth (dead code) `bffAuthMiddleware` | **Tinggi** | Perlu hapus |
| 2 | CORS `*` di backend & BFF | **Sedang** | Perbaiki produksi |
| 3 | Tanpa security headers di backend | **Sedang** | Tambah middleware |
| 4 | RSS berita tanpa validasi URL/target | **Rendah-Sedang** | SSRF risiko rendah |
| 5 | `.htpasswd` skrip cetak password ke stdout | **Rendah** | Info |
| 6 | Tanpa rate-limit pada `express.json` (body size) | **Rendah** | Perbaiki |
| 7 | Docker tanpa non-root user | **Sedang** | Perbaiki |
| 8 | GoAPI key di env (sudah benar via env) | Info | OK |
| 9 | Secret di git history (token GitHub di commit message) | **Tinggi (historis)** | Rotasi |

**Tidak ditemukan:** SQL injection (semua query pakai ORM/parameterized), path traversal
(pemisahan dir tetap), eval()/dangerous sink di backend.

---

## 1. Detail Temuan

### 1.1 🔴 TINGGI — Hardcoded token auth (dead code) — `bff-layer/shared/bff.middleware.ts`
```ts
if (token === "valid-token-ihsg-insight") { next(); }
```
- Middleware ini **TIDAK dipakai** di server.ts (dead code), tapi berisi **token
  statis** yang mudah ditebak. Jika suatu saat diaktifkan tanpa perbaikan → siapa pun
  yang tahu string ini bisa lolos auth.
- **Attack scenario:** developer mengaktifkan middleware "untuk mengamankan portfolio",
  token bocor di repo publik → attacker pakai token ini untuk akses data.

### 1.2 🟠 SEDANG — CORS `*` terbuka
- Backend FastAPI: `allow_origins=["*"]` · BFF: `app.use(cors())` (default semua origin).
- Untuk pemakaian pribadi/komunitas: risiko rendah; **bila app publik** → siapa pun
  bisa fetch API dari origin lain (jika ada data sensitif = berbahaya).

### 1.3 🟠 SEDANG — Tanpa security headers di backend
- Backend tidak mengirim `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  `Content-Security-Policy` (di nginx gateway sudah ada sebagian; tapi kalau API diakses
  langsung, headers hilang).

### 1.4 🟡 RENDAH-SEDANG — RSS fetch tanpa validasi target (SSRF potensial)
- `news_provider` fetch dari URL tetap (yahoo/google) — bukan dari input user → **risiko
  SSRF rendah**. Tapi url di DB (seed) tidak di-validate → kalau source bisa dipengaruhi,
  berpotensi fetch internal. Untuk sekarang aman.

### 1.5 🟡 RENDAH — `generate_htpasswd.sh` mencetak password ke stdout
- Password tercetak di terminal (bisa terekam di history/log). Aman-ish untuk lokal,
  tapi hindari kalau di shared machine.

### 1.6 🟡 RENDAH — `express.json()` tanpa body limit
- `app.use(express.json())` tanpa `limit` → body besar bisa menekan memori BFF.
  Tambah `express.json({ limit: '1mb' })`.

### 1.7 🟠 SEDANG — Docker containers jalan sebagai root
- Dockerfiles tidak `USER` non-root → bila container di-compromise, attacker punya
  root di container. Best practice: jalankan sebagai user non-root.

### 1.8 🔴 TINGGI (historis) — Secret di git history
- Commit message pernah memuat GitHub PAT (di sesi awal). Token itu sudah expired/revoke,
  tapi **masih ada di history repo** — kalau repo publik, jangan pernah commit secret;
  pastikan token lama di-revoke (sudah) & pertimbangkan rotasi.

---

## 2. Attack Scenarios

| Scenario | Vector | Impact |
|---|---|---|
| Aktifkan auth middleware bocor | hardcoded token di kode publik | akses data tak sah |
| CORS `*` + app publik | fetch lintas origin dari site jahat | baca respons API (bila ada data user) |
| Docker root | container compromise → root | ambil alih container |
| Log berisi password | generate_htpasswd di shared terminal | bocor kredensial gating |
| Body besar → BFF | POST tanpa limit | DoS memori BFF |

---

## 3. Secure Implementation Fixes

### 3.1 Hapus dead code auth (atau ganti dengan JWT benar)
```ts
// bff-layer/shared/bff.middleware.ts — HAPUS blok if(token === "valid-token-ihsg-insight")
// Jika butuh auth di masa depan: pakai JWT dengan secret dari env:
//   import jwt from 'jsonwebtoken';
//   const decoded = jwt.verify(token, process.env.JWT_SECRET!);
//   (req as any).user = decoded; next();
```

### 3.2 CORS dibatasi (produksi)
```ts
// bff-layer/server.ts
app.use(cors({ origin: process.env.CORS_ORIGIN ? process.env.CORS_ORIGIN.split(',') : '*' }));
```
```python
# backend app/main.py — dari env, bukan hardcode "*"
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(','))
```

### 3.3 Security headers (backend — middleware FastAPI)
```python
@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "SAMEORIGIN"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return resp
```

### 3.4 Body limit BFF
```ts
app.use(express.json({ limit: '1mb' }));
```

### 3.5 Docker non-root
```dockerfile
# backend & bff Dockerfile — tambah di akhir
USER 10001
```

### 3.6 Skrip gating — tidak cetak password (opsional)
Ganti `echo "Password : $PASS"` → instruksi "lihat file .htpasswd" / tanya konfirmasi.

---

## 4. Production-Grade Recommendations

1. **Jangan commit secret** — pakai `.env` (sudah) + secrets manager (VPS: systemd env /
   docker secrets). **Rotasi token lama** (sudah dilakukan sebagian).
2. **CORS ketat** di produksi (`CORS_ORIGINS=https://domain`).
3. **Security headers** di backend + pastikan nginx sudah mengirim (sudah sebagian).
4. **Docker non-root** + read-only filesystem (`read_only: true`) + `cap_drop: ALL`.
5. **Body limit** di BFF; **rate-limit edge** sudah ada (nginx) — pertahankan.
6. **Update dependensi** rutin (yfinance/pandas/express/nginx) — patch keamanan.
7. **Logging** tanpa data sensitif (jangan log token/password/authorization header).
8. **Backup** encrypted (sudah di plan V2: cron pg_dump).
9. **WAF/firewall** (ufw hanya 80/443) — sudah di plan V2.
10. **Uji berkala** — jalankan audit ini tiap rilis (jadikan checklist).

---

## 5. Checklist (untuk tiap rilis)

- [ ] Tidak ada token/secret baru di kode (grep `valid-token|password|secret`)
- [ ] CORS dibatasi (produksi)
- [ ] Security headers aktif
- [ ] Docker non-root
- [ ] Body limit BFF
- [ ] Dependensi up-to-date
- [ ] Log tanpa data sensitif
