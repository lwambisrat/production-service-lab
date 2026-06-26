# What Happens If driver-matching Is Unavailable?

## Overview

driver-matching is the Driver Matching Service. ride-booking depends on it to complete every ride booking request. If driver-matching goes down, the entire booking flow breaks at the second hop.

---

## What Happens to the Request

When a user sends a request and driver-matching is unavailable:

1. Client sends `POST /ride/request` through Nginx
2. Nginx forwards it to ride-booking
3. ride-booking tries to call `http://driver-matching.internal:3002/driver/match`
4. The connection fails (or times out after `DOWNSTREAM_TIMEOUT`, default 5 seconds)
5. ride-booking catches the exception and returns a `502` error to the client

The client receives:

```json
{
  "request_id": "<uuid>",
  "status": "error",
  "message": "Driver matching service is unavailable. Please try again later."
}
```

---

## What Appears in the Logs

ride-booking logs the failure as a structured JSON error:

```json
{
  "timestamp": "2026-06-20T...",
  "level": "ERROR",
  "service": "ride-booking",
  "event": "driver_matching_unreachable",
  "request_id": "<uuid>",
  "target": "driver-matching",
  "error": "..."
}
```

driver-matching produces no logs because it never received the request.

View the logs:

```bash
sudo journalctl -u ride-booking -n 30
```

---

## What Happens to ride-booking

ride-booking keeps running. It does not crash. It simply cannot complete the booking flow until driver-matching is restored.

Every request during the outage will return the same 502 error until driver-matching comes back.

---

## What Happens at Boot

The systemd service file for ride-booking contains:

```ini
After=network-online.target driver-matching.service ride-dispatch.service
Wants=network-online.target driver-matching.service ride-dispatch.service
ExecStartPre=/opt/ridelab/scripts/wait-for-deps.sh
```

This means:

- `After` — ride-booking is ordered to start *after* driver-matching and ride-dispatch
- `Wants` — driver-matching and ride-dispatch are pulled in as soft dependencies (a
  weaker link than `Requires`; ride-booking is not force-stopped if they later stop)
- `ExecStartPre` — the readiness gate (`wait-for-deps.sh`) blocks A's startup
  until driver-matching and ride-dispatch actually answer `/health`. `After=` only guarantees the
  processes launched, not that they are ready — this script closes that gap.

If driver-matching is down at boot time, the readiness gate times out and ride-booking
fails to start, so it will not become operational until driver-matching is healthy.

---

## How to Diagnose It

### Step 1 — Check if driver-matching is running

```bash
sudo systemctl status driver-matching
```

If it shows `inactive` or `failed`, driver-matching is down.

### Step 2 — Check why driver-matching went down

```bash
sudo journalctl -u driver-matching -n 50 -l
```

Look for:

- Python errors or import failures
- Port already in use
- File not found errors

### Step 3 — Check ride-booking's logs for the error

```bash
sudo journalctl -u ride-booking -n 20
```

You should see `driver_matching_unreachable` with a connection error pointing to `driver-matching.internal`.

### Step 4 — Confirm the port is not listening

```bash
sudo ss -tulpn | grep 3002
```

If nothing is returned, nothing is listening on port 3002 — driver-matching is definitely down.

---

## How to Recover

Restart driver-matching first, then ride-booking:

```bash
sudo systemctl restart driver-matching
sudo systemctl restart ride-booking
```

Always restart in dependency order. If you restart ride-booking before driver-matching is up, the `wait-for-deps.sh` readiness gate (`ExecStartPre`) blocks and eventually times out, so ride-booking fails to start until driver-matching is healthy.

Verify recovery:

```bash
sudo systemctl status driver-matching ride-booking
curl -s -X POST http://localhost/ride/request
```

---

## How to Simulate the Failure

Stop driver-matching intentionally:

```bash
sudo systemctl stop driver-matching
```

Then trigger a request to observe the failure:

```bash
curl -s -X POST http://localhost/ride/request
```

Watch the logs in real time:

```bash
sudo journalctl -f -u ride-booking -u driver-matching
```

---

## Quick Reference

```bash
# Check if driver-matching is running
sudo systemctl status driver-matching

# Read driver-matching logs
sudo journalctl -u driver-matching -n 50 -l

# Read ride-booking error logs
sudo journalctl -u ride-booking -n 20

# Check port 3002
sudo ss -tulpn | grep 3002

# Restart in correct order
sudo systemctl restart driver-matching
sudo systemctl restart ride-booking

# Verify full chain is working again
curl -s -X POST http://localhost/ride/request
```
