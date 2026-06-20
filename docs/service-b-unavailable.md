# What Happens If Service B Is Unavailable?

## Overview

Service B is the Driver Matching Service. Service A depends on it to complete every ride booking request. If Service B goes down, the entire booking flow breaks at the second hop.

---

## What Happens to the Request

When a user sends a request and Service B is unavailable:

1. Client sends `GET /greet-driver-matching` through Nginx
2. Nginx forwards it to Service A
3. Service A tries to call `http://service-b.internal:3002/greet`
4. The connection times out after 5 seconds
5. Service A catches the exception and returns a `500` error to the client

The client receives:

```json
{
  "request_id": "<uuid>",
  "status": "error",
  "message": "Failed to reach driver-matching"
}
```

---

## What Appears in the Logs

Service A logs the failure as a structured JSON error:

```json
{
  "timestamp": "2026-06-20T...",
  "service": "ride-booking",
  "event": "request_failed",
  "request_id": "<uuid>",
  "path": "/greet-driver-matching",
  "status": 500,
  "error": "..."
}
```

Service B produces no logs because it never received the request.

View the logs:

```bash
sudo journalctl -u ride-booking -n 30
```

---

## What Happens to Service A

Service A keeps running. It does not crash. It simply cannot complete the booking flow until Service B is restored.

Every request during the outage will return the same 500 error until Service B comes back.

---

## What Happens at Boot

The systemd service file for Service A contains:

```ini
After=network.target driver-matching.service ride-dispatch.service
Requires=driver-matching.service ride-dispatch.service
```

This means:

- `After` — Service A will not start until Service B has started
- `Requires` — if Service B fails to start, Service A will also fail to start

If Service B is down at boot time, Service A will not become operational.

---

## How to Diagnose It

### Step 1 — Check if Service B is running

```bash
sudo systemctl status driver-matching
```

If it shows `inactive` or `failed`, Service B is down.

### Step 2 — Check why Service B went down

```bash
sudo journalctl -u driver-matching -n 50 -l
```

Look for:

- Python errors or import failures
- Port already in use
- File not found errors

### Step 3 — Check Service A's logs for the error

```bash
sudo journalctl -u ride-booking -n 20
```

You should see `request_failed` with a connection error pointing to `service-b.internal`.

### Step 4 — Confirm the port is not listening

```bash
sudo ss -tulpn | grep 3002
```

If nothing is returned, nothing is listening on port 3002 — Service B is definitely down.

---

## How to Recover

Restart Service B first, then Service A:

```bash
sudo systemctl restart driver-matching
sudo systemctl restart ride-booking
```

Always restart in dependency order. If you restart Service A before Service B is up, systemd will refuse to start it because the `Requires=` dependency is not satisfied.

Verify recovery:

```bash
sudo systemctl status driver-matching ride-booking
curl -s http://localhost/greet-driver-matching
```

---

## How to Simulate the Failure

Stop Service B intentionally:

```bash
sudo systemctl stop driver-matching
```

Then trigger a request to observe the failure:

```bash
curl -s http://localhost/greet-driver-matching
```

Watch the logs in real time:

```bash
sudo journalctl -f -u ride-booking -u driver-matching
```

---

## Quick Reference

```bash
# Check if Service B is running
sudo systemctl status driver-matching

# Read Service B logs
sudo journalctl -u driver-matching -n 50 -l

# Read Service A error logs
sudo journalctl -u ride-booking -n 20

# Check port 3002
sudo ss -tulpn | grep 3002

# Restart in correct order
sudo systemctl restart driver-matching
sudo systemctl restart ride-booking

# Verify full chain is working again
curl -s http://localhost/greet-driver-matching
```
