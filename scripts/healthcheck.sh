#!/usr/bin/env bash
echo "== Services =="
systemctl status service-a service-b service-c nginx --no-pager

echo "== Health =="
curl -s http://localhost/service-a/health
echo
curl -s http://service-b.internal:3002/health
echo
curl -s http://service-c.internal:3003/health
echo

echo "== Ports =="
sudo ss -tulpn | grep -E '3001|3002|3003|80'
