# Systemd Service Management Guide

## What is Systemd?

Systemd is Linux's service manager. It starts, stops, and monitors processes. In this project, all three services and Nginx are managed by systemd.

This means:

- Services start automatically on boot
- Services restart automatically if they crash
- ride-booking will not start before driver-matching and ride-dispatch are ready
- Logs are collected and accessible through `journalctl`

---

## Service Files

Each service has a unit file installed at `/etc/systemd/system/`:

| File | Service |
| ---- | ------- |
| `ride-booking.service` | Ride Booking API (port 3001) |
| `driver-matching.service` | Driver Matching Service (port 3002) |
| `ride-dispatch.service` | Ride Dispatch Service (port 3003) |

View a service file:

```bash
sudo systemctl cat ride-booking
```

---

## Dependency Management

ride-booking depends on both driver-matching and ride-dispatch.

The service file enforces this:

```ini
After=network-online.target driver-matching.service ride-dispatch.service
Wants=network-online.target driver-matching.service ride-dispatch.service
ExecStartPre=/opt/ridelab/scripts/wait-for-deps.sh
```

- `After` — ride-booking is ordered to start after driver-matching and ride-dispatch
- `Wants` — driver-matching and ride-dispatch are pulled in as soft dependencies (weaker than `Requires`)
- `ExecStartPre` — the `wait-for-deps.sh` readiness gate blocks A's startup
  until driver-matching and ride-dispatch actually answer `/health`, since `After=` only guarantees the
  processes launched, not that they are ready

This means services must always be started in dependency order:

```bash
# Correct order
sudo systemctl start ride-dispatch
sudo systemctl start driver-matching
sudo systemctl start ride-booking
```

---

## What Happens if a Dependency Goes Down

If driver-matching is stopped while the system is running:

1. ride-booking keeps running but cannot complete requests
2. Requests to ride-booking return a 502 error
3. ride-booking logs a `driver_matching_unreachable` event for `driver-matching.internal`

If driver-matching is down at boot time:

- The `wait-for-deps.sh` readiness gate times out, so ride-booking fails to start until driver-matching is healthy

---

## Common Systemd Commands

### Check service status

```bash
sudo systemctl status ride-booking
sudo systemctl status driver-matching
sudo systemctl status ride-dispatch
sudo systemctl status nginx
```

### Start services

```bash
sudo systemctl start ride-dispatch
sudo systemctl start driver-matching
sudo systemctl start ride-booking
```

### Stop services

```bash
sudo systemctl stop ride-booking driver-matching ride-dispatch
```

### Restart services

Always restart in dependency order:

```bash
sudo systemctl restart ride-dispatch
sudo systemctl restart driver-matching
sudo systemctl restart ride-booking
```

### Enable services to start on boot

```bash
sudo systemctl enable ride-booking driver-matching ride-dispatch nginx
```

### Disable services from starting on boot

```bash
sudo systemctl disable ride-booking
```

### Reload systemd after editing a service file

```bash
sudo systemctl daemon-reload
```

---

## Viewing Logs

Systemd collects all service output through `journalctl`.

### View recent logs for a service

```bash
sudo journalctl -u ride-booking -n 50
sudo journalctl -u driver-matching -n 50
sudo journalctl -u ride-dispatch -n 50
```

### Follow logs live across all services

```bash
sudo journalctl -f -u ride-booking -u driver-matching -u ride-dispatch
```

### View full log with no truncation

```bash
sudo journalctl -u ride-booking -n 50 -l
```

### View logs since last boot

```bash
sudo journalctl -u ride-booking -b
```

### View system-level errors

```bash
sudo journalctl -xe
```

---

## Troubleshooting Service Startup Failures

### Step 1 — Check the service status

```bash
sudo systemctl status ride-booking
```

Look for `Active: failed` or `Active: inactive`.

### Step 2 — Read the logs

```bash
sudo journalctl -u ride-booking -n 50 -l
```

Common causes:

| Cause | What to look for in logs |
| ----- | ------------------------ |
| Wrong path | `No such file or directory` |
| venv missing | `Failed to execute` |
| Port in use | `Address already in use` |
| Dependency down | `Dependency failed` |
| Python error | Traceback in logs |

### Step 3 — Check dependencies first

If ride-booking fails, check driver-matching and ride-dispatch before investigating ride-booking:

```bash
sudo systemctl status driver-matching
sudo systemctl status ride-dispatch
```

### Step 4 — Fix and restart in order

```bash
sudo systemctl restart ride-dispatch
sudo systemctl restart driver-matching
sudo systemctl restart ride-booking
```

### Step 5 — Verify

```bash
sudo systemctl status ride-booking driver-matching ride-dispatch nginx
curl -s http://localhost/health
curl -s -X POST http://localhost/ride/request
```

---

## Reboot Recovery Test

Because all services are enabled, they start automatically after a reboot.

Test this:

```bash
sudo reboot
```

After the system comes back:

```bash
sudo systemctl status ride-booking driver-matching ride-dispatch nginx
curl -s http://localhost/health
```

All services should be running without any manual intervention.
