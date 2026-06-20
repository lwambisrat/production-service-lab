# Failure Scenarios and Investigation Guide

This guide covers how to simulate, investigate, and recover from common failures in the production service lab.

---

## Scenario 1 — Stop Service B

### Why this matters

Service B is a dependency of Service A. Stopping it simulates a real-world situation where an internal service goes down while the system is running.

### How to stop Service B

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
curl -s http://localhost/greet-driver-matching
```

Expected response:

```json
{
  "request_id": "<uuid>",
  "status": "error",
  "message": "Failed to reach driver-matching"
}
```

### Watch the logs during the failure

Open a second terminal and follow the logs before sending the request:

```bash
sudo journalctl -f -u ride-booking -u driver-matching -u ride-dispatch
```

You will see Service A log a `request_failed` event. Service B produces no logs because it never received the request.

### Recover from the failure

Restart in dependency order — B before A:

```bash
sudo systemctl restart driver-matching
sudo systemctl restart ride-booking
```

Verify recovery:

```bash
sudo systemctl status driver-matching ride-booking
curl -s http://localhost/greet-driver-matching
```

---

## Scenario 2 — Investigate a 502 Error

### What a 502 means

A 502 Bad Gateway means Nginx is running and received the request, but the service it is trying to reach (Service A) is down or not responding.

```
Client → Nginx ✓ → Service A ✗ → 502
```

### Step-by-step investigation

**Step 1 — Confirm Nginx is running**

```bash
sudo systemctl status nginx
```

If Nginx is down, that produces a different error (connection refused), not a 502.

**Step 2 — Check if Service A is responding**

```bash
curl -s http://localhost:3001/health
```

If this fails, Service A is down. That is the cause of the 502.

**Step 3 — Check Service A's status**

```bash
sudo systemctl status ride-booking
```

**Step 4 — Read Service A's logs**

```bash
sudo journalctl -u ride-booking -n 50 -l
```

Look for crash errors, Python tracebacks, or connection failures.

**Step 5 — Check if Service A's dependencies are up**

Service A requires Service B and Service C. If either is down, Service A may have failed to start.

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

Services call each other using names like `http://service-b.internal:3002`. If the name cannot be resolved to an IP address, the connection fails and the request chain breaks.

Symptoms:

- `curl http://localhost/greet-driver-matching` returns a 500 error
- Service A logs show a connection error to `service-b.internal`
- `getent hosts service-b.internal` returns nothing

### Step-by-step investigation

**Step 1 — Check the /etc/hosts entries**

```bash
cat /etc/hosts | grep service
```

Expected:

```
127.0.0.1   service-a.internal
127.0.0.1   service-b.internal
127.0.0.1   service-c.internal
```

If any line is missing, that service name will not resolve.

**Step 2 — Test name resolution directly**

```bash
getent hosts service-a.internal
getent hosts service-b.internal
getent hosts service-c.internal
```

Each should return `127.0.0.1`. If a line returns nothing, the name is not resolving.

**Step 3 — Test connectivity by name**

```bash
curl -s http://service-b.internal:3002/health
curl -s http://service-c.internal:3003/health
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
echo '127.0.0.1   service-a.internal' | sudo tee -a /etc/hosts
echo '127.0.0.1   service-b.internal' | sudo tee -a /etc/hosts
echo '127.0.0.1   service-c.internal' | sudo tee -a /etc/hosts
```

**Step 6 — Restart services after fixing hosts**

```bash
sudo systemctl restart ride-dispatch
sudo systemctl restart driver-matching
sudo systemctl restart ride-booking
```

**Step 7 — Verify the full chain**

```bash
curl -s http://localhost/greet-driver-matching
```

---

## Scenario 4 — Investigate a Failed Service A Startup

### What happens

Service A will fail to start if:

- Service B or Service C is not running (systemd dependency enforcement)
- The virtual environment path is wrong
- The working directory does not exist
- A Python error prevents the process from starting

### Step-by-step investigation

**Step 1 — Check Service A's status**

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
| `Dependency failed` | Service B or C is not running |
| `No such file or directory` | Wrong path in WorkingDirectory or ExecStart |
| `Failed to execute` | venv not created or uvicorn not installed |
| `Address already in use` | Port 3001 is occupied by another process |
| Python traceback | Syntax error or missing package in app.py |

**Step 3 — Check the dependencies first**

```bash
sudo systemctl status driver-matching
sudo systemctl status ride-dispatch
```

Service A will not start if either of these is down. Fix the dependency before trying to start A.

**Step 4 — Check the service file paths**

```bash
sudo systemctl cat ride-booking
```

Verify that:

- `User=` matches your actual Linux username
- `WorkingDirectory=` points to the correct `services/ride-booking` folder
- `ExecStart=` points to the correct `venv/bin/uvicorn`

**Step 5 — Check the port is free**

```bash
sudo ss -tulpn | grep 3001
```

If something else is using port 3001:

```bash
sudo pkill -f uvicorn
```

**Step 6 — Check the venv exists**

```bash
ls /path/to/production-service-lab/venv/bin/uvicorn
```

If the file does not exist, recreate the venv:

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
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
curl -s http://localhost/greet-driver-matching
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
cat /etc/hosts | grep service
getent hosts service-b.internal
getent hosts service-c.internal

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
curl -s http://localhost/greet-driver-matching
```
