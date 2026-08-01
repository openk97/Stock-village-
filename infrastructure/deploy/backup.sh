#!/usr/bin/env bash
# ============================================================================
# backup.sh — backup otomatis Stock Village di VPS.
#   - PostgreSQL (pg_dump via docker exec, dikompres gzip)
#   - config penting: .env, .htpasswd, docker-compose.yml
#   - retensi: default 14 hari (hapus yang lebih tua)
#
# Cron (root, tiap hari 03:15):
#   15 3 * * * bash /opt/stock-village/infrastructure/deploy/backup.sh >> /var/log/stock-village/backup.log 2>&1
#
# Opsional off-site: install rclone, sambungkan ke Backblaze B2 / Google
# Drive / OneDrive, lalu set BACKUP_RCLONE_REMOTE=remote:path.
# ============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

DEST="${BACKUP_DIR:-/var/backups/stock-village}"
KEEP="${BACKUP_KEEP_DAYS:-14}"
mkdir -p "$DEST"

# Baca .env (POSTGRES_*)
set -a; [ -f .env ] && . ./.env; set +a

DB_CONTAINER="${DB_CONTAINER:-ihsg-postgres-db}"
PGUSER="${POSTGRES_USER:-ihsg_admin}"
PGDB="${POSTGRES_DB:-ihsg_insight_db}"
TS="$(date +%Y%m%d-%H%M%S)"
DB_FILE="$DEST/db-$TS.sql.gz"

echo "[$(date -Is)] Backup dimulai..."

# 1) Dump Postgres (amankan dari password di .env)
docker exec -e PGPASSWORD="${POSTGRES_PASSWORD:-}" "$DB_CONTAINER" \
  pg_dump -U "$PGUSER" -h 127.0.0.1 "$PGDB" | gzip > "$DB_FILE"

# 2) Config penting (bukan rahasia maksimal, tapi berguna saat restore)
tar czf "$DEST/config-$TS.tar.gz" \
  .env \
  infrastructure/api-gateway/.htpasswd \
  docker-compose.yml 2>/dev/null || true

# 3) Retensi
find "$DEST" -type f -mtime +"$KEEP" -delete

# 4) Opsional: salin off-site (rclone). Set BACKUP_RCLONE_REMOTE di .env
if [ -n "${BACKUP_RCLONE_REMOTE:-}" ]; then
  rclone copy "$DEST" "$BACKUP_RCLONE_REMOTE/stock-village" --quiet \
    && echo "   Off-site OK ($BACKUP_RCLONE_REMOTE)"
fi

echo "✅ Selesai. $(ls -1 "$DEST" | wc -l) file di $DEST:"
ls -lh "$DEST" | tail -4
