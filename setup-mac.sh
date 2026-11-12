#!/usr/bin/env bash
# DBCompass setup for macOS.
#
#   ./setup-mac.sh          install everything (safe to re-run), then offer to start the app
#   ./setup-mac.sh start    start the app (backend + frontend) without reinstalling
#
# Ports default to 8000 (API) and 5173 (web). If they are taken:
#   DBCOMPASS_BACKEND_PORT=8010 DBCOMPASS_FRONTEND_PORT=5180 ./setup-mac.sh start
#
# Needs Python 3.11+ and Node.js 20+. If they are missing and Homebrew is installed, the script
# offers to install them. Runs locally with SQLite and the dev sign-in bypass: no Docker, no Azure.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV="$BACKEND/.venv"
BACKEND_PORT="${DBCOMPASS_BACKEND_PORT:-8000}"    # override if the port is taken, e.g. DBCOMPASS_BACKEND_PORT=8010
FRONTEND_PORT="${DBCOMPASS_FRONTEND_PORT:-5173}"

bold() { printf "\n\033[1m%s\033[0m\n" "$1"; }
ok() { printf "  \033[32m✓\033[0m %s\n" "$1"; }
warn() { printf "  \033[33m!\033[0m %s\n" "$1"; }
fail() { printf "\n\033[31m✗ %s\033[0m\n" "$1"; exit 1; }
ask_yes() { read -r -p "  $1 [Y/n] " reply; [[ -z "$reply" || "$reply" =~ ^[Yy] ]]; }

# ---------- prerequisites ----------

find_python() {
  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
        echo "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

node_ok() {
  command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1 &&
    node -e 'process.exit(parseInt(process.versions.node) >= 20 ? 0 : 1)' 2>/dev/null
}

offer_brew_install() {
  local package="$1" label="$2" url="$3"
  if command -v brew >/dev/null 2>&1; then
    if ask_yes "$label is missing. Install it with Homebrew now?"; then
      brew install "$package"
      return 0
    fi
  fi
  fail "$label is required. Install it from $url and run this script again."
}

check_prerequisites() {
  bold "1/5  Checking Python and Node.js"
  if ! PYTHON="$(find_python)"; then
    offer_brew_install "python@3.12" "Python 3.11 or newer" "https://www.python.org/downloads/macos/"
    PYTHON="$(find_python)" || fail "Python 3.11+ still not found. Open a new terminal and run the script again."
  fi
  ok "$("$PYTHON" --version)"
  if ! node_ok; then
    offer_brew_install "node" "Node.js 20 or newer" "https://nodejs.org/en/download"
    node_ok || fail "Node.js 20+ still not found. Open a new terminal and run the script again."
  fi
  ok "Node.js $(node --version), npm $(npm --version)"
}

# ---------- configuration ----------

create_env_files() {
  bold "2/5  Creating local settings"
  if [[ -f "$ROOT/.env" ]]; then
    ok ".env already exists (kept as is)"
  else
    cp "$ROOT/.env.example" "$ROOT/.env"
    ok "Created .env (local SQLite database, dev sign-in bypass)"
  fi
  if [[ -f "$FRONTEND/.env.local" ]]; then
    ok "frontend/.env.local already exists (kept as is)"
  else
    cp "$FRONTEND/.env.example" "$FRONTEND/.env.local"
    ok "Created frontend/.env.local"
  fi
}

# ---------- install ----------

install_backend() {
  bold "3/5  Installing the backend (Python packages)"
  if [[ ! -x "$VENV/bin/python" ]]; then
    "$PYTHON" -m venv "$VENV"
    ok "Created backend/.venv"
  fi
  "$VENV/bin/python" -m pip install --quiet --upgrade pip
  "$VENV/bin/python" -m pip install --quiet -r "$BACKEND/requirements.txt" ||
    fail "pip install failed. Behind a corporate proxy? See 'Quick setup' in README.md."
  ok "Python packages installed"
}

install_frontend() {
  bold "4/5  Installing the frontend (npm packages)"
  (cd "$FRONTEND" && npm ci --no-audit --no-fund --loglevel=error) ||
    fail "npm install failed. Behind a corporate proxy? See 'Quick setup' in README.md."
  ok "npm packages installed"
}

check_knowledge_base() {
  bold "5/5  Checking the knowledge base"
  if (cd "$BACKEND" && "$VENV/bin/python" -m app.knowledge.check >/dev/null 2>&1); then
    ok "Knowledge base check passed"
  else
    warn "Knowledge base check reported problems. Run: cd backend && .venv/bin/python -m app.knowledge.check"
  fi
}

# ---------- start ----------

port_busy() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

start_app() {
  [[ -x "$VENV/bin/uvicorn" ]] || fail "Not installed yet. Run ./setup-mac.sh first."
  [[ -d "$FRONTEND/node_modules" ]] || fail "Frontend not installed yet. Run ./setup-mac.sh first."
  for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
    port_busy "$port" && fail "Port $port is already in use (another DBCompass or 'docker compose up'?). Stop it, or pick other ports: DBCOMPASS_BACKEND_PORT=8010 DBCOMPASS_FRONTEND_PORT=5180 ./setup-mac.sh start"
  done

  bold "Starting DBCompass"
  local log="$ROOT/backend/backend.log"
  (cd "$BACKEND" && "$VENV/bin/uvicorn" app.main:app --port "$BACKEND_PORT" >"$log" 2>&1) &
  local backend_pid=$!
  trap 'echo; echo "Stopping DBCompass..."; kill "$backend_pid" 2>/dev/null || true; exit 0' INT TERM EXIT
  for _ in $(seq 1 60); do
    curl -fsS "http://localhost:$BACKEND_PORT/api/health" >/dev/null 2>&1 && break
    kill -0 "$backend_pid" 2>/dev/null || fail "The backend stopped while starting. See backend/backend.log."
    sleep 0.5
  done
  ok "Backend running on http://localhost:$BACKEND_PORT (log: backend/backend.log)"

  (sleep 3 && open "http://localhost:$FRONTEND_PORT") >/dev/null 2>&1 &
  ok "Opening http://localhost:$FRONTEND_PORT in your browser. Press Ctrl+C here to stop."
  cd "$FRONTEND" && VITE_API_PROXY_TARGET="http://localhost:$BACKEND_PORT" npm run dev -- --port "$FRONTEND_PORT" --strictPort
}

# ---------- main ----------

if [[ "${1:-}" == "start" ]]; then
  start_app
  exit 0
fi

printf "\033[1mDBCompass setup for macOS\033[0m\n"
check_prerequisites
create_env_files
install_backend
install_frontend
check_knowledge_base

bold "Setup complete"
echo "  Start the app any time with:  ./setup-mac.sh start"
if ask_yes "Start DBCompass now?"; then
  start_app
fi
