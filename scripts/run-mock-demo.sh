#!/usr/bin/env bash
# End-to-end mock demo: MCP sanctions server, three onboarding chats, SAR approval (HITL),
# mock evals and an audit summary. No cloud resources required.
set -euo pipefail

PORT="${PORT:-8765}"
STARTUP_TIMEOUT="${STARTUP_TIMEOUT:-60}"
APPROVER="${APPROVER:-Workshop Reviewer}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

export DEMO_MODE=mock
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
export MCP_SANCTIONS_URL="http://127.0.0.1:${PORT}/mcp"

if [ -x .venv/bin/python ]; then PY=.venv/bin/python
elif [ -x .venv/Scripts/python.exe ]; then PY=.venv/Scripts/python.exe
else echo "Missing .venv - run scripts/setup.sh first." >&2; exit 1; fi

DATA_DIR="${KYC_DATA_DIR:-$REPO_ROOT/.data/demo-run}"
# Fresh state each run (only for the script's own folder) so SAR statuses and audit counts are repeatable.
[ "$DATA_DIR" = "$REPO_ROOT/.data/demo-run" ] && rm -rf "$DATA_DIR"
mkdir -p "$DATA_DIR"
export KYC_DATA_DIR="$DATA_DIR"

step() { printf '\n\033[36m==> %s\033[0m\n' "$1"; }

port_open() {
  "$PY" - "$1" <<'PY'
import socket, sys
s = socket.socket(); s.settimeout(0.5)
try:
    s.connect(("127.0.0.1", int(sys.argv[1]))); sys.exit(0)
except OSError:
    sys.exit(1)
finally:
    s.close()
PY
}

agent() {
  printf '\033[33myou> %s\033[0m\n' "$1" >&2
  local out
  out="$("$PY" -m kyc_agent chat "$1" 2>&1)" || { echo "$out" >&2; echo "kyc_agent chat failed: $1" >&2; return 1; }
  echo "$out" >&2
  printf '%s' "$out"
}

if port_open "$PORT"; then echo "Port $PORT already in use - stop the existing MCP server first." >&2; exit 1; fi

SERVER_PID=""
cleanup() {
  if [ -n "$SERVER_PID" ]; then
    step "Stopping MCP server (PID $SERVER_PID)"
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

step "Starting sanctions MCP server on http://127.0.0.1:${PORT}/mcp"
"$PY" -m kyc_sanctions.server --http >"$DATA_DIR/mcp-server.log" 2>&1 &
SERVER_PID=$!
deadline=$(( $(date +%s) + STARTUP_TIMEOUT ))
until port_open "$PORT"; do
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then cat "$DATA_DIR/mcp-server.log" >&2; echo "MCP server exited during startup." >&2; exit 1; fi
  if [ "$(date +%s)" -gt "$deadline" ]; then echo "MCP server did not open port $PORT within ${STARTUP_TIMEOUT}s." >&2; exit 1; fi
  sleep 0.5
done
echo "  MCP server up (PID $SERVER_PID)"

step "Onboarding chats"
agent "onboard CUST-1001" >/dev/null
agent "onboard CUST-1003" >/dev/null
SAR_REPLY="$(agent "onboard CUST-1007")"

step "Human-in-the-loop SAR approval"
SAR_ID="$(printf '%s' "$SAR_REPLY" | grep -oE 'SAR-[A-Za-z0-9]+' | head -n1 || true)"
[ -n "$SAR_ID" ] || { echo "No SAR id found in CUST-1007 output." >&2; exit 1; }
APPROVAL="$(agent "approve $SAR_ID as $APPROVER")"
case "$APPROVAL" in *approved*) ;; *) echo "SAR approval did not succeed: $APPROVAL" >&2; exit 1 ;; esac

step "Mock evals"
"$PY" -m kyc_agent.evals --mode mock --threshold 0.8

step "Audit summary"
AUDIT_FILE="$DATA_DIR/audit.jsonl"
if [ -f "$AUDIT_FILE" ]; then
  "$PY" - "$AUDIT_FILE" <<'PY'
import collections, json, sys
counts = collections.Counter()
with open(sys.argv[1], encoding="utf-8") as fh:
    for line in fh:
        if line.strip():
            counts[json.loads(line).get("event", "?")] += 1
width = max((len(k) for k in counts), default=5)
print(f"  {'Event':<{width}}  Count")
for event, n in counts.most_common():
    print(f"  {event:<{width}}  {n}")
print(f"  {sum(counts.values())} audit events in {sys.argv[1]}")
PY
else
  echo "WARNING: no audit log at $AUDIT_FILE" >&2
fi

printf '\n\033[32mMock demo completed successfully.\033[0m\n'
