#!/usr/bin/env bash
# RPHelper host-dev launcher (Linux/WSL). Runs both halves in this terminal:
#   [api] uvicorn on 127.0.0.1:8184 with reload, debug logging
#   [ui]  Vite on 8193
# Ctrl-C (or either half exiting) stops both and exits.
# Ports are topology literals, not settings (docs/architecture/deployment.md).

set -uo pipefail
set -m  # job control: each background job gets its own process group

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

prefix() { sed -u "s/^/$1 /"; }

(cd "$root/backend" && exec .venv/bin/python -m uvicorn app.main:app \
    --host 127.0.0.1 --port 8184 --reload --log-level debug --use-colors) \
    < /dev/null > >(prefix $'\e[36m[api]\e[0m') 2>&1 &
api=$!

(cd "$root/frontend" && FORCE_COLOR=1 exec npx vite --port 8193) \
    < /dev/null > >(prefix $'\e[35m[ui] \e[0m') 2>&1 &
ui=$!

cleanup() {
    trap - INT TERM EXIT
    set +m  # silence "[n]+ Terminated" job notices
    echo "Stopping..."
    # Negative pid = whole process group (uvicorn reloader + worker, vite + esbuild).
    kill -TERM -- -"$api" -"$ui" 2>/dev/null
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        kill -0 -- -"$api" 2>/dev/null || kill -0 -- -"$ui" 2>/dev/null || break
        sleep 0.5
    done
    kill -KILL -- -"$api" -"$ui" 2>/dev/null
    wait 2>/dev/null
}
trap cleanup INT TERM EXIT

# Returns when either half exits (or on Ctrl-C, via the trap).
wait -n "$api" "$ui"
