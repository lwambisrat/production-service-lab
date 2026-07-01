# Validation Evidence Pack

> **Purpose:** Configuration alone is not proof. This document records *demonstrated*
> behavior — for every major claim the system makes, it lists the command, where it
> was run, the expected result, the actual result, and a pass/fail verdict.
>
> **Collection method:** Inside-VM results were gathered with
> `bash scripts/collect-evidence.sh` and focused systemd tests. External results
> were collected from macOS through Lima's host-forwarded Nginx entry point.

- **VM access:** Lima guest `192.168.5.15`; macOS entry point
  `http://127.0.0.1:8080`
- **Note:** This evidence reflects a live run. Re-collect after any change to services,
  Nginx, firewall, or systemd units.

---

## 1. Proof Pack

| # | Claim | Where | Command | Expected | Actual | Result |
|---|-------|-------|---------|----------|--------|--------|
| 1 | Listening interfaces are correct | Inside VM | `sudo ss -tulpen \| grep -E ":80\|:3001\|:3002\|:3003"` | 80 public (`0.0.0.0`/`*`); 3001–3003 bound to `127.0.0.1` only | Port 80 listened on `0.0.0.0`; ports 3001, 3002, and 3003 listened on `127.0.0.1` only. | **Pass** |
| 2 | Firewall is active and scoped | Inside VM | `sudo ufw status verbose` | UFW active; default deny incoming; 80 + OpenSSH allowed; 3001–3003 denied | UFW was active with default deny incoming; ports 22 and 80 were allowed, and ports 3001–3003 were denied for IPv4 and IPv6. | **Pass** |
| 3 | Public entry works | macOS host | `curl -i http://127.0.0.1:8080/nginx-health` | `200 OK`, body `ok` | Lima forwarded guest Nginx port 80 to host port 8080; the endpoint returned `200 OK` with body `ok`. | **Pass** |
| 4 | Public health via Nginx works | macOS host | `curl -i http://127.0.0.1:8080/health` | `200`, `{"service":"ride-booking",...}` | Returned `200 OK` and `{"service":"ride-booking","status":"healthy","port":3001}`. | **Pass** |
| 5a | ride-booking not directly public | macOS host | `curl -i --connect-timeout 3 http://127.0.0.1:3001/health` | Fails (timeout / refused) | Connection refused; Lima reported `Not forwarding TCP 127.0.0.1:3001`. | **Pass** |
| 5b | driver-matching not directly public | macOS host | `curl -i --connect-timeout 3 http://127.0.0.1:3002/health` | Fails (timeout / refused) | Connection refused; Lima reported `Not forwarding TCP 127.0.0.1:3002`. | **Pass** |
| 5c | ride-dispatch not directly public | macOS host | `curl -i --connect-timeout 3 http://127.0.0.1:3003/health` | Fails (timeout / refused) | Connection refused; Lima reported `Not forwarding TCP 127.0.0.1:3003`. | **Pass** |
| 6 | Host port-forward not exposing internals | macOS host | `curl --connect-timeout 3 http://127.0.0.1:3002/health` | Fails — VM tooling is not forwarding internal ports to the host | The request was refused after Lima's 3001–3003 forwarding rules were explicitly disabled. | **Pass** |
| 7 | Internal discovery resolves + works | Inside VM | `getent hosts driver-matching.internal && curl -s http://driver-matching.internal:3002/health` | Resolves to `127.0.0.1`; returns `200` health JSON | All three `.internal` names resolved to `127.0.0.1`; each service returned healthy JSON on its internal port. | **Pass** |
| 8 | Nginx route boundary — internal services not routed | macOS host | `curl -i http://127.0.0.1:8080/driver/match` (and `/ride/dispatch`) | Proxied to ride-booking, which has no such route → `404` from `ride-booking`. driver-matching and ride-dispatch are never reached. | Both requests returned structured `404` responses identifying `ride-booking`; neither internal endpoint was routed publicly. | **Pass** |
| 9 | Nginx version hidden | macOS host | `curl -sI http://127.0.0.1:8080/nginx-health \| grep -i server` | `Server: nginx` with **no version** (`server_tokens off`) | Response contained `Server: nginx` with no version number. | **Pass** |
| 10 | Happy-path trace across all hops | Host + VM logs | `curl -s -X POST http://127.0.0.1:8080/ride/request -H "X-Request-ID: demo-001"` then `journalctl ... \| grep demo-001` | Same `demo-001` appears in ride-booking, driver-matching, ride-dispatch, and the callback | Request `demo-1782537533` completed with ride `RIDE-B92C03`; the same IDs appeared in ride-booking, driver-matching, ride-dispatch, and callback log events. | **Pass** |
| 11 | Failure behavior is controlled | Inside VM + macOS host | Stop driver-matching, then `curl -i -X POST http://127.0.0.1:8080/ride/request` | `502` with a clear message; `driver_matching_unreachable` logged at ERROR | Request `vm-fail-b-20260701` returned `502 Bad Gateway` with a clear unavailable message; ride-booking logged `driver_matching_unreachable` at `ERROR` with `outcome=failure`. Starting B restored a `200 OK` accepted ride. | **Pass** |
| 12 | systemd restart-on-crash | Inside VM | Kill the driver-matching main PID; wait four seconds; check status and journal | Service auto-restarts (`Restart=on-failure`); journal records the restart | Killing PID 2576 with `SIGKILL` produced `Failed with result 'signal'`; systemd scheduled restart counter 1 and started new PID 3008. Service state returned to `active`. | **Pass** |
| 13 | Dependency readiness gate | Inside VM | Temporarily mask driver-matching, then restart ride-booking | ride-booking remains in start-pre until driver-matching is healthy | With B unavailable, ride-booking remained `activating` / `start-pre` in `wait-for-deps.sh`. After restoring and starting B, the gate detected both dependencies as healthy and ride-booking became `active`. | **Pass** |
| 14 | Boot persistence | Inside VM | `systemctl is-enabled ride-booking driver-matching ride-dispatch nginx`; `sudo reboot`; recheck after boot | All `enabled`; all `active` after reboot with no manual action | Before and after reboot, all four units reported `enabled`; after reboot all reported `active`. A post-boot full-chain request returned `200 OK` with `"status":"accepted"`. | **Pass** |
| 15 | Client IP is logged | Inside VM | `curl -s -X POST http://localhost/ride/request -H 'X-Forwarded-For: 203.0.113.9'; journalctl -u ride-booking -n 20` | `ride_request_received` log includes `"client_ip": "203.0.113.9"` | The `ride_request_received` event recorded `"client_ip": "203.0.113.9, 127.0.0.1"`. | **Pass** |

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
VM_ENTRY=http://127.0.0.1:8080
curl -i "$VM_ENTRY/nginx-health"
curl -i "$VM_ENTRY/health"
curl -i --connect-timeout 3 http://127.0.0.1:3001/health   # expect fail
curl -i --connect-timeout 3 http://127.0.0.1:3002/health   # expect fail
curl -i --connect-timeout 3 http://127.0.0.1:3003/health   # expect fail
```

---

## 4. Why this matters

- **Reduces false confidence** — config can exist while runtime state is wrong; evidence shows what is actually running.
- **Speeds incident response** — operators already know how to check exposure, routing, firewall, dependency health, and logs.
- **Improves handover** — another engineer can verify the system without the original authors.
- **Separates failure domains** — external curls, binding checks, firewall output, and Nginx logs isolate proxy vs. firewall vs. VM-runtime vs. app.
- **Catches accidental exposure** — host port-forward tests catch cases where VM tooling exposes internal ports despite loopback binding.
