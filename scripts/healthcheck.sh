#!/usr/bin/env bash
# healthcheck.sh — quick operational snapshot of the ride booking system.

# Pretty-print JSON from stdin; fall back to raw text if it isn't valid JSON.
pp(){ python3 -m json.tool 2>/dev/null || cat; }

echo "== Services =="
systemctl status ride-booking driver-matching ride-dispatch nginx --no-pager

echo
echo "== Health (through Nginx — hits ride-booking) =="
curl -s localhost/health | pp
echo "== Health (direct to each internal service) =="
curl -s localhost:3001/health | pp
curl -s localhost:3002/health | pp
curl -s localhost:3003/health | pp

echo
echo "== Full chain (POST /ride/request) =="
curl -s -X POST localhost/ride/request | pp

echo
echo "== Nginx-only health (no service involved) =="
curl -s localhost/nginx-health

echo
echo "== Ports =="
sudo ss -tulpn | grep -E '3001|3002|3003|:80'

echo
echo "== Recent Nginx access log =="
sudo tail -n 5 /var/log/nginx/ride-booking_access.log 2>/dev/null || echo "  (no access log yet)"
