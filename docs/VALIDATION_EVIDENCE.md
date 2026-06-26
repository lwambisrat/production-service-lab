# Validation Evidence Pack

> **Purpose:** Configuration alone is not proof. This document records *demonstrated*
> behavior — for every major claim the system makes, it lists the command, where it
> was run, the expected result, the actual result, and a pass/fail verdict.
>
> **How to fill this in:** Run `bash scripts/collect-evidence.sh` *inside the VM* to
> generate the inside-VM evidence automatically, then paste the relevant output into
> the "Actual" cells below. Run the host/external rows from a separate machine (or the
> host running the VM) and paste those results too. Replace every `TODO` and set each
> `Result` to **Pass** or **Fail**.

- **VM public IP:** `TODO` (used as `<VM_IP>` below)
- **Date collected:** `TODO`
- **Collected by:** `TODO`
- **Note:** This evidence reflects a live run. Re-collect after any change to services,
  Nginx, firewall, or systemd units.

---

## 1. Proof Pack

| # | Claim | Where | Command | Expected | Actual | Result |
|---|-------|-------|---------|----------|--------|--------|
| 1 | Listening interfaces are correct | Inside VM | `sudo ss -tulpen \| grep -E ":80\|:3001\|:3002\|:3003"` | 80 public (`0.0.0.0`/`*`); 3001–3003 bound to `127.0.0.1` only | `TODO` | TODO |
| 2 | Firewall is active and scoped | Inside VM | `sudo ufw status verbose` | UFW active; default deny incoming; 80 + OpenSSH allowed; 3001–3003 denied | `TODO` | TODO |
| 3 | Public entry works | Host/external | `curl -i http://<VM_IP>/nginx-health` | `200 OK`, body `ok` | `TODO` | TODO |
| 4 | Public health via Nginx works | Host/external | `curl -i http://<VM_IP>/health` | `200`, `{"service":"ride-booking",...}` | `TODO` | TODO |
| 5a | ride-booking not directly public | Host/external | `curl -i --connect-timeout 3 http://<VM_IP>:3001/health` | Fails (timeout / refused) | `TODO` | TODO |
| 5b | driver-matching not directly public | Host/external | `curl -i --connect-timeout 3 http://<VM_IP>:3002/health` | Fails (timeout / refused) | `TODO` | TODO |
| 5c | ride-dispatch not directly public | Host/external | `curl -i --connect-timeout 3 http://<VM_IP>:3003/health` | Fails (timeout / refused) | `TODO` | TODO |
| 6 | Host port-forward not exposing internals | Host machine | `curl --connect-timeout 3 http://127.0.0.1:3002/health` | Fails — VM tooling is not forwarding internal ports to the host | `TODO` | TODO |
| 7 | Internal discovery resolves + works | Inside VM | `getent hosts driver-matching.internal && curl -s http://driver-matching.internal:3002/health` | Resolves to `127.0.0.1`; returns `200` health JSON | `TODO` | TODO |
| 8 | Nginx route boundary — internal services not routed | Host/external | `curl -i http://<VM_IP>/driver/match` (and `/ride/dispatch`) | Proxied to ride-booking, which has no such route → `404` from `ride-booking`. driver-matching and ride-dispatch are never reached. | `TODO` | TODO |
| 9 | Nginx version hidden | Host/external | `curl -sI http://<VM_IP>/nginx-health \| grep -i server` | `Server: nginx` with **no version** (`server_tokens off`) | `TODO` | TODO |
| 10 | Happy-path trace across all hops | Host + VM logs | `curl -s -X POST http://<VM_IP>/ride/request -H "X-Request-ID: demo-001"` then `journalctl ... \| grep demo-001` | Same `demo-001` appears in ride-booking, driver-matching, ride-dispatch, and the callback | `TODO` | TODO |
| 11 | Failure behavior is controlled | Inside VM + host | Stop driver-matching, then `curl -i -X POST http://<VM_IP>/ride/request` | `502` with a clear message; `driver_matching_unreachable` logged at ERROR | `TODO` | TODO |
| 12 | systemd restart-on-crash | Inside VM | `sudo pkill -f 'uvicorn app:app --host 127.0.0.1 --port 3002'; sleep 4; systemctl status driver-matching` | Service auto-restarts (`Restart=on-failure`); journal records the restart | `TODO` | TODO |
| 13 | Dependency readiness gate | Inside VM | `sudo systemctl stop driver-matching; sudo systemctl restart ride-booking` | ride-booking blocks on `wait-for-deps.sh` and fails to start until driver-matching is healthy | `TODO` | TODO |
| 14 | Boot persistence | Inside VM | `systemctl is-enabled ride-booking driver-matching ride-dispatch nginx`; `sudo reboot`; recheck after boot | All `enabled`; all `active` after reboot with no manual action | `TODO` | TODO |
| 15 | Client IP is logged | Inside VM | `curl -s -X POST http://localhost/ride/request -H 'X-Forwarded-For: 203.0.113.9'; journalctl -u ride-booking -n 20` | `ride_request_received` log includes `"client_ip": "203.0.113.9"` | `TODO` | TODO |

---

## 2. Minimum commands to capture (inside VM)

```bash
sudo ss -tulpen | grep -E ":80|:3001|:3002|:3003"
sudo ufw status verbose
getent hosts ride-booking.internal driver-matching.internal ride-dispatch.internal
curl -s http://localhost/nginx-health
curl -s http://localhost/health
curl -s -X POST http://localhost/ride/request -H "X-Request-ID: demo-001"
sudo journalctl -u ride-booking -u driver-matching -u ride-dispatch --since "5 minutes ago" | grep demo-001
```

## 3. Minimum commands to capture (host / external)

```bash
VM_IP=<VM_IP>
curl -i http://$VM_IP/nginx-health
curl -i --connect-timeout 3 http://$VM_IP:3001/health   # expect fail
curl -i --connect-timeout 3 http://$VM_IP:3002/health   # expect fail
curl -i --connect-timeout 3 http://$VM_IP:3003/health   # expect fail
curl -i --connect-timeout 3 http://127.0.0.1:3002/health # from host; expect fail
```

---

## 4. Worked example (illustrative — replace with your real output)

| Claim | Command | Where | Expected | Actual | Result |
|-------|---------|-------|----------|--------|--------|
| Only Nginx is public | `curl http://<VM_IP>:3002/health` | Host/external | Fail | `curl: (28) Connection timed out` | **Pass** |
| driver-matching works internally | `curl http://driver-matching.internal:3002/health` | Inside VM | `200 OK` | `{"service":"driver-matching","status":"healthy","port":3002}` | **Pass** |
| UFW active | `sudo ufw status verbose` | Inside VM | Active, deny inbound | `Status: active` / `Default: deny (incoming)` | **Pass** |
| driver-matching restarts | `pkill ...` + `systemctl status` | Inside VM | Active after crash | `Active: active (running)` after ~2s | **Pass** |
| Full trace works | `journalctl ... \| grep demo-001` | Inside VM | logs found across all services | 4 log lines across all services | **Pass** |

---

## 5. Why this matters

- **Reduces false confidence** — config can exist while runtime state is wrong; evidence shows what is actually running.
- **Speeds incident response** — operators already know how to check exposure, routing, firewall, dependency health, and logs.
- **Improves handover** — another engineer can verify the system without the original authors.
- **Separates failure domains** — external curls, binding checks, firewall output, and Nginx logs isolate proxy vs. firewall vs. VM-runtime vs. app.
- **Catches accidental exposure** — host port-forward tests catch cases where VM tooling exposes internal ports despite loopback binding.
