#!/usr/bin/env bash
# wait-for-deps.sh — blocks until the driver-matching and ride-dispatch
# services are healthy.
#
# Used as ExecStartPre in ride-booking.service.
# systemd's After= only guarantees that the process started, not that
# the application is ready to serve traffic. This script closes that gap.

set -euo pipefail

DEPS=(
    "http://driver-matching.internal:3002/health"
    "http://ride-dispatch.internal:3003/health"
)
TIMEOUT="${DEPS_TIMEOUT:-60}"
elapsed=0

echo "Waiting for dependencies (timeout: ${TIMEOUT}s)..." >&2

for url in "${DEPS[@]}"; do
    echo "  Checking $url ..." >&2
    until curl -fsS --max-time 2 "$url" > /dev/null 2>&1; do
        if [ "$elapsed" -ge "$TIMEOUT" ]; then
            echo "  TIMEOUT: $url did not become healthy within ${TIMEOUT}s" >&2
            exit 1
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    echo "  OK: $url is healthy" >&2
done

echo "All dependencies are healthy. Starting ride-booking." >&2
