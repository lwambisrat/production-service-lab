# Testing Guide — All Scenarios

A single, ordered walkthrough to exercise every behaviour the system claims:
health, the full request chain, request tracing, failure handling, resilience,
boot recovery, and network security. Run it **on the VM**, top to bottom.

Tip: keep a second terminal following logs while you run the failure scenarios:

```bash
sudo journalctl -f -u ride-booking -u driver-matching -u ride-dispatch -o cat
```

---

## 0. Deploy / redeploy

```bash
cd ~/production-service-lab
git pull
bash scripts/install.sh       
```

If services get stuck `activating` with `address already in use`, an old
deployment is still holding the ports. Clear it once:

```bash
sudo systemctl stop ride-booking driver-matching ride-dispatch
sudo pkill -f 'uvicorn services.service-' || true      
sudo ss -tulpn | grep -E ':3001|:3002|:3003' || echo "ports free"
sudo systemctl start ride-dispatch driver-matching ride-booking
```

---

## 1. One-command proof

```bash
bash scripts/verify.sh
```
Expect `Result: PASS=… FAIL=0`. (If run without sudo, the firewall line reports
"need root" — harmless.) The steps below let you watch each behaviour happen.

---

## 2. Health checks

```bash
curl -s http://localhost/nginx-health                    # -> ok   (Nginx itself, no service)
curl -s http://localhost/health | python3 -m json.tool   # ride-booking, via Nginx
curl -s http://localhost:3001/health                     # ride-booking direct
curl -s http://localhost:3002/health                     # driver-matching direct
curl -s http://localhost:3003/health                     # ride-dispatch direct
```
Expect each service: `{"service":"<name>","status":"healthy","port":<port>}`.

---

## 3. Full chain — request to ride-booking (A → B → C → A)

```bash
curl -s -X POST http://localhost/ride/request | python3 -m json.tool
```
Expect `"status": "accepted"`, a `ride_id` (`RIDE-XXXXXX`), and a `matched_driver`.
That one call exercised all three services plus the callback.

---

## 4. Request tracing — follow one request across all services

```bash
curl -s -X POST http://localhost/ride/request \
  -H "X-Request-ID: demo-001" -H "X-Forwarded-For: 203.0.113.9" >/dev/null

sudo journalctl -u ride-booking -u driver-matching -u ride-dispatch -o cat \
  --since "1 min ago" | grep demo-001
```
Expect log lines from **all three** services with `request_id=demo-001`, the same
`ride_id`, plus `outcome`/`duration_ms` on the forwarding events and
`"client_ip":"203.0.113.9"` on `ride_request_received`.

Follow one ride by its **business id** instead:

```bash
sudo journalctl -u ride-booking -u driver-matching -u ride-dispatch -o cat | grep RIDE-XXXXXX
```

---

## 5. Failure — driver-matching is down (the 502 path)

```bash
sudo systemctl stop driver-matching
curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST http://localhost/ride/request   # -> 502
curl -s -X POST http://localhost/ride/request | python3 -m json.tool                  # clear error JSON
sudo journalctl -u ride-booking -n 5 -o cat | grep driver_matching_unreachable        # ERROR, outcome=failure
sudo systemctl start driver-matching                                                   # recover
curl -s -X POST http://localhost/ride/request | python3 -m json.tool                   # accepted again
```

---

## 6. Failure — ride-dispatch is down (driver matched, dispatch fails)

```bash
sudo systemctl stop ride-dispatch
curl -s -o /dev/null -w "HTTP %{http_code}\n" -X POST http://localhost/ride/request   # -> 502
sudo journalctl -u driver-matching -n 5 -o cat | grep dispatch_service_unreachable
sudo systemctl start ride-dispatch
```

---

## 7. Resilience — auto-restart on crash

```bash
sudo systemctl kill -s SIGKILL driver-matching      # hard kill
sleep 4
systemctl is-active driver-matching                 # -> active (Restart=on-failure brought it back)
sudo journalctl -u driver-matching -n 10 -o cat | grep -E 'service_started|service_stopping'
```

---

## 8. Dependency readiness gate

Note: simply stopping a dependency and restarting ride-booking does **not** show
the gate — ride-booking's `Wants=` pulls the dependency back up. To prove the
gate, **mask** the dependency so systemd cannot start it:

```bash
sudo systemctl mask --now driver-matching            # stop it AND block it from starting
sudo systemctl restart ride-booking &                # runs the readiness gate; will block

sleep 5
systemctl status ride-booking --no-pager | head -6   # -> "activating (start-pre)" — stuck on wait-for-deps
sudo journalctl -u ride-booking -n 5 -o cat | grep wait-for-deps   # "waiting for .../health ..."

# now release it — the gate detects health and ride-booking finishes starting
sudo systemctl unmask driver-matching
sudo systemctl start driver-matching
sleep 3
systemctl is-active ride-booking                     # -> active
```

If you'd rather see the gate **time out and fail** (it gives up after
`DEPS_TIMEOUT`, default 60s), leave the dependency masked and wait — ride-booking
goes to `failed`. Then `unmask` + `start` the dependency and restart ride-booking.

---

## 9. Boot persistence

```bash
systemctl is-enabled ride-booking driver-matching ride-dispatch nginx   # all -> enabled
sudo reboot
# reconnect, then:
systemctl is-active ride-booking driver-matching ride-dispatch nginx    # all -> active, no manual steps
curl -s -X POST http://localhost/ride/request | python3 -m json.tool
```

---

## 10. Network security

```bash
sudo ss -tulpn | grep -E ':3001|:3002|:3003'        # all 127.0.0.1, never 0.0.0.0
sudo ufw status verbose                              # active; 80 + SSH allowed; 3001-3003 denied

VM_IP=$(hostname -I | awk '{print $1}')
curl -m3 http://$VM_IP:3002/health                   # FAIL (internal port sealed)
curl -m3 http://$VM_IP/health                        # SUCCEED (Nginx is public)
```

Also run the **host port-forward** check from your Mac (not the VM): a Lima
port-forward can re-expose internal ports despite loopback binding —
`curl --connect-timeout 3 http://127.0.0.1:3002/health` from the host should fail.

---

## 11. Service discovery

```bash
getent hosts ride-booking.internal driver-matching.internal ride-dispatch.internal   # each -> 127.0.0.1
```

---

## 12. Nginx logs

```bash
sudo tail -n 5 /var/log/nginx/ride-booking_access.log   # includes client IP, status, trace=
sudo tail -n 5 /var/log/nginx/ride-booking_error.log    # 502s / upstream issues
```

---

## 13. Capture evidence

```bash
bash scripts/collect-evidence.sh | tee evidence-$(date +%Y%m%d).txt
```
Paste the relevant output into [VALIDATION_EVIDENCE.md](VALIDATION_EVIDENCE.md),
and run the host/external rows from your Mac.
