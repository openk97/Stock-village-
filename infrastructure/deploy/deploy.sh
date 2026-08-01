#!/usr/bin/env bash
# ============================================================================
# deploy.sh — deploy / update idempoten Stock Village di VPS.
# Dipanggil dari ROOT repo (setelah git pull/checkout). Aman diulang.
#
# Alur: cek .env & .htpasswd -> docker compose build+up -> tunggu /healthz.
# Tidak ada jendela downtime: nginx gateway (service lama) tetap melayani
# selama image baru di-build.
#
# Rollback (satu perintah):
#   git checkout <commit-terakhir-yang-oke> && bash infrastructure/deploy/deploy.sh
# ============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

# 1) Wajib: .env (rahasia). Buat sekali dari template.
if [ ! -f .env ]; then
  echo "❌ .env tidak ada. Jalankan:  cp .env.example .env" >&2
  echo "   lalu isi POSTGRES_PASSWORD (dan GOAPI_API_KEY bila ada)." >&2
  exit 1
fi

# 2) Wajib: .htpasswd (gating 1-password). Buat sekali:
#    bash infrastructure/api-gateway/generate_htpasswd.sh
if [ ! -f infrastructure/api-gateway/.htpasswd ]; then
  echo "❌ infrastructure/api-gateway/.htpasswd tidak ada. Jalankan:" >&2
  echo "   bash infrastructure/api-gateway/generate_htpasswd.sh" >&2
  exit 1
fi

# 3) Validasi cepat compose sebelum menyentuh container (gagal cepat).
echo "▶ Validasi docker compose config..."
docker compose config --quiet

# 4) Build image & start service baru (container lama diganti berurutan).
echo "▶ Build & start service..."
docker compose up -d --build --remove-orphans

# 5) Tunggu gateway end-to-end sehat: nginx -> BFF -> backend (/healthz).
echo "▶ Tunggu healthcheck gateway (max 3 menit)..."
for i in $(seq 1 36); do
  if curl -fsS --max-time 5 http://127.0.0.1/healthz >/dev/null 2>&1; then
    echo "✅ Deploy selesai — gateway sehat setelah $((i * 5)) detik."
    docker compose ps
    exit 0
  fi
  sleep 5
done

# 6) Gagal: tampilkan kondisi untuk diagnosa. (Rollback: lihat header file.)
echo "❌ Deploy GAGAL: /healthz tidak 200 dalam 180 detik." >&2
docker compose ps >&2 || true
exit 1
