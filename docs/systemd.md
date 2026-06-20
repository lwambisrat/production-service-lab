# Systemd Service Management Guide

## What is Systemd?

Systemd is Linux's service manager. It starts, stops, and monitors processes. In this project, all three services and Nginx are managed by systemd.

This means:

- Services start automatically on boot
- Services restart automatically if they crash
- Service A will not start before Service B and Service C are ready
- Logs are collected and accessible through `journalctl`

---

## Service Files

Each service has a unit file installed at `/etc/systemd/system/`:

| File | Service |
| ---- | ------- |
| `service-a.service` | Ride Booking API (port 3001) |
| `service-b.service` | Driver Matching Service (port 3002) |
| `service-c.service` | Ride Dispatch Service (port 3003) |

View a service file:

```bash
sudo systemctl cat service-a
```

---

## Dependency Management

Service A depends on both Service B and Service C.

The service file enforces this:

```ini
After=network.target service-b.service service-c.service
Requires=service-b.service service-c.service
```

- `After` — Service A will not start until B and C have started
- `Requires` — if B or C fail, Service A will also stop

This means services must always be started in dependency order:

```bash
# Correct order
sudo systemctl start service-c
sudo systemctl start service-b
sudo systemctl start service-a
```

---

## What Happens if a Dependency Goes Down

If Service B is stopped while the system is running:

1. Service A keeps running but cannot complete requests
2. Requests to Service A return a 500 error
3. Service A logs show a connection failure to `service-b.internal`

If Service B is down at boot time:

- Systemd will refuse to start Service A because `Requires=service-b.service` is not satisfied

---

## Common Systemd Commands

### Check service status

```bash
sudo systemctl status service-a
sudo systemctl status service-b
sudo systemctl status service-c
sudo systemctl status nginx
```

### Start services

```bash
sudo systemctl start service-c
sudo systemctl start service-b
sudo systemctl start service-a
```

### Stop services

```bash
sudo systemctl stop service-a service-b service-c
```

### Restart services

Always restart in dependency order:

```bash
sudo systemctl restart service-c
sudo systemctl restart service-b
sudo systemctl restart service-a
```

### Enable services to start on boot

```bash
sudo systemctl enable service-a service-b service-c nginx
```

### Disable services from starting on boot

```bash
sudo systemctl disable service-a
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
sudo journalctl -u service-a -n 50
sudo journalctl -u service-b -n 50
sudo journalctl -u service-c -n 50
```

### Follow logs live across all services

```bash
sudo journalctl -f -u service-a -u service-b -u service-c
```

### View full log with no truncation

```bash
sudo journalctl -u service-a -n 50 -l
```

### View logs since last boot

```bash
sudo journalctl -u service-a -b
```

### View system-level errors

```bash
sudo journalctl -xe
```

---

## Troubleshooting Service Startup Failures

### Step 1 — Check the service status

```bash
sudo systemctl status service-a
```

Look for `Active: failed` or `Active: inactive`.

### Step 2 — Read the logs

```bash
sudo journalctl -u service-a -n 50 -l
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

If Service A fails, check B and C before investigating A:

```bash
sudo systemctl status service-b
sudo systemctl status service-c
```

### Step 4 — Fix and restart in order

```bash
sudo systemctl restart service-c
sudo systemctl restart service-b
sudo systemctl restart service-a
```

### Step 5 — Verify

```bash
sudo systemctl status service-a service-b service-c nginx
curl -s http://localhost/health
curl -s http://localhost/greet-service-b
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
sudo systemctl status service-a service-b service-c nginx
curl -s http://localhost/health
```

All services should be running without any manual intervention.
