# 1. FRONTEND CLIENTS (Masing-masing memiliki BFF tersendiri)
frontend/
  web-app/            # Aplikasi Next.js Web Dashboard kita
  mobile-app/         # (Placeholder) Aplikasi Android / iOS Flutter/React Native
  desktop-app/        # (Placeholder) Aplikasi desktop Electron

# 2. BACKEND FOR FRONTEND (BFF) LAYER
bff-layer/
  web-bff/            # BFF khusus mengoptimalkan payload data untuk web browser
    web.routes.ts     # Rute API khusus Web Client
    web.controller.ts # Controller penerima request web HTTP
    web.service.ts    # AGREGATOR DATA: Menggabungkan data dari microservices
    web.dto.ts        # Data Transfer Object (Skema data khusus Web)
  mobile-bff/         # BFF khusus mengoptimalkan payload ringan untuk koneksi seluler
    mobile.routes.ts
    mobile.controller.ts
    mobile.service.ts # Kompresi chart dan batasi berita menjadi max 3 item saja
    mobile.dto.ts
  shared/
    bff.middleware.ts # Middleware Keamanan, CORS, & JWT Auth
    bff.utils.ts      # Helper parser data finansial
    bff.types.ts      # Interface TS bersama

# 3. BACKEND SERVICES (Microservices Independen)
backend-services/
  user-service/       # Python FastAPI untuk otentikasi user & watchlist portfolio
  ihsg-data-service/  # Python FastAPI untuk pengolahan & kalkulasi teknikal IHSG ^JKSE
  news-service/       # Python FastAPI untuk crawling berita & klasifikasi sentimen AI
  sector-service/     # Python FastAPI untuk melacak pergerakan 11 sektor bursa

# 4. INFRASTRUCTURE & CONFIGURATION
infrastructure/
  api-gateway/        # Nginx / Kong Gateway untuk routing lalu lintas ke BFF yang tepat
  database/           # PostgreSQL / SQLite tempat penyimpanan data persisten
  cache/              # Redis untuk caching harga real-time IHSG agar hemat API bursa
  message-queue/      # RabbitMQ / Celery untuk pemrosesan asinkron (misal: scraping berkala)
monitoring/
  logs/               # Logging sistem pusat (ELK Stack)
  metrics/            # Prometheus + Grafana untuk metrik performa API
config/
  env/                # Konfigurasi Environment (.env.development, .env.production)
  deployment/         # Berkas Dockerfile, docker-compose.yml & Kubernetes manifests
