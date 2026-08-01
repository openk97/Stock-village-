#!/usr/bin/env bash
# =============================================================================
# start_all.sh — Stock Village: jalanin SEMUA (backend + BFF + frontend + proxy)
# dengan SATU perintah. Bisa di PC (Linux/macOS/WSL) maupun Termux (Android).
#
# Cara pakai:
#   bash start_all.sh            # setup (sekali) + jalankan semua + healthcheck
#   bash start_all.sh --stop     # hentikan semua service
#   bash start_all.sh --restart  # hentikan lalu jalankan lagi
#
# Setelah jalan, buka di browser (PC):
#   http://localhost:8080
# Di HP (satu WiFi dgn PC), buka alamat IP yang dicetak skrip, mis:
#   http://192.168.1.10:8080
# Di Termux: ketik  termux-open-url http://localhost:8080
#
# Port: backend 8000 · BFF 3000 · frontend 8080 (ubah lewat env PORT_*)
# Log & PID: $HOME/.stockvillage-logs/
# =============================================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$SCRIPT_DIR"
LOGDIR="${STOCKVILLAGE_LOGS:-$HOME/.stockvillage-logs}"
mkdir -p "$LOGDIR"

# --- Port (bisa di-override) ---
PORT_BACKEND="${PORT_BACKEND:-8000}"
PORT_BFF="${PORT_BFF:-3000}"
PORT_FRONTEND="${PORT_FRONTEND:-8080}"

# --- Skala: jumlah worker uvicorn (PERF). Default 1 (aman di Termux/RAM kecil).
# Untuk produksi multi-core: WORKERS=4 bash start_all.sh
# Catatan: cache bersama antar worker memakai Redis (CACHE_BACKEND=redis);
# tanpa Redis, tiap worker punya cache sendiri (tetap aman, hanya duplikat).
WORKERS="${WORKERS:-1}"

# --- Deteksi Termux ---
IS_TERMUX=0
if [ -n "${TERMUX_VERSION:-}" ] || [ -d "/data/data/com.termux/files/usr" ]; then
  IS_TERMUX=1
fi

# --- Pilih interpreter Python (Termux: `python` = Python 3) ---
if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi

log()  { printf '\033[1;34m[start]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[start]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[start]\033[0m %s\n' "$*"; }
err()  { printf '\033[1;31m[start]\033[0m %s\n' "$*"; }

stop_all() {
  log "Menghentikan semua service (jika berjalan)..."
  for pidf in "$LOGDIR"/*.pid; do
    [ -f "$pidf" ] || continue
    pid=$(cat "$pidf" 2>/dev/null)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null
      sleep 1
      kill -9 "$pid" 2>/dev/null
      ok "  service $pid dihentikan"
    fi
    rm -f "$pidf"
  done
  # Bersihkan proses yatim (kalau PID file hilang tapi proses masih jalan)
  pkill -f "uvicorn app.main:app" 2>/dev/null
  pkill -f "ts-node server.ts" 2>/dev/null
  pkill -f "serve_with_proxy.py" 2>/dev/null
  ok "Selesai. Semua service berhenti."
}

# ----------------------------------------------------------------------------
# 1) SETUP BACKEND (Python venv + dependensi) — hanya sekali
# ----------------------------------------------------------------------------
setup_backend() {
  cd "$ROOT/backend-services/ihsg-data-service" || { err "Folder backend tidak ditemukan"; exit 1; }

  VENV="$ROOT/backend-services/ihsg-data-service/.venv"
  if [ ! -x "$VENV/bin/python" ] && [ ! -x "$VENV/bin/python3" ]; then
    log "Membuat virtualenv Python (pertama kali, butuh beberapa menit)..."
    if ! "$PY" -m venv "$VENV" 2>"$LOGDIR/setup.log"; then
      warn "venv gagal (di Termux butuh: pkg install python-venv). Pakai Python sistem langsung."
      VENV=""  # fallback: pip ke sistem
    fi
  fi

  if [ -n "$VENV" ] && [ -x "$VENV/bin/pip" ]; then
    PYV="$VENV/bin/python"
    PIP="$VENV/bin/pip"
  else
    PYV="$PY"
    PIP="$PY -m pip"
  fi

  # Cek dependensi inti (kalau belum ada, install)
  if ! "$PYV" -c "import fastapi, uvicorn, yfinance, pandas, sqlalchemy, requests" 2>/dev/null; then
    log "Menginstall dependensi backend (pertama kali, bisa lama di Termux)..."
    $PIP install --no-cache-dir -q \
      fastapi uvicorn sqlalchemy pydantic yfinance pandas requests \
      >>"$LOGDIR/setup.log" 2>&1 || { err "Gagal install dependensi backend. Lihat $LOGDIR/setup.log"; exit 1; }
    ok "Dependensi backend terinstall."
  else
    log "Dependensi backend sudah ada."
  fi
  echo "$PYV" > "$LOGDIR/.pyv"
}

# ----------------------------------------------------------------------------
# 2) SETUP BFF (npm install) — hanya sekali
# ----------------------------------------------------------------------------
setup_bff() {
  cd "$ROOT/bff-layer" || { err "Folder bff-layer tidak ditemukan"; exit 1; }
  if [ ! -d node_modules ]; then
    log "Menginstall dependensi BFF (npm install, pertama kali)..."
    npm install --no-audit --no-fund >>"$LOGDIR/setup.log" 2>&1 || { err "Gagal npm install. Lihat $LOGDIR/setup.log"; exit 1; }
    ok "Dependensi BFF terinstall."
  fi
}

# ----------------------------------------------------------------------------
# 3) JALANKAN SEMUA
# ----------------------------------------------------------------------------
run_all() {
  PYV="$(cat "$LOGDIR/.pyv" 2>/dev/null || echo "$PY")"

  # --- Backend ---
  log "Menjalankan Backend (FastAPI) di :$PORT_BACKEND ..."
  ( cd "$ROOT/backend-services/ihsg-data-service" \
      && rm -f *.db app/*.db 2>/dev/null \
      && setsid nohup "$PYV" -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT_BACKEND" --workers "$WORKERS" \
           >"$LOGDIR/backend.log" 2>&1 < /dev/null & echo $! > "$LOGDIR/backend.pid" )
  sleep 1

  # --- BFF ---
  log "Menjalankan BFF (Express/TS) di :$PORT_BFF ..."
  ( cd "$ROOT/bff-layer" \
      && setsid nohup ./node_modules/.bin/ts-node server.ts \
           >"$LOGDIR/bff.log" 2>&1 < /dev/null & echo $! > "$LOGDIR/bff.pid" )
  sleep 1

  # --- Frontend + proxy ---
  log "Menjalankan Frontend (static + proxy /api) di :$PORT_FRONTEND ..."
  ( cd "$ROOT" \
      && setsid nohup "$PY" "$ROOT/serve_with_proxy.py" --port "$PORT_FRONTEND" --bff "http://localhost:$PORT_BFF" \
           >"$LOGDIR/frontend.log" 2>&1 < /dev/null & echo $! > "$LOGDIR/frontend.pid" )
}

# ----------------------------------------------------------------------------
# 4) HEALTHCHECK
# ----------------------------------------------------------------------------
healthcheck() {
  local ok_all=1
  sleep 8  # beri waktu boot (backend seed & prefetch)
  log "Healthcheck..."
  _hc() { # $1 label, $2 url
    local code
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$2" 2>/dev/null)
    if [ "$code" = "200" ]; then ok "  ✓ $1  -> HTTP 200"
    else warn "  ? $1  -> HTTP ${code:-timeout} (mungkin masih boot / gagal)"; ok_all=0; fi
  }
  _hc "Backend  (8000)"  "http://localhost:$PORT_BACKEND/"
  _hc "BFF      (3000)"  "http://localhost:$PORT_BFF/health"
  _hc "Frontend (8080)"  "http://localhost:$PORT_FRONTEND/"

  if [ "$ok_all" = "1" ]; then
    ok "Semua service hidup!"
  else
    warn "Ada service yang belum siap — cek log di $LOGDIR (backend.log / bff.log / frontend.log)."
  fi

  # Cetak URL akses (LAN IP untuk HP)
  echo
  log "Buka aplikasi:"
  echo "  PC/Local  : http://localhost:$PORT_FRONTEND"
  local ip=""
  if command -v hostname >/dev/null 2>&1; then ip=$(hostname -I 2>/dev/null | awk '{print $1}'); fi
  if [ -z "$ip" ] && command -v ip >/dev/null 2>&1; then
    ip=$(ip -4 addr show 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | grep -v '^127\.' | head -1)
  fi
  if [ -n "$ip" ]; then echo "  HP (LAN)  : http://$ip:$PORT_FRONTEND"; fi
  if [ "$IS_TERMUX" = "1" ] && command -v termux-open-url >/dev/null 2>&1; then
    echo "  Buka di HP: termux-open-url http://localhost:$PORT_FRONTEND"
  fi
  echo
  log "Log ada di: $LOGDIR"
  log "Hentikan semua: bash start_all.sh --stop"
}

# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------
case "${1:-}" in
  --stop)    stop_all; exit 0 ;;
  --restart) stop_all; sleep 2 ;;
  --help|-h) sed -n '1,25p' "$0" | sed 's/^# \{0,2\}//' | grep -v '^=' ; exit 0 ;;
esac

log "=== Stock Village — start semua service ==="
if [ "$IS_TERMUX" = "1" ]; then
  log "Mode: Termux (Android). Pastikan sudah: pkg install python nodejs"
fi
setup_backend
setup_bff
run_all
healthcheck
