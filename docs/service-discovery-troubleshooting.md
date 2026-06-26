# Service Discovery Troubleshooting Guide

## What is Service Discovery?

In this system, services do not communicate using IP addresses. Instead they use names:

- `http://driver-matching.internal:3002`
- `http://ride-dispatch.internal:3003`
- `http://ride-booking.internal:3001`

These names are resolved using `/etc/hosts`. When ride-booking calls `driver-matching.internal`, Linux looks up that name in `/etc/hosts`, finds `127.0.0.1`, and connects to driver-matching on port 3002.

If that lookup fails, the services cannot communicate and the entire request chain breaks.

---

## How Name Resolution Works

Linux resolves hostnames using a resolver order defined in `/etc/nsswitch.conf`.

The line that matters is:

```
hosts: files dns
```

- `files` means check `/etc/hosts` first
- `dns` means fall back to a DNS server if not found in the file

Because our service names are defined in `/etc/hosts`, they resolve locally without needing any DNS server.

---

## Symptoms of a Service Discovery Failure

- `curl -X POST http://localhost/ride/request` returns a 502 error
- ride-booking logs a `driver_matching_unreachable` event for `driver-matching.internal`
- `getent hosts driver-matching.internal` returns nothing
- `ping driver-matching.internal` says "Name or service not known"

---

## Step-by-Step Troubleshooting

### Step 1 — Check if the entries exist in /etc/hosts

```bash
cat /etc/hosts | grep internal
```

Expected output:

```
127.0.0.1   ride-booking.internal
127.0.0.1   driver-matching.internal
127.0.0.1   ride-dispatch.internal
```

If any line is missing, that service name cannot be resolved.

---

### Step 2 — Test name resolution directly

```bash
getent hosts ride-booking.internal
getent hosts driver-matching.internal
getent hosts ride-dispatch.internal
```

Each should return:

```
127.0.0.1       ride-booking.internal
127.0.0.1       driver-matching.internal
127.0.0.1       ride-dispatch.internal
```

If a line returns nothing, the name is not resolving even if the entry appears to exist. Check for typos in `/etc/hosts`.

---

### Step 3 — Test connectivity using the service name

```bash
curl -s http://driver-matching.internal:3002/health
curl -s http://ride-dispatch.internal:3003/health
```

If this succeeds, name resolution is working and the services are reachable by name.

If this fails but `getent` returns the correct IP, the service itself may be down — check with `sudo systemctl status driver-matching`.

---

### Step 4 — Check the resolver order

```bash
cat /etc/nsswitch.conf | grep hosts
```

Expected:

```
hosts: files dns
```

If it shows `dns files` instead, Linux queries DNS before checking `/etc/hosts`. Since `.internal` names are not in any DNS server, they will fail to resolve.

Fix:

```bash
sudo nano /etc/nsswitch.conf
```

Change `dns files` to `files dns` and save.

---

### Step 5 — Re-add missing entries

If any entries are missing from `/etc/hosts`, add them:

```bash
echo '127.0.0.1   ride-booking.internal' | sudo tee -a /etc/hosts
echo '127.0.0.1   driver-matching.internal' | sudo tee -a /etc/hosts
echo '127.0.0.1   ride-dispatch.internal' | sudo tee -a /etc/hosts
```

Verify they were added:

```bash
cat /etc/hosts | grep internal
```

---

### Step 6 — Restart affected services

After fixing `/etc/hosts`, restart the services so they pick up the change:

```bash
sudo systemctl restart ride-dispatch
sudo systemctl restart driver-matching
sudo systemctl restart ride-booking
```

Always restart in dependency order — ride-dispatch first, then driver-matching, then ride-booking.

---

### Step 7 — Test the full chain again

```bash
curl -s -X POST http://localhost/ride/request
```

Expected response:

```json
{
  "request_id": "<uuid>",
  "status": "accepted",
  "message": "Ride request accepted. Driver matched and dispatched.",
  "ride_id": "RIDE-A1B2C3",
  "matched_driver": { "driver_name": "Brian", "eta_minutes": 3 }
}
```

---

## Quick Reference — All Diagnostic Commands

```bash
# Check /etc/hosts entries
cat /etc/hosts | grep internal

# Test name resolution
getent hosts ride-booking.internal
getent hosts driver-matching.internal
getent hosts ride-dispatch.internal

# Test connectivity by name
curl -s http://driver-matching.internal:3002/health
curl -s http://ride-dispatch.internal:3003/health

# Check resolver order
cat /etc/nsswitch.conf | grep hosts

# Check service logs for connection errors
sudo journalctl -u ride-booking -n 30
```

---

## Most Common Cause

The `/etc/hosts` entries were never added or were removed. This is always the first thing to check. It is fixed in under 30 seconds by re-adding the three lines.
