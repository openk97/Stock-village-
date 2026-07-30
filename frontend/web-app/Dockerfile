# Dockerfile untuk Frontend Statis (Bloomberg-style IHSG Dashboard)
#
# CATATAN PERBAIKAN BUG:
# Dockerfile versi lama mengasumsikan ada aplikasi Next.js penuh (package.json, next build,
# folder pages/app), padahal source code yang benar-benar ada hanyalah index.html mandiri
# (vanilla JS + inline <script>, sudah fetch ke endpoint BFF "/api/web/dashboard").
# Karena tidak ada scaffold Next.js yang sebenarnya, container build lama akan SELALU GAGAL.
# Solusi paling aman: sajikan index.html sebagai static file lewat Nginx ringan.

FROM nginx:alpine

# Salin halaman dashboard statis ke direktori web root Nginx
COPY index.html /usr/share/nginx/html/index.html
COPY css /usr/share/nginx/html/css
COPY js /usr/share/nginx/html/js

# Konfigurasi Nginx sederhana: dengarkan di port 3001 agar konsisten dengan docker-compose
RUN echo 'server { \
    listen 3001; \
    server_name localhost; \
    root /usr/share/nginx/html; \
    index index.html; \
    location / { try_files $uri $uri/ /index.html; } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 3001

CMD ["nginx", "-g", "daemon off;"]
