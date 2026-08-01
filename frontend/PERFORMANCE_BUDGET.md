# PERFORMANCE BUDGET — Frontend Stock Village

**Keputusan tech lead (Fase 2):** budget performa eksplisit + audit otomatis yang CI-able, supaya setiap perubahan kode tidak diam-diam memperlambat aplikasi mobile.

---

## 1. Budget (nilai saat ini vs target)

| Metrik | Budget | Terukur (Aug 2026) | Status |
|---|---|---|---|
| **FCP** (First Contentful Paint) | ≤ 1500 ms | **128 ms** | ✅ sangat cepat |
| **JS transfer (gzip)** — internal | ≤ 150 KB | **106 KB** (lib+ui+app+Lit) | ✅ |
| **CSS transfer (gzip)** | ≤ 15 KB | **5.4 KB** | ✅ |
| **index.html** | ≤ 200 KB | **185 KB** | ✅ |
| **JS errors** | 0 | **0** | ✅ |
| **Mobile overflow (390px, semua view)** | 0 | **0** | ✅ |
| LCP (Largest Contentful Paint) | ≤ 2500 ms | (lihat catatan) | ⚠️ ukur manual |

> Catatan jujur: **LCP tidak ter-trigger konsisten di headless Chromium** (tidak ada
> interaksi user). Karena itu LCP diukur manual per rilis via Lighthouse di perangkat
> nyata (HP mid-range, 4G throttling). FCP dipakai sebagai metrik otomatis pengganti
> yang reliable — dan sudah sangat baik (164 ms).

## 2. Cara menjalankan audit

```bash
# dari folder frontend (server dev/prod harus hidup: bash start_all.sh)
python3 tests/perf_budget.py --base http://localhost:8081/index.html
# exit 0 = PASS, 1 = FAIL (siap dipakai CI)
```

Audit mengukur:
- FCP via Paint Timing API
- Transfer size JS/CSS/HTML (respons aktual, bukan ukuran file)
- JS errors (pageerror)
- Overflow horizontal di 8 view utama pada viewport 390px (mobile)

## 3. Kontributor ukuran (agar tidak membengkak diam-diam)

| Aset | Ukuran gzip | Catatan |
|---|---|---|
| `js/app.js` | ~94 KB | terbesar; modularisasi bertahap (strangler) akan mengecilkannya |
| `js/lib.js` + `js/ui.js` | ~6 KB | kecil, stabil |
| `css/*` | ~5.4 KB | sudah di-minify Vite |
| `index.html` | 30 KB gzip / 185 KB raw | markup + inline (script eksternal) |
| **tv.js (CDN TradingView)** | eksternal | di luar kendali; di-load async oleh widget |

## 4. Aturan (tech-lead, untuk 5 tahun)

1. **Setiap rilis wajib lolos `perf_budget.py`** (CI atau manual sebelum push).
2. **Jangan menambah JS/CSS tanpa ukur** — budget adalah pagar: kalau mau naikkan,
   harus keputusan sadar + alasan.
3. **FCP adalah raja** — hindari render-blocking baru (script/CSS sync di <head>).
4. **Mobile-first** — tiap view baru wajib lolos audit 390px (tidak overflow).
5. **Perf budget di-review tiap kuartal** — sesuaikan kalau fitur bertambah sah.

## 5. Rekomendasi lanjutan (roadmap)

- **Code-split** via strangler pattern: view/langka di-bundle terpisah → hanya dimuat
  saat dibutuhkan (turunkun JS awal).
- **Lazy-load `app.js` berat** setelah interaksi pertama (idle) → FCP/LCP lebih baik.
- **Preload** aset kritis (`app.js`, CSS) — kurangi waterfall.
- **Lighthouse CI** pada HP nyata untuk LCP (mengisi gap budget LCP).

---

## 6. Catatan Strangler Pattern (Lit)

Komponen pertama yang dimigrasi ke Lit: **`sv-status-dot`** (lampu status 3 warna di sidebar). Lit (framework ringan ~7KB gzip) di-bundle via Vite (`src/lit/`), custom element dipakai dari HTML klasik tanpa mengganggu vanilla JS.

- Bundle Lit: `assets/index.js` (~7KB gzip) — total JS naik 99→106KB, **tetap dalam budget 150KB**.
- Kontrak migrasi: app.js set `tone` attribute (fallback ke inline style bila custom element belum terdefinisi) — migrasi tidak pernah merusak tampilan.
- Aturan strangler: migrasi satu komponen/area per langkah, wajib lolos `perf_budget.py` tiap kali.
