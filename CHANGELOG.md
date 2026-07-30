# CHANGELOG - Bug Fixes & Perbaikan Struktur

Dokumen ini merangkum seluruh bug yang ditemukan dan diperbaiki pada proyek
IHSG Dashboard (Stock Village), setelah audit menyeluruh terhadap kode di
`ihsg-dashboard.zip` (commit sebelumnya).

## 🐛 Bug Kritis (menyebabkan service tidak bisa berjalan)

1. **`ihsg-data-service/app/database.py` — Import Error fatal**
   - Sebelumnya: `from sqlalchemy import create_backend, create_engine`
   - `create_backend` bukan fungsi yang ada di SQLAlchemy → service langsung
     crash saat start (`ImportError`).
   - Diperbaiki menjadi: `from sqlalchemy import create_engine`.

2. **BFF Layer tidak pernah benar-benar menyala**
   - `web-bff/web.routes.ts` hanya membuat `express.Router()` dan
     meng-export-nya, tanpa pernah membuat instance `express()` app maupun
     memanggil `app.listen()`. Menjalankan `npm start` tidak membuka port
     apa pun.
   - Ditambahkan `bff-layer/server.ts` sebagai entry point baru yang
     menginisialisasi Express app, memasang middleware (CORS, logging),
     me-mount `WebBffRouter` di prefix `/api/web` (sesuai routing Nginx
     Gateway), dan memanggil `app.listen(PORT)`.
   - `package.json` diperbarui: `main`, `scripts.start`, dan
     `scripts.dev` sekarang menunjuk ke `server.ts` / `dist/server.js`.

3. **`news-service` — Dependency `lxml` hilang**
   - `BeautifulSoup(response.content, 'xml')` butuh parser `lxml`, namun
     tidak tercantum di `requirements.txt` → `bs4.FeatureNotFound` saat
     runtime.
   - Ditambahkan `lxml>=4.9.3` ke `backend-services/news-service/requirements.txt`.

4. **`ihsg-data-service` — Driver PostgreSQL hilang**
   - `docker-compose.yml` mengonfigurasi `DATABASE_URL` ke PostgreSQL,
     tetapi `requirements.txt` tidak memuat driver `psycopg2`, sehingga
     SQLAlchemy gagal connect saat dijalankan lewat Docker Compose.
   - Ditambahkan `psycopg2-binary>=2.9.9` ke
     `backend-services/ihsg-data-service/requirements.txt`.

5. **`frontend/web-app/Dockerfile` mengasumsikan project Next.js yang tidak ada**
   - Dockerfile lama menjalankan `npm ci` dan `npm run build` seolah ada
     aplikasi Next.js lengkap (package.json, folder pages/app), padahal
     source code sebenarnya hanyalah `frontend/index.html` mandiri
     (vanilla JS). Build container akan selalu gagal.
   - Dockerfile ditulis ulang menjadi image `nginx:alpine` ringan yang
     menyajikan `index.html`, `css/`, dan `js/` sebagai static file di
     port 3001. `docker-compose.yml` diperbarui agar build context
     mengarah ke `./frontend` (bukan `./frontend/web-app`) supaya file
     statis tersebut ikut ter-copy.

## ⚠️ Bug Logika / Konfigurasi

6. **`SECTOR_SERVICE_URL` mengarah ke service yang tidak eksis**
   - BFF sebelumnya memakai env var terpisah `SECTOR_SERVICE_URL` yang
     default-nya `http://localhost:8003/api` — padahal tidak pernah ada
     microservice ke-6 di port tersebut. Endpoint `/api/sectors`
     sebenarnya disediakan oleh `ihsg-data-service`.
   - Variabel `SECTOR_SERVICE_URL` dihapus; BFF sekarang selalu
     memanggil `${IHSG_SERVICE_URL}/sectors`.

7. **`fetch_and_sync_history` tidak kompatibel dengan `yfinance` versi baru**
   - `yf.download()` pada versi `yfinance` terkini mengembalikan kolom
     `MultiIndex (Price, Ticker)` meski hanya meminta 1 ticker, sehingga
     `row['Date']` menjadi `Series`, bukan `Timestamp` scalar, dan
     `.strftime()` melempar `AttributeError`.
   - Ditambahkan flatten kolom (`df.columns.get_level_values(0)`) sebelum
     diproses lebih lanjut.

8. **Filter `period` pada `/api/ihsg/history` tidak berfungsi**
   - `get_history_from_db()` selalu mengembalikan SELURUH riwayat harga
     di database, mengabaikan parameter `period` (`5d`, `1mo`, `3mo`,
     `6mo`, `1y`, `5y`) yang dikirim client — membuat filter periode
     chart di dashboard tidak berpengaruh sama sekali.
   - Fungsi kini menerima parameter `period`, memetakannya ke jumlah
     hari, dan memotong hasil query sesuai jumlah tersebut.

9. **TypeScript strict-mode error di `web.service.ts`**
   - `tsconfig.json` memakai `"strict": true`, tetapi hasil
     `Promise.all(...)` pada `fetch().then().catch()` yang beda tipe
     balikan menghasilkan tipe `unknown`, membuat `npm run build` gagal
     dengan banyak error `TS18046`.
   - `web.service.ts` ditulis ulang memakai helper generik
     `fetchJson<T>()` dengan tipe eksplisit (`IHSGRealtimeRaw`,
     `NewsRaw[]`, `SectorRaw[]`, `SentimentRaw`) dan fallback yang aman,
     termasuk fallback berjenjang (news-service → ihsg-data-service jika
     news-service sedang offline).

## 🧹 Perbaikan Struktur

10. **Duplikasi struktur folder**
    - `ihsg-dashboard.zip` sebelumnya berisi DUA salinan project: satu di
      root ZIP, satu lagi identik (dengan sedikit perbedaan) di dalam
      folder `ihsg-dashboard/`. Ini membingungkan mana yang jadi
      "source of truth" dan berisiko developer mengedit versi yang
      salah.
    - Struktur dirapikan menjadi satu folder project tunggal (root repo
      ini), diambil dari versi yang paling lengkap (frontend Bloomberg-
      style penuh dengan watchlist, portfolio tracker, sector heatmap,
      dsb).
    - `ihsg-dashboard.zip` (arsip biner lama) dihapus dari repo karena
      seluruh isinya sudah menjadi source code langsung di repo ini.

## 🎨 Perbaikan Tampilan Responsif (Mobile & Tablet)

Setelah audit visual menyeluruh menggunakan Playwright (screenshot otomatis di
lebar 390px/mobile, 768px/tablet, 1366px/laptop, dan 1920px/desktop), ditemukan
dan diperbaiki beberapa masalah tampilan berikut di `frontend/index.html`:

11. **Root cause utama — CSS Grid track `1fr` tidak punya batas minimum 0**
    - Semua container `display: grid` di halaman (`.dashboard-grid`, `.grid-2`,
      `.grid-3`, `.grid-4`, dan beberapa grid inline lain untuk Watchlist,
      Broker Summary, dan Kalkulator) menggunakan `1fr` atau `minmax(200px,
      1fr)` tanpa batas minimum eksplisit `0`. Secara default, track grid
      punya `min-width: auto`, sehingga ketika ada teks panjang non-wrap di
      dalamnya (misalnya "Rp 11.845 Triliun", "4.12%", macro-economic stats),
      seluruh grid ikut melebar melampaui lebar viewport di layar sempit —
      hasilnya teks di ujung kanan terpotong/tersembunyi meskipun
      `overflow-x: hidden` sudah dipasang di `html, body`.
    - Diperbaiki dengan mengganti seluruh `1fr` polos menjadi `minmax(0, 1fr)`,
      dan `minmax(200px, 1fr)` dkk. menjadi `minmax(min(200px, 100%), 1fr)`
      (mempertahankan perilaku multi-kolom di layar lebar, tapi mencegah
      overflow saat viewport lebih sempit dari nilai minimum tersebut).
    - Dampaknya terlihat jelas di panel "Statistik Pasar IHSG", "Kekuatan
      Pasar & Makro", "Top Movers", dan "IDX Sectors Heatmap" — semua data
      kini terbaca penuh di layar HP tanpa terpotong.

12. **Tabel lebar (Portfolio Position Monitor & Stock Screener) berantakan di
    mobile**
    - Kedua tabel ini punya 6–10 kolom yang didesain untuk layar lebar. Di
      mobile, browser memaksa seluruh kolom menyusut ke lebar layar 390px
      alih-alih men-scroll, sehingga teks antar kolom saling bertabrakan/
      tumpang-tindih dan sama sekali tidak terbaca (dialami di halaman
      Watchlist & Portofolio, VPA Screener, Wyckoff Screener, dan Premium
      Combo Screener — keempatnya memakai komponen tabel yang sama).
    - Diperbaiki dengan pola "responsive table → card" standar industri:
      ditambahkan class `.responsive-table` dan CSS `@media (max-width:
      767px)` yang mengubah `<table>` menjadi kumpulan kartu vertikal di
      bawah breakpoint tersebut. Setiap kolom mendapat label otomatis lewat
      atribut `data-label` (dirender lewat CSS `::before`), dan kolom
      pertama (kode/simbol emiten) dijadikan judul kartu. Tabel penuh
      (bukan kartu) tetap ditampilkan apa adanya di layar ≥768px — tidak ada
      perubahan visual di desktop/tablet.
    - Header tabel juga diberi `padding-right` yang sebelumnya tidak ada,
      supaya label kolom tidak saling menempel di lebar layar menengah
      (768px–1023px).

13. **Widget chart TradingView terlalu padat di HP**
    - Widget chart resmi TradingView (di-load dari CDN eksternal, di luar
      kendali CSS kita) menampilkan toolbar gambar samping dan date-range
      selector penuh di semua ukuran layar, membuat area chart yang tersisa
      sangat sempit dan legend OHLCV (`O:`, `H:`, `L:`, `C:`, `V:`) terlihat
      penuh sesak di HP.
    - Diperbaiki dengan mendeteksi lebar layar (`window.innerWidth < 768`)
      sebelum menginisialisasi widget, lalu men-set opsi
      `hide_side_toolbar: true` dan `withdateranges: false` khusus di layar
      sempit, sehingga area chart lebih lega di mobile tanpa mengubah
      pengalaman desktop.

## ✅ Validasi yang Sudah Dilakukan

- `python3 -m py_compile` pada seluruh modul Python: **lulus**.
- `ihsg-data-service` dijalankan langsung (bukan Docker) dan diuji:
  - `GET /api/ihsg/realtime` ✅
  - `GET /api/ihsg/history?period=5d|1mo|3mo|6mo|1y` ✅ (jumlah baris
    sesuai periode)
  - `GET /api/news`, `/api/sectors`, `/api/sentiment` ✅
- `news-service` dijalankan dan diuji:
  - `GET /api/news` berhasil scraping RSS asli CNBC Indonesia ✅
  - `GET /api/sentiment` menghitung skor agregat dengan benar ✅
- `bff-layer`:
  - `npx tsc --noEmit` **lulus tanpa error**.
  - `npm run build` **sukses**.
  - Server dijalankan (`node dist/server.js`) dan `GET
    /api/web/dashboard?period=1mo` berhasil mengagregasi data dari
    kedua microservice Python secara end-to-end ✅
- `frontend/index.html`:
  - Screenshot otomatis (Playwright) di 4 breakpoint (390px, 768px,
    1366px, 1920px) untuk seluruh menu (Home, Watchlist & Portofolio,
    VPA Screener, Wyckoff Screener, Premium Combo, Kalkulator Avg Down)
    sebelum & sesudah perbaikan.
  - Dipastikan `document.documentElement.scrollWidth ===
    document.documentElement.clientWidth` di semua breakpoint (tidak
    ada overflow horizontal tersembunyi).
  - Dipastikan tidak ada elemen konten yang bounding box-nya melebihi
    lebar viewport (dicek terprogram lewat `getBoundingClientRect()`
    untuk seluruh elemen di halaman) — satu-satunya elemen yang secara
    sengaja melebihi lebar viewport adalah ticker-tape marquee di
    bagian atas, yang memang didesain untuk berjalan otomatis
    (auto-scroll) secara horizontal.
