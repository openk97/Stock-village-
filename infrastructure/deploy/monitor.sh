#!/usr/bin/env bash
# ============================================================================
# monitor.sh — healthcheck ringan + alert Telegram. Dijalankan CRON tiap menit.
#
# Cron (root):
#   * * * * * bash /opt/stock-village/infrastructure/deploy/monitor.sh >> /var/log/stock-village/monitor.log 2>&1
#
# Yang dicek:
#   1. /healthz gateway (end-to-end: nginx -> BFF -> backend)
#   2. /readyz backend langsung (loopback 127.0.0.1:8000; cek DB/Redis)
#   3. Disk terpakai (alert > 85%)
#   4. Ada container compose unhealthy?
#
# Alert: Telegram (opsional) — set TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID di
# .env root. Tanpa itu, status hanya ke log (exit code untuk cron).
# Anti-spam: alert HANYA saat status berubah (state disimpan di /tmp).
# ============================================================================
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATE_DIR="${MONITOR_STATE_DIR:-/tmp/stock-village-monitor}"
mkdir -p "$STATE_DIR"

# Baca konfigurasi alert (TELEGRAM_*) dari .env root
set -a; [ -f "$ROOT/.env" ] && . "$ROOT/.env"; set +a

LOG="$ROOT/monitor.log"
log() { echo "[$(date -Is)] $*" >> "$LOG"; }

notify() { # notify <teks>
  if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
    curl -fsS --max-time 10 -X POST \
      "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
      -d chat_id="$TELEGRAM_CHAT_ID" -d text="$1" >/dev/null 2>&1 || true
  fi
}

# check <nama> <cmd...> — alert hanya saat status BERUBAH; log tiap perubahan
check() {
  local name="$1"; shift
  local state_file="$STATE_DIR/$name"
  if "$@" >/dev/null 2>&1; then
    if [ ! -f "$state_file" ] || [ "$(cat "$state_file")" != "ok" ]; then
      log "OK   : $name pulih."
      notify "✅ Stock Village — $name pulih."
    fi
    echo ok > "$state_file"
  else
    if [ ! -f "$state_file" ] || [ "$(cat "$state_file")" != "fail" ]; then
      log "FAIL : $name"
      notify "🔴 Stock Village — $name bermasalah! Cek: docker compose ps"
    fi
    echo fail > "$state_file"
  fi
}

# 1) Gateway end-to-end (nginx -> BFF -> backend)
check gateway curl -fsS --max-time 8 http://127.0.0.1/healthz

# 2) Backend readiness (DB/Redis terjangkau) — loopback ops
check backend_ready curl -fsS --max-time 8 http://127.0.0.1:8000/readyz

# 3) Disk: alert bila > 85%
disk_used="$(df -P / | awk 'NR==2 {gsub("%","",$5); print $5}')"
disk_used="${disk_used:-100}"
check disk test "$disk_used" -le 85
[ "$disk_used" -gt 85 ] && log "Disk ${disk_used}% terpakai (>85%)."

# 4) Container unhealthy (compose)
unhealthy="$(cd "$ROOT" && docker compose ps --format json 2>/dev/null | grep -c '"Health":"unhealthy"' || true)"
unhealthy="${unhealthy:-0}"
check containers test "$unhealthy" -eq 0
[ "$unhealthy" -gt 0 ] && log "$unhealthy container unhealthy."

log "Selesai (disk ${disk_used}%, unhealthy ${unhealthy})."
exit 0
