# Stock Village Web Dashboard

Projek ini adalah platform analisis, pemantauan, dan visualisasi Indeks Harga Saham Gabungan (IHSG) secara komprehensif. Aplikasi dirancang menggunakan arsitektur modern fullstack (FastAPI + Next.js) dengan kapabilitas analisis data historis, sentimen berita, pelacakan dana asing (*foreign flow*), dan pencarian saham (*stock screener*).

---

## 1. Arsitektur Sistem & Tech Stack

```mermaid
graph TD
    A[Data Sources: Yahoo Finance, IDX, News Sites] -->|Scraping / API| B(Backend: FastAPI)
    B -->|Time-Series Data| C[(PostgreSQL + TimescaleDB)]
    B -->|Caching & Session| D[(Redis)]
    B -->|REST API / WebSockets| E[Frontend: Next.js + Tailwind CSS]
    E -->|Interactive Charts| F[User Browser: TradingView Charts / Recharts]
```

### **Backend (Data & API)**
*   **Framework:** **FastAPI (Python)** — Dipilih karena sangat cepat, mendukung asinkronus (async), dan ekosistem Python yang kaya akan pustaka analisis keuangan (Pandas, Numpy, TA-Lib).
*   **Database Utama:** **PostgreSQL** (opsional dengan ekstensi **TimescaleDB** untuk penyimpanan data time-series harga saham secara efisien).
*   **Caching & Broker:** **Redis** — Untuk menyimpan data *real-time ticker* IHSG dan mengurangi beban API eksternal.
*   **Scraper / Data Fetcher:** `yfinance` (Yahoo Finance API), `BeautifulSoup4` (untuk scraping berita), dan `pandas-ta` (untuk analisis teknikal otomatis).

### **Frontend (User Interface & Visualisasi)**
*   **Framework:** **Next.js (React)** — Optimal untuk performa, SEO-friendly (penting untuk web berita/informasi saham), dan mendukung Server-Side Rendering (SSR).
*   **Styling:** **Tailwind CSS** + **Shadcn/ui** (untuk komponen UI yang bersih, modern, dan profesional).
*   **Visualisasi Chart:** **TradingView Lightweight Charts** atau **Recharts** — Untuk grafik candlestick dan volume interaktif yang *responsive*.

---

## 2. Struktur Direktori Projek

```text
ihsg-dashboard/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py            # Entry point FastAPI
│   │   ├── config.py          # Konfigurasi database & environment
│   │   ├── database.py        # Koneksi database SQLAlchemy / Tortoise ORM
│   │   ├── models.py          # Definisi skema tabel database
│   │   ├── schemas.py         # Skema Pydantic untuk request & response
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── scraper.py     # Service pengambil data IHSG (Yahoo Finance/IDX)
│   │   │   ├── analytics.py   # Penghitungan indikator teknikal (RSI, MACD, MA)
│   │   │   └── news.py        # Scraper berita saham & analisis sentimen
│   │   └── api/
│   │       ├── __init__.py
│   │       ├── endpoints/
│   │       │   ├── ihsg.py    # Endpoint data IHSG & sektoral
│   │       │   ├── stocks.py  # Endpoint saham individual (LQ45, dsb.)
│   │       │   └── news.py    # Endpoint berita & sentimen
│   └── requirements.txt       # Dependensi Python
├── frontend/
│   ├── src/
│   │   ├── app/               # Next.js App Router (pages & layouts)
│   │   ├── components/        # Reusable UI Components (CandlestickChart, Screener, NewsCard)
│   │   ├── hooks/             # Custom React Hooks (useIHSGData, useWebSocket)
│   │   ├── lib/               # Utility functions & API clients
│   │   └── types/             # TypeScript interfaces
│   ├── package.json
│   ├── tailwind.config.js
│   └── tsconfig.json
└── README.md
```

---

## 3. Fitur Utama Aplikasi

1.  **Dashboard IHSG Real-Time & Historis:**
    *   Grafik Candlestick interaktif IHSG (`^JKSE`) harian, mingguan, bulanan.
    *   Status Pasar (Open, High, Low, Close, Volume, Value, Freq).
    *   Performa Indeks Sektoral (Infrastruktur, Keuangan, Energi, Consumer, dll.).
2.  **Analisis Arus Dana Asing (*Foreign Flow*):**
    *   Pelacakan akumulasi/distribusi dana asing (*Net Foreign Buy/Sell*) harian dan akumulatif secara *real-time*.
3.  **Penyaring Saham Pintar (*Stock Screener*):**
    *   Menyaring saham berdasarkan rasio fundamental penting: PE Ratio, PBV, ROE, Dividend Yield, dan Market Cap.
    *   Filter teknikal: Golden Cross MA50/200, RSI Oversold/Overbought.
4.  **Agregasi Berita & Analisis Sentimen (AI/NLP):**
    *   Scraping otomatis berita keuangan Indonesia (CNBC Indonesia, Kontan, Bisnis.com).
    *   Menggunakan model NLP sederhana (VADER atau Transformers lokal) untuk menentukan sentimen berita (*Positive*, *Neutral*, *Negative*) terhadap IHSG.
5.  **Simulasi Portofolio & Alert Sistem:**
    *   Fitur bagi pengguna untuk membuat portofolio virtual dan melacak performa aset mereka dibanding performa IHSG (*beating the market*).

---

## 4. Build Frontend (Vite — Fase 2 tech lead plan)

Pipeline build minimal (tanpa mengubah logika; bundling + minify + asset hash):

```bash
cd frontend
npm install        # sekali
npm run build      # -> frontend/dist/ (index.html + assets/ + js/ tersalin)
```

- **Dev / Termux:** `bash start_all.sh` (serve source langsung, tanpa build).
- **Prod:** `bash start_all.sh` dengan `FRONTEND_DIR=dist` (serve hasil build yang
  lebih kecil & cache-busted), atau layani `frontend/dist/` via nginx/CDN.
- **Catatan arsitektur:** script klasik (`js/lib.js`, `ui.js`, `app.js`) tidak
  di-bundle (butuh `type="module"` yang mengubah scope global) — disalin apa
  adanya. Code-split/minify JS penuh dilakukan bertahap (strangler pattern,
  lihat TECH_LEAD_PLAN.md).
