# Production Service Lab – Ride Booking System

## Project Overview

This project simulates a production-style ride booking platform running inside an Ubuntu VM.

The system consists of three internal microservices and one public reverse proxy.

The purpose of this project is to demonstrate:

* Linux service lifecycle management
* Internal service communication
* Service discovery
* Reverse proxying
* Structured logging
* Request tracing
* Network security
* Troubleshooting and operational thinking

This system behaves like a small production environment where users can initiate ride requests, drivers are matched, and ride dispatch is completed.

---

## Scenario

The platform simulates a ride booking workflow.

A customer requests a ride.

The system:

1. Receives the request
2. Matches the nearest available driver
3. Dispatches the ride
4. Sends a callback to confirm the ride

The system uses mock location data to simulate real-world ride matching.

No external APIs are required.

---

## Architecture

| Component | Port | Role                    |
| --------- | ---: | ----------------------- |
| Service A | 3001 | Ride Booking API        |
| Service B | 3002 | Driver Matching Service |
| Service C | 3003 | Ride Dispatch Service   |
| Nginx     |   80 | Public Entry Point      |

### Request Flow

```
Client
  ↓
Nginx (port 80)
  ↓
Service A (port 3001)
  ↓
Service B (port 3002)
  ↓
Service C (port 3003)
  ↓
Service A (callback)
```

### Responsibilities

#### Service A — Ride Booking API

The only publicly accessible service. All external traffic enters here through Nginx.

Endpoints:

* `GET /health` — health check
* `GET /greet-service-b` — initiates the ride booking flow, forwards to Service B
* `POST /greeting-rcvd` — receives the callback from Service C when dispatch is complete

#### Service B — Driver Matching Service

Internal only. Receives requests from Service A, matches the nearest available driver, and forwards to Service C.

Endpoints:

* `GET /health` — health check
* `GET /greet` — receives ride request, matches driver, forwards to Service C

#### Service C — Ride Dispatch Service

Internal only. Receives the matched driver from Service B, finalizes dispatch, and sends a callback to Service A.

Endpoints:

* `GET /health` — health check
* `GET /greet-c` — receives dispatch payload, calls back to Service A

---

## Service Discovery

Services communicate using names instead of IP addresses.

Examples:

* `http://service-b.internal:3002`
* `http://service-c.internal:3003`

This is implemented using `/etc/hosts` entries that map each service name to `127.0.0.1`.

```
127.0.0.1   service-a.internal
127.0.0.1   service-b.internal
127.0.0.1   service-c.internal
```

### How name resolution works

Linux resolves hostnames by checking `/etc/nsswitch.conf`, which specifies `hosts: files dns`. This means `/etc/hosts` is checked before any DNS query. Since all service names are defined there, they resolve without a DNS server.

### What performs the resolution

The Linux C library resolver (`libc`) reads `/etc/hosts` and returns `127.0.0.1` for any of the service names.

### Troubleshooting service discovery

```bash
# Check entries exist
cat /etc/hosts | grep service

# Test resolution for each name
getent hosts service-a.internal
getent hosts service-b.internal
getent hosts service-c.internal

# Test connectivity
ping -c 1 service-b.internal
```

If resolution fails:

* Verify the entries exist in `/etc/hosts`
* Check for typos in the hostname
* Re-add missing entries manually

---

## Reverse Proxy

Nginx listens on port 80 and forwards all traffic to Service A at `127.0.0.1:3001`.

Service B and Service C are never referenced in the Nginx configuration and are not reachable through it.

### Why Nginx

* Provides a single public entry point
* Hides internal services from the outside
* Passes the original client IP and request ID to Service A
* Makes it easy to add routing, rate limiting, or TLS in future

### Troubleshooting Nginx

```bash
# Test configuration syntax
sudo nginx -t

# Check status
sudo systemctl status nginx

# View recent logs
sudo journalctl -u nginx -n 50

# View full configuration
sudo nginx -T
```

---

## Network Security

Service B and Service C are protected in two ways:

**Layer 1 — Loopback binding**

All three services bind to `127.0.0.1` instead of `0.0.0.0`. This means the operating system only accepts connections from the local machine, not from the network.

**Layer 2 — UFW firewall**

UFW explicitly blocks external access to ports 3001, 3002, and 3003. Even if a service were misconfigured to bind to `0.0.0.0`, the firewall would still block external connections.

Only ports 22 (SSH) and 80 (HTTP) are allowed from outside.

### Verify protection

```bash
# Check firewall rules
sudo ufw status verbose

# Check which address each service is bound to
sudo ss -tulpn | grep -E '3001|3002|3003'
```

Expected: all three services show `127.0.0.1` not `0.0.0.0`.

### Troubleshooting connectivity

```bash
# From outside the VM, these should fail (connection refused or timeout):
curl http://<VM_PUBLIC_IP>:3002/health
curl http://<VM_PUBLIC_IP>:3003/health

# From outside the VM, this should succeed:
curl http://<VM_PUBLIC_IP>/health
```

---

## Installation

### 1. Clone the repository

```bash
git clone <repo-url>
cd production-service-lab
```

### 2. Install system dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv nginx curl ufw
```

### 3. Configure service discovery

```bash
echo '127.0.0.1   service-a.internal' | sudo tee -a /etc/hosts
echo '127.0.0.1   service-b.internal' | sudo tee -a /etc/hosts
echo '127.0.0.1   service-c.internal' | sudo tee -a /etc/hosts
```

### 4. Create Python virtual environment

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

### 5. Install systemd service files

The service files use your username and project path. Set these variables first:

```bash
U=<your-username>
P=<absolute-path-to-project>
```

Then write the service files:

```bash
sudo tee /etc/systemd/system/service-c.service << EOF
[Unit]
Description=Production Lab Service C
After=network.target

[Service]
User=$U
WorkingDirectory=$P/services/service-c
ExecStart=$P/venv/bin/uvicorn app:app --host 127.0.0.1 --port 3003
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/service-b.service << EOF
[Unit]
Description=Production Lab Service B
After=network.target service-c.service
Requires=service-c.service

[Service]
User=$U
WorkingDirectory=$P/services/service-b
ExecStart=$P/venv/bin/uvicorn app:app --host 127.0.0.1 --port 3002
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/service-a.service << EOF
[Unit]
Description=Production Lab Service A
After=network.target service-b.service service-c.service
Requires=service-b.service service-c.service

[Service]
User=$U
WorkingDirectory=$P/services/service-a
ExecStart=$P/venv/bin/uvicorn app:app --host 127.0.0.1 --port 3001
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
```

### 6. Configure Nginx

```bash
sudo cp nginx/production-service-lab.conf /etc/nginx/sites-available/production-service-lab
sudo ln -sf /etc/nginx/sites-available/production-service-lab /etc/nginx/sites-enabled/production-service-lab
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

### 7. Configure firewall

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw deny 3001/tcp
sudo ufw deny 3002/tcp
sudo ufw deny 3003/tcp
sudo ufw enable
```

### 8. Enable and start services

```bash
sudo systemctl enable --now service-c
sudo systemctl enable --now service-b
sudo systemctl enable --now service-a
sudo systemctl enable nginx
```

---

## Operation

### Start all services

```bash
./scripts/start.sh
```

Or manually:

```bash
sudo systemctl start service-c service-b service-a nginx
```

### Stop all services

```bash
./scripts/stop.sh
```

Or manually:

```bash
sudo systemctl stop service-a service-b service-c
```

### Restart all services

```bash
./scripts/restart.sh
```

Or manually:

```bash
sudo systemctl restart service-c service-b service-a
```

### Check service status

```bash
sudo systemctl status service-a service-b service-c nginx
```

---

## Validation

### Health checks

```bash
# Through Nginx (public path)
curl -s http://localhost/health

# Direct to each service
curl -s http://localhost:3001/health
curl -s http://localhost:3002/health
curl -s http://localhost:3003/health
```

### Full chain test

```bash
curl -s http://localhost/greet-service-b
```

Expected response:

```json
{
  "request_id": "<uuid>",
  "status": "success",
  "message": "Request completed successfully"
}
```

### Run the health check script

```bash
./scripts/healthcheck.sh
```

---

## Logging

All services produce structured JSON logs.

Each log entry contains:

| Field        | Description                          |
| ------------ | ------------------------------------ |
| `timestamp`  | ISO 8601 UTC timestamp               |
| `service`    | Which service produced the log       |
| `event`      | What happened                        |
| `request_id` | Unique ID tying all logs for one request |
| `path`       | HTTP path that was called            |
| `status`     | HTTP status code or info/error       |

### View logs

```bash
# Last 50 lines from each service
sudo journalctl -u service-a -n 50
sudo journalctl -u service-b -n 50
sudo journalctl -u service-c -n 50

# Follow live across all three services
sudo journalctl -f -u service-a -u service-b -u service-c
```

### Trace a specific request

Every request gets a `request_id`. To follow one request across all services:

```bash
sudo journalctl -u service-a -u service-b -u service-c | grep <request_id>
```

---

## Request Tracing

Each request is assigned a `request_id` (UUID) when it enters Service A.

This ID is:

* Generated by Service A if not provided by the client
* Passed to Service B via the `X-Request-ID` header
* Passed to Service C via the `X-Request-ID` header
* Included in the callback from Service C back to Service A
* Logged by every service at every step

This means a single request can be traced across all four hops:

```
service-a: ride_request_received     request_id=abc123
service-b: driver_matched            request_id=abc123
service-c: ride_dispatch_started     request_id=abc123
service-a: callback_received         request_id=abc123
```

---

## Troubleshooting

### Service startup failure

```bash
sudo systemctl status service-a
sudo journalctl -u service-a -n 50 -l
```

Common causes:

* Wrong path in `WorkingDirectory` or `ExecStart`
* venv not created or packages not installed
* Port already in use

### Service dependency failure

Service A requires B and C. If B or C is down, A will not start.

```bash
# Check which service failed
sudo systemctl status service-b
sudo systemctl status service-c

# Restart in dependency order
sudo systemctl restart service-c
sudo systemctl restart service-b
sudo systemctl restart service-a
```

### Reverse proxy failure

```bash
# Test Nginx config
sudo nginx -t

# Check status
sudo systemctl status nginx

# Check if Service A is up (502 means A is down)
curl -s http://localhost:3001/health
```

### Service discovery failure

```bash
# Check entries exist
cat /etc/hosts | grep service

# Test resolution
getent hosts service-b.internal
getent hosts service-c.internal

# Re-add if missing
echo '127.0.0.1   service-b.internal' | sudo tee -a /etc/hosts
echo '127.0.0.1   service-c.internal' | sudo tee -a /etc/hosts
```

### Name resolution failure

```bash
# Check resolver config
cat /etc/nsswitch.conf | grep hosts
```

Should show `files` before `dns`. If not:

```bash
sudo nano /etc/nsswitch.conf
# Change: hosts: dns files
# To:     hosts: files dns
```

### Network access failure

```bash
# Check firewall rules
sudo ufw status verbose

# Check port binding
sudo ss -tulpn | grep -E '3001|3002|3003|80'

# Re-apply rules if needed
sudo ufw allow 80/tcp
sudo ufw deny 3002/tcp
sudo ufw deny 3003/tcp
sudo ufw reload
```

### Missing logs

```bash
# Check if service is running
sudo systemctl status service-a

# Check journal for errors
sudo journalctl -xe -u service-a

# Check PYTHONUNBUFFERED is set in service file
sudo systemctl cat service-a | grep PYTHONUNBUFFERED
```

### Invalid routing behavior

```bash
# Check Nginx is routing to correct port
sudo nginx -T | grep proxy_pass

# Check which service is on which port
sudo ss -tulpn | grep -E '3001|3002|3003'
```

### Inter-service communication failure

```bash
# Test each hop manually
curl -s http://service-b.internal:3002/health
curl -s http://service-c.internal:3003/health

# Check /etc/hosts
getent hosts service-b.internal
getent hosts service-c.internal
```

---

## Reboot Recovery

All services are enabled with systemd and start automatically on boot.

Test:

```bash
sudo reboot
```

After reboot:

```bash
sudo systemctl status service-a service-b service-c nginx
curl -s http://localhost/health
curl -s http://localhost/greet-service-b
```

All services should be running without manual intervention.

---

## Final Notes

This project demonstrates how a small production system should be deployed, operated, secured, monitored, and recovered.

The focus is not only functionality but operational reliability — the ability to diagnose, recover from, and explain failures in a live environment.
