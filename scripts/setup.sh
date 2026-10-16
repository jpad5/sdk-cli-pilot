#!/usr/bin/env bash
# Workshop setup: Python venv + editable packages, npm install, .env, prerequisite report.
# Usage: scripts/setup.sh [--live] [--check-only]
set -euo pipefail

LIVE=0
CHECK_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --live) LIVE=1 ;;
    --check-only) CHECK_ONLY=1 ;;
    -h|--help) sed -n '2,3p' "$0"; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

step() { printf '\033[36m==> %s\033[0m\n' "$1"; }
warn() { printf '\033[33mWARNING: %s\033[0m\n' "$1" >&2; }

check_prereqs() {
  step "Prerequisite check"
  local missing=0 total=0
  while IFS='|' read -r name desc; do
    total=$((total + 1))
    if path="$(command -v "$name" 2>/dev/null)"; then
      printf '  [ok]   %-8s %s\n' "$name" "$path"
    else
      missing=$((missing + 1))
      warn "$(printf '%-8s not found - %s' "$name" "$desc")"
    fi
  done <<'EOF'
python3|Python 3.11+ (required)
node|Node.js 20.19+ (required for agent-ops-copilot)
az|Azure CLI (live labs)
azd|Azure Developer CLI (deploy lab)
gh|GitHub CLI (CI/CD + OIDC labs)
atk|M365 Agents Toolkit CLI (Teams lab)
a365|Agent 365 CLI (govern lab)
pac|Power Platform CLI (Copilot Studio lab)
copilot|GitHub Copilot CLI (agent-ops lab)
EOF
  echo "  $missing of $total tools missing (mock mode only needs python + node)."
}

check_prereqs
[ "$CHECK_ONLY" -eq 1 ] && exit 0

if [ -x .venv/bin/python ]; then
  PY=.venv/bin/python
elif [ -x .venv/Scripts/python.exe ]; then
  PY=.venv/Scripts/python.exe
else
  step "Creating .venv"
  BASE_PY="$(command -v python3 || command -v python || true)"
  [ -n "$BASE_PY" ] || { echo "Python not found on PATH." >&2; exit 1; }
  "$BASE_PY" -m venv .venv
  PY=.venv/bin/python
  [ -x "$PY" ] || PY=.venv/Scripts/python.exe
fi

step "Installing Python packages (editable)"
"$PY" -m pip install --quiet --upgrade pip
AGENT_EXTRAS="dev"
[ "$LIVE" -eq 1 ] && AGENT_EXTRAS="dev,live"
for pkg in "shared/kyc_core[dev]" "shared/mcp-sanctions" "src/foundry-kyc-agent[$AGENT_EXTRAS]" "src/m365-host[test]"; do
  echo "  pip install -e $pkg"
  "$PY" -m pip install --quiet -e "$pkg"
done
if [ "$LIVE" -eq 1 ]; then
  echo "  pip install -r src/copilot-studio-intake/requirements.txt"
  "$PY" -m pip install --quiet -r src/copilot-studio-intake/requirements.txt
fi

if command -v npm >/dev/null 2>&1; then
  step "npm install (src/agent-ops-copilot)"
  (cd src/agent-ops-copilot && npm install --no-fund --no-audit)
else
  warn "npm not found - skipping src/agent-ops-copilot install."
fi

if [ ! -f .env ]; then
  cp .env.example .env
  step "Created .env from .env.example (DEMO_MODE=mock)"
else
  step ".env already exists - left unchanged"
fi

echo
echo "Setup complete. Next: scripts/run-mock-demo.sh"
