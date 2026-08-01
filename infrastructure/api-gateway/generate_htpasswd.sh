#!/usr/bin/env bash
# generate_htpasswd.sh — buat file .htpasswd untuk gating 1-password (nginx auth_basic).
#
# Cara pakai (dari folder repo):
#   bash infrastructure/api-gateway/generate_htpasswd.sh   # default user: admin
#   USER=nama bash infrastructure/api-gateway/generate_htpasswd.sh   # user kustom
#   USER=nama PASS=rahasia bash infrastructure/api-gateway/generate_htpasswd.sh
#
# Hasil: infrastructure/api-gateway/.htpasswd (JANGAN di-commit; sudah di .gitignore)
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$DIR/.htpasswd"
USER="${USER:-admin}"
PASS="${PASS:-}"

# Generate password acak bila tidak diset
if [ -z "$PASS" ]; then
  PASS="$(openssl rand -base64 12 | tr -d '/+=' | head -c 12)"
fi

# Buat hash apr1 (format yang dipakai nginx auth_basic)
HASH="$(openssl passwd -apr1 "$PASS")"
printf '%s:%s\n' "$USER" "$HASH" > "$OUT"
chmod 600 "$OUT"

echo "✅ .htpasswd dibuat: $OUT"
echo "   User     : $USER"
echo "   Password : $PASS"
echo
echo "Langkah berikutnya:"
echo "   docker compose up -d --build api-gateway   (VPS/prod)"
echo "   atau restart nginx agar memuat file baru."
