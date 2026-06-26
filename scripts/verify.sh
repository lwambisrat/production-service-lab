#!/usr/bin/env bash
# verify.sh — one-command proof that the system is healthy and secure.
# Exit code 0 = all critical checks passed.

set -uo pipefail

PASS=0; FAIL=0

green(){ printf '  \033[32mPASS\033[0m  %s\n' "$1"; PASS=$((PASS+1)); }
red(){   printf '  \033[31mFAIL\033[0m  %s\n' "$1"; FAIL=$((FAIL+1)); }
note(){  printf '  ----  %s\n' "$1"; }
hdr(){   printf '\n\033[1m%s\033[0m\n' "$1"; }

# ---------------------------------------------------------------------------
hdr "1. Service Discovery — name resolution"
# ---------------------------------------------------------------------------
for name in ride-booking.internal driver-matching.internal ride-dispatch.internal; do
    ip=$(getent hosts "$name" 2>/dev/null | awk '{print $1}')
    if [ "$ip" = "127.0.0.1" ]; then
        green "$name → $ip"
    else
        red   "$name did not resolve (check /etc/hosts)"
    fi
done

# ---------------------------------------------------------------------------
hdr "2. Port Binding — services must bind to 127.0.0.1 only"
# ---------------------------------------------------------------------------
for port in 3001 3002 3003; do
    binding=$(ss -ltnH "sport = :$port" 2>/dev/null | awk '{print $4}' | head -1)
    if echo "$binding" | grep -q "^127\.0\.0\.1"; then
        green "port $port bound to $binding"
    else
        red   "port $port binding is '$binding' — expected 127.0.0.1:$port"
    fi
done

# Nginx must listen publicly
nginx_bind=$(ss -ltnH "sport = :80" 2>/dev/null | awk '{print $4}' | head -1)
if [ -n "$nginx_bind" ]; then
    green "Nginx listening on $nginx_bind"
else
    red   "Nginx is not listening on port 80"
fi

# ---------------------------------------------------------------------------
hdr "3. Health Endpoints — direct service checks"
# ---------------------------------------------------------------------------
for port in 3001 3002 3003; do
    if curl -fsS --max-time 3 "http://127.0.0.1:$port/health" > /dev/null 2>&1; then
        green "service on port $port responded to /health"
    else
        red   "service on port $port did not respond to /health"
    fi
done

# ---------------------------------------------------------------------------
hdr "4. End-to-End — full request chain through Nginx"
# ---------------------------------------------------------------------------
response=$(curl -fsS --max-time 10 -X POST http://localhost/ride/request 2>/dev/null || true)
if echo "$response" | grep -q '"status"'; then
    green "POST /ride/request returned a valid response"
    echo "$response" | python3 -m json.tool 2>/dev/null | sed 's/^/        /' || note "Response: $response"
else
    red   "POST /ride/request failed or returned unexpected response"
    note  "Response: $response"
fi

# ---------------------------------------------------------------------------
hdr "5. Network Security — internal ports must be unreachable externally"
# ---------------------------------------------------------------------------
PUBLIC_IP=$(hostname -I | awk '{print $1}')
note "Testing external access using VM IP: $PUBLIC_IP"

for port in 3002 3003; do
    if curl -fsS --max-time 3 "http://${PUBLIC_IP}:${port}/health" > /dev/null 2>&1; then
        red   "port $port is reachable externally — should be blocked"
    else
        green "port $port is correctly blocked from external access"
    fi
done

if curl -fsS --max-time 3 "http://${PUBLIC_IP}/health" > /dev/null 2>&1; then
    green "port 80 (Nginx) is reachable externally"
else
    red   "port 80 (Nginx) is not reachable — check Nginx and firewall"
fi

# ---------------------------------------------------------------------------
hdr "6. Firewall"
# ---------------------------------------------------------------------------
if command -v ufw &>/dev/null; then
    status=$(ufw status | head -1)
    note "UFW: $status"
    ufw status | grep -E '3001|3002|3003|80' | while read -r line; do
        note "  $line"
    done
else
    note "ufw not installed"
fi

# ---------------------------------------------------------------------------
hdr "7. Systemd Service Status"
# ---------------------------------------------------------------------------
for svc in ride-booking driver-matching ride-dispatch nginx; do
    state=$(systemctl is-active "$svc" 2>/dev/null || echo "unknown")
    if [ "$state" = "active" ]; then
        green "$svc is $state"
    else
        red   "$svc is $state"
    fi
done

# ---------------------------------------------------------------------------
printf '\n\033[1mResult: PASS=%d  FAIL=%d\033[0m\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
