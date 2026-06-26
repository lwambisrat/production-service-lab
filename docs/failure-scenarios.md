# Failure Scenarios and Investigation Guide

This guide covers how to simulate, investigate, and recover from common failures in the production service lab.

---

## Scenario 1 — Stop driver-matching

### Why this matters

driver-matching is a dependency of ride-booking. Stopping it simulates a real-world situation where an internal service goes down while the system is running.

### How to stop driver-matching

```bash
sudo systemctl stop driver-matching
```

### Verify it is stopped

```bash
sudo systemctl status driver-matching
```

Expected output shows `Active: inactive (dead)`.

Also confirm the port is no longer listening:

```bash
sudo ss -tulpn | grep 3002
```

Nothing should be returned.

### Trigger a request to observe the failure

```bash
curl -s -X POST http://localhost/ride/request
```

Expected response (HTTP 502):

```json
{
  "request_id": "<uuid>",
  "status": "error",
  "message": "Driver matching service is unavailable. Please try again later."
}
```

### Watch the logs during the failure

Open a second terminal and follow the logs before sending the request:

```bash
sudo journalctl -f -u ride-booking -u driver-matching -u ride-dispatch
```

You will see ride-booking log a `driver_matching_unreachable` event at ERROR level. driver-matching produces no logs because it never received the request.

### Recover from the failure

Restart in dependency order — driver-matching before ride-booking:

```bash
sudo systemctl restart driver-matching
sudo systemctl restart ride-booking
```

Verify recovery:

```bash
sudo systemctl status driver-matching ride-booking
curl -s -X POST http://localhost/ride/request
```

---

## Scenario 2 — Investigate a 502 Error

### What a 502 means

A 502 Bad Gateway means Nginx is running and received the request, but the service it is trying to reach (ride-booking) is down or not responding.

```
Client → Nginx ✓ → ride-booking ✗ → 502
```

### Step-by-step investigation

**Step 1 — Confirm Nginx is running**

```bash
sudo systemctl status nginx
```

If Nginx is down, that produces a different error (connection refused), not a 502.

**Step 2 — Check if ride-booking is responding**

```bash
curl -s http://localhost:3001/health
```

If this fails, ride-booking is down. That is the cause of the 502.

**Step 3 — Check ride-booking's status**

```bash
sudo systemctl status ride-booking
```

**Step 4 — Read ride-booking's logs**

```bash
sudo journalctl -u ride-booking -n 50 -l
```

Look for crash errors, Python tracebacks, or connection failures.

**Step 5 — Check if ride-booking's dependencies are up**

ride-booking requires driver-matching and ride-dispatch. If either is down, ride-booking may have failed to start.

```bash
sudo systemctl status driver-matching
sudo systemctl status ride-dispatch
```

**Step 6 — Check Nginx configuration**

```bash
sudo nginx -t
sudo nginx -T | grep proxy_pass
```

Confirm it is pointing to `127.0.0.1:3001`.

### Recovery

```bash
sudo systemctl restart ride-dispatch
sudo systemctl restart driver-matching
sudo systemctl restart ride-booking
sudo systemctl reload nginx
```

Verify:

```bash
curl -s http://localhost/health
```

---

## Scenario 3 — Investigate a Service Discovery Failure

### What service discovery failure looks like

Services call each other using names like `http://driver-matching.internal:3002`. If the name cannot be resolved to an IP address, the connection fails and the request chain breaks.

Symptoms:

- `curl -X POST http://localhost/ride/request` returns a 502 error
- ride-booking logs a `driver_matching_unreachable` event with a connection error to `driver-matching.internal`
- `getent hosts driver-matching.internal` returns nothing

### Step-by-step investigation

**Step 1 — Check the /etc/hosts entries**

```bash
cat /etc/hosts | grep internal
```

Expected:

```
127.0.0.1   ride-booking.internal
127.0.0.1   driver-matching.internal
127.0.0.1   ride-dispatch.internal
```

If any line is missing, that service name will not resolve.

**Step 2 — Test name resolution directly**

```bash
getent hosts ride-booking.internal
getent hosts driver-matching.internal
getent hosts ride-dispatch.internal
```

Each should return `127.0.0.1`. If a line returns nothing, the name is not resolving.

**Step 3 — Test connectivity by name**

```bash
curl -s http://driver-matching.internal:3002/health
curl -s http://ride-dispatch.internal:3003/health
```

If this works but services still cannot communicate, the problem is in the service code, not discovery.

**Step 4 — Check the resolver order**

```bash
cat /etc/nsswitch.conf | grep hosts
```

Must show `files` before `dns`:

```
hosts: files dns
```

If it shows `dns files`, Linux is querying DNS first and `.internal` names will fail.

Fix:

```bash
sudo nano /etc/nsswitch.conf
# Change: dns files
# To:     files dns
```

**Step 5 — Re-add missing entries**

```bash
echo '127.0.0.1   ride-booking.internal' | sudo tee -a /etc/hosts
echo '127.0.0.1   driver-matching.internal' | sudo tee -a /etc/hosts
echo '127.0.0.1   ride-dispatch.internal' | sudo tee -a /etc/hosts
```

**Step 6 — Restart services after fixing hosts**

```bash
sudo systemctl restart ride-dispatch
sudo systemctl restart driver-matching
sudo systemctl restart ride-booking
```

**Step 7 — Verify the full chain**

```bash
curl -s -X POST http://localhost/ride/request
```

---

## Scenario 4 — Investigate a Failed ride-booking Startup

### What happens

ride-booking will fail to start if:

- driver-matching or ride-dispatch is not running (systemd dependency enforcement)
- The virtual environment path is wrong
- The working directory does not exist
- A Python error prevents the process from starting

### Step-by-step investigation

**Step 1 — Check ride-booking's status**

```bash
sudo systemctl status ride-booking
```

Look for `Active: failed` or `Active: activating` stuck indefinitely.

**Step 2 — Read the full error from the logs**

```bash
sudo journalctl -u ride-booking -n 50 -l
```

Common log messages and what they mean:

| Log message | Cause |
| ----------- | ----- |
| `Dependency failed` | driver-matching is not running |
| `No such file or directory` | Wrong path in WorkingDirectory or ExecStart |
| `Failed to execute` | venv not created or uvicorn not installed |
| `Address already in use` | Port 3001 is occupied by another process |
| Python traceback | Syntax error or missing package in app.py |

**Step 3 — Check the dependencies first**

```bash
sudo systemctl status driver-matching
sudo systemctl status ride-dispatch
```

ride-booking will not start if either of these is down. Fix the dependency before trying to start ride-booking.

**Step 4 — Check the service file paths**

```bash
sudo systemctl cat ride-booking
```

Verify that:

- `User=` is the dedicated service account `ridelab`
- `WorkingDirectory=` points to `/opt/ridelab/services/ride-booking`
- `ExecStart=` points to `/opt/ridelab/venv/bin/uvicorn`

**Step 5 — Check the port is free**

```bash
sudo ss -tulpn | grep 3001
```

If something else is using port 3001:

```bash
sudo pkill -f uvicorn
```

**Step 6 — Check the deployed venv exists**

```bash
ls /opt/ridelab/venv/bin/uvicorn
```

If the file does not exist, the deploy is incomplete — just re-run the
installer, which recreates `/opt/ridelab` (code + venv) and restarts everything:

```bash
bash scripts/install.sh
```

**Step 7 — Reload and restart in order**

```bash
sudo systemctl daemon-reload
sudo systemctl restart ride-dispatch
sudo systemctl restart driver-matching
sudo systemctl restart ride-booking
```

**Step 8 — Verify**

```bash
sudo systemctl status ride-booking
curl -s http://localhost/health
curl -s -X POST http://localhost/ride/request
```

---

## Quick Reference — All Diagnostic Commands

```bash
# Check all service statuses at once
sudo systemctl status ride-booking driver-matching ride-dispatch nginx

# Read logs for each service
sudo journalctl -u ride-booking -n 50 -l
sudo journalctl -u driver-matching -n 50 -l
sudo journalctl -u ride-dispatch -n 50 -l

# Follow live logs across all services
sudo journalctl -f -u ride-booking -u driver-matching -u ride-dispatch

# Check ports
sudo ss -tulpn | grep -E '80|3001|3002|3003'

# Check service discovery
cat /etc/hosts | grep internal
getent hosts driver-matching.internal
getent hosts ride-dispatch.internal

# Check Nginx
sudo nginx -t
sudo nginx -T | grep proxy_pass

# Restart everything in correct order
sudo systemctl restart ride-dispatch
sudo systemctl restart driver-matching
sudo systemctl restart ride-booking
sudo systemctl reload nginx

# Verify full chain
curl -s http://localhost/health
curl -s -X POST http://localhost/ride/request
```
