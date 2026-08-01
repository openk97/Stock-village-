# ============================================================================
# Stock Village — Frontend (build Vite -> serve statis via Nginx)
#
# PERBAIKAN (Fase A deploy): versi lama meng-copy index.html/css/js MENTAH
# tanpa build Vite, sehingga:
#   - modul <script type="module" src="/src/lit/main.js"> TIDAK ada di hasil
#     (index.html hasil build merujuk asset ber-hash di dist/assets/)
#   - CSS tidak di-minify / tidak di-hash (cache-busting hilang)
#   - PWA hilang: sw.js, manifest.webmanifest, icons/ tidak ikut tersalin
# Sekarang multi-stage: node (npm ci + vite build) -> nginx (serve dist/).
# Build context = frontend/ (lihat docker-compose.yml).
# ============================================================================
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# STAGE 2: serve dist via nginx (image UNPRIVILEGED — bisa jalan non-root;
# image nginx:alpine biasa tidak bisa menulis pid/temp path saat non-root)
FROM nginxinc/nginx-unprivileged:alpine
COPY web-app/default.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 3001

# Healthcheck (liveness): nginx statis merespons /healthz
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3001/healthz >/dev/null 2>&1 || exit 1

# Image unprivileged sudah berjalan non-root (uid 101) — tidak perlu USER 10001.

CMD ["nginx", "-g", "daemon off;"]
