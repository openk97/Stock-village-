#!/usr/bin/env bash
# ============================================================================
# setup_tls.sh — aktifkan HTTPS (Let's Encrypt) pada API Gateway.
#
# Prasyarat:
#   - Domain sudah dibeli & A record mengarah ke IP VPS (propagasi selesai)
#   - Port 80 & 443 terbuka di firewall (ufw)
#   - App sudah berjalan (docker compose up -d) — TANPA downtime:
#     sertifikat diterbitkan via webroot (nginx melayani challenge).
#
# Cara pakai (dari root repo di VPS):
#   bash infrastructure/deploy/setup_tls.sh app.contoh.com [email-opsional]
#
# Hasil:
#   - Sertifikat di /etc/letsencrypt/live/<domain>/
#   - nginx.conf.docker digenerate dari template .tls (domain terisi)
#   - Gateway restart dengan HTTPS + redirect HTTP->HTTPS
# Renewal otomatis: timer systemd certbot.timer (webroot, tanpa downtime).
# ============================================================================
set -euo pipefail

DOMAIN="${1:?Usage: setup_tls.sh <domain> [email]}"
EMAIL="${2:-}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# 0) Certbot di host (Ubuntu/Debian)
if ! command -v certbot >/dev/null 2>&1; then
  echo "▶ Install certbot..."
  sudo apt-get update -qq
  sudo apt-get install -y -qq certbot
fi

# 1) Webroot directory (di-mount ke container nginx sebagai /var/www/certbot)
mkdir -p certbot-webroot/.well-known/acme-challenge

# 2) Terbitkan sertifikat via webroot (nginx tetap jalan; TANPA downtime)
ARGS=(certonly --webroot -w "$ROOT/certbot-webroot" -d "$DOMAIN" --agree-tos -n)
if [ -n "$EMAIL" ]; then
  ARGS+=(--email "$EMAIL" --no-eff-email)
fi
sudo certbot "${ARGS[@]}"

# 3) Generate config TLS dari template (isi __DOMAIN__)
sed "s/__DOMAIN__/$DOMAIN/g" infrastructure/api-gateway/nginx.conf.docker.tls \
  > infrastructure/api-gateway/nginx.conf.docker
echo "▶ nginx.conf.docker digenerate untuk domain $DOMAIN."

# 4) Restart gateway (mount config baru + sertifikat)
docker compose up -d api-gateway
sleep 4

# 5) Verifikasi
if curl -fsS --max-time 10 "https://$DOMAIN/healthz" >/dev/null 2>&1; then
  echo "✅ HTTPS aktif: https://$DOMAIN  (HTTP otomatis redirect ke HTTPS)"
  echo "   Jangan lupa set CORS_ORIGINS / CORS_ORIGIN = https://$DOMAIN di .env"
else
  echo "⚠️  Cek manual: https://$DOMAIN  (lihat: docker compose logs api-gateway)"
fi
