#!/usr/bin/env bash
# collect-evidence.sh — gather the INSIDE-VM evidence for docs/VALIDATION_EVIDENCE.md.
#
# This runs the inside-VM portion of the proof pack and prints labelled output you
# can paste into the evidence table. It does NOT cover host/external rows — those
# must be run from a separate machine (or the VM host) because, by design, the
# internal ports are unreachable from inside the VM's own loopback tests.
#
# Usage: bash scripts/collect-evidence.sh
#        bash scripts/collect-evidence.sh | tee evidence-$(date +%Y%m%d).txt

set -uo pipefail

TRACE_ID="demo-$(date +%s 2>/dev/null || echo 001)"

hdr(){ printf '\n\033[1m========== %s ==========\033[0m\n' "$1"; }
run(){ printf '\n\033[36m$ %s\033[0m\n' "$1"; eval "$1" 2>&1 || true; }

hdr "1. Listening interfaces (expect :80 public, 3001-3003 on 127.0.0.1)"
run "sudo ss -tulpen | grep -E ':80|:3001|:3002|:3003'"

hdr "2. Firewall state (expect active, deny incoming, 80+SSH allowed, 3001-3003 denied)"
run "sudo ufw status verbose"

hdr "7. Internal service discovery (expect 127.0.0.1 + healthy JSON)"
for name in ride-booking.internal driver-matching.internal ride-dispatch.internal; do
    run "getent hosts $name"
done
run "curl -s http://ride-booking.internal:3001/health"
run "curl -s http://driver-matching.internal:3002/health"
run "curl -s http://ride-dispatch.internal:3003/health"

hdr "3/4. Public entry through Nginx (expect ok + ride-booking health)"
run "curl -s http://localhost/nginx-health"
run "curl -s http://localhost/health"

hdr "9. Nginx version hidden (expect 'Server: nginx' with no version)"
run "curl -sI http://localhost/nginx-health | grep -i '^server'"

hdr "10/15. Happy-path trace + client IP (trace id: $TRACE_ID)"
run "curl -s -X POST http://localhost/ride/request -H 'X-Request-ID: $TRACE_ID' -H 'X-Forwarded-For: 203.0.113.9' | python3 -m json.tool"
echo
echo "  --- log lines tagged with $TRACE_ID across all services ---"
run "sudo journalctl -u ride-booking -u driver-matching -u ride-dispatch --since '2 minutes ago' | grep $TRACE_ID"

hdr "14. Boot persistence (expect all 'enabled')"
run "systemctl is-enabled ride-booking driver-matching ride-dispatch nginx"

hdr "Systemd service states (expect all 'active')"
run "systemctl is-active ride-booking driver-matching ride-dispatch nginx"

printf '\n\033[1mDone.\033[0m Paste the relevant output into docs/VALIDATION_EVIDENCE.md.\n'
printf 'Remember to also run the HOST/EXTERNAL rows from a separate machine:\n'
printf '  curl -i --connect-timeout 3 http://<VM_IP>:3002/health   # expect fail\n'
printf '  curl -i http://<VM_IP>/nginx-health                       # expect 200\n'
