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

1. Receives the request via Nginx
2. Forwards to the Ride Booking API (Service A)
3. Matches the nearest available driver (Service B)
4. Dispatches the ride (Service C)
5. Sends a callback to confirm the ride back to Service A

The system uses mock location data to simulate real-world ride matching.

No external APIs are required.

---

## Architecture

| Component              | Port | Role                    |
| ---------------------- | ---: | ----------------------- |
| Nginx                  |   80 | Public Entry Point      |
| Ride Booking API       | 3001 | Service A — public via Nginx only |
| Driver Matching Service| 3002 | Service B — internal only |
| Ride Dispatch Service  | 3003 | Service C — internal only |

### Request Flow

```
Client
  ↓
Nginx (port 80)
  ↓
Service A — Ride Booking API (port 3001)
  ↓
Service B — Driver Matching Service (port 3002)
  ↓
Service C — Ride Dispatch Service (port 3003)
  ↓
Service A — callback received
```

### Responsibilities

#### Nginx — Public Entry Point

The only externally reachable component. Forwards all traffic to Service A by discovery name.

Endpoints:

* `GET /nginx-health` — Nginx-only health check (does not touch any service)
* `/*` — everything else is proxied to Service A

#### Service A — Ride Booking API (port 3001)

The only publicly accessible service. All external traffic enters here through Nginx.

Endpoints:

* `GET /health` — health check
* `POST /ride/request` — initiates the full ride booking flow (A → B → C → A)
* `POST /ride/callback` — receives the dispatch confirmation from Service C

#### Service B — Driver Matching Service (port 3002)

Internal only. Receives requests from Service A, matches the nearest available driver, and forwards to Service C.

Endpoints:

* `GET /health` — health check
* `POST /driver/match` — matches a driver and calls Service C

#### Service C — Ride Dispatch Service (port 3003)

Internal only. Receives the matched driver from Service B, finalizes dispatch, and sends a callback to Service A.

Endpoints:

* `GET /health` — health check
* `POST /ride/dispatch` — dispatches the ride and calls back to Service A

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

### Troubleshooting service discovery

```bash
# Check entries exist
grep service /etc/hosts

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

Nginx listens on port 80 and forwards all traffic to Service A at `service-a.internal:3001`.

Service B and Service C are never referenced in the Nginx configuration and are not reachable through it.

### Nginx-specific health check

```bash
sudo cp nginx/production-service-lab.conf /etc/nginx/sites-available/production-service-lab
sudo nginx -t && sudo systemctl reload nginx
curl http://localhost/nginx-health
# ok
```

This is answered by Nginx itself — Service A is not involved.

### Why Nginx

* Provides a single public entry point
* Hides internal services from the outside
* Propagates the `X-Request-ID` trace header through the entire chain
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

### Verify external access

```bash
# From outside the VM, these should fail (connection refused or timeout):
curl http://<VM_PUBLIC_IP>:3001/health
curl http://<VM_PUBLIC_IP>:3002/health
curl http://<VM_PUBLIC_IP>:3003/health

# From outside the VM, this should succeed:
curl http://<VM_PUBLIC_IP>/health
```

---

## Installation

Run the install script — it handles everything automatically:

```bash
git clone <repo-url>
cd production-service-lab
bash scripts/install.sh
```

The script:

1. Installs system packages (python3, nginx, ufw, curl)
2. Adds `/etc/hosts` entries for service discovery
3. Creates the Python virtual environment and installs dependencies
4. Installs systemd service files with your username and path substituted
5. Configures Nginx
6. Configures the UFW firewall
7. Enables and starts all services
8. Runs `verify.sh` to confirm everything is working

---

## Operation

### Start all services

```bash
sudo systemctl start ride-dispatch driver-matching ride-booking nginx
```

### Stop all services

```bash
sudo systemctl stop ride-booking driver-matching ride-dispatch
```

### Restart all services

```bash
sudo systemctl restart ride-dispatch driver-matching ride-booking
```

### Check service status

```bash
sudo systemctl status ride-booking driver-matching ride-dispatch nginx
```

---

## Validation

### Nginx health check

```bash
# Answered by Nginx directly — no service involved
sudo cp nginx/production-service-lab.conf /etc/nginx/sites-available/production-service-lab
sudo nginx -t && sudo systemctl reload nginx
curl http://localhost/nginx-health
```

### Service health checks

```bash
# Through Nginx (public path — hits Service A)
curl http://localhost/health
```

Expected response:

```json
{"service": "ride-booking-api", "status": "healthy", "port": 3001}
```

```bash
# Direct to each service (from inside the VM only)
curl http://localhost:3001/health
curl http://localhost:3002/health
curl http://localhost:3003/health
```

Expected responses:

```json
{"service": "ride-booking-api",        "status": "healthy", "port": 3001}
{"service": "driver-matching-service", "status": "healthy", "port": 3002}
{"service": "ride-dispatch-service",   "status": "healthy", "port": 3003}
```

### Full chain test

This triggers the entire A → B → C → A flow in one request:

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
  "customer": "Lwam",
  "pickup":  { "area": "Westlands", "lat": -1.2676, "lng": 36.8108 },
  "dropoff": { "area": "CBD",       "lat": -1.2864, "lng": 36.8172 },
  "matched_driver": {
    "driver_id":       "DRV-101",
    "driver_name":     "Brian",
    "area":            "Westlands",
    "driver_location": { "lat": -1.265, "lng": 36.812 },
    "eta_minutes":     3,
    "match_reason":    "Closest available driver to pickup location"
  }
}
```

### Test with a custom trace ID

```bash
curl -s -X POST http://localhost/ride/request \
  -H "X-Request-ID: my-trace-123"
```

The same `my-trace-123` will appear in the logs of all three services.

### Test each service endpoint directly

**Service A — trigger ride booking:**

```bash
curl -s -X POST http://localhost:3001/ride/request
```

**Service B — trigger driver matching:**

```bash
curl -s -X POST http://localhost:3002/driver/match \
  -H "Content-Type: application/json" \
  -d '{"request_id": "test-123", "pickup": {"lat": -1.28, "lng": 36.82}}'
```

**Service C — trigger ride dispatch:**

```bash
curl -s -X POST http://localhost:3003/ride/dispatch \
  -H "Content-Type: application/json" \
  -d '{"request_id": "test-123", "driver": "Brian", "pickup": {"lat": -1.28, "lng": 36.82}}'
```

**Service A — test callback endpoint:**

```bash
curl -s -X POST http://localhost:3001/ride/callback \
  -H "Content-Type: application/json" \
  -d '{"request_id": "test-123", "driver": "Brian", "status": "dispatched"}'
```

### Run the full verification script

```bash
bash scripts/verify.sh
```

---

## Logging

All services produce structured JSON logs.

Each log entry contains:

| Field        | Description                              |
| ------------ | ---------------------------------------- |
| `timestamp`  | ISO 8601 UTC timestamp                   |
| `level`      | INFO, WARNING, or ERROR                  |
| `service`    | Which service produced the log           |
| `event`      | What happened                            |
| `request_id` | Unique ID tying all logs for one request |
| `message`    | Human-readable description               |

### View logs

```bash
# Last 50 lines from each service
sudo journalctl -u ride-booking -n 50
sudo journalctl -u driver-matching -n 50
sudo journalctl -u ride-dispatch -n 50

# Follow live across all three services
sudo journalctl -f -u ride-booking -u driver-matching -u ride-dispatch
```

### Trace a specific request

Every request gets a `request_id`. To follow one request across all services:

```bash
sudo journalctl -u ride-booking -u driver-matching -u ride-dispatch | grep <request_id>
```

---

## Request Tracing

Each request is assigned a `request_id` (UUID) when it enters Service A.

This ID is:

* Generated by Service A if not provided by the client (or passed via `X-Request-ID` header)
* Passed to Service B via the `X-Request-ID` header
* Passed to Service C via the `X-Request-ID` header
* Included in the callback from Service C back to Service A
* Logged by every service at every step

This means a single request can be traced across all four hops:

```
ride-booking:    ride_request_received     request_id=abc123
driver-matching: driver_matched            request_id=abc123
ride-dispatch:   ride_dispatch_started     request_id=abc123
ride-booking:    callback_received         request_id=abc123
```

---

## Troubleshooting

### Service startup failure

```bash
sudo systemctl status ride-booking
sudo journalctl -u ride-booking -n 50 -l
```

Common causes:

* Wrong path in `WorkingDirectory` or `ExecStart`
* venv not created or packages not installed
* Port already in use

### Service dependency failure

Service A (ride-booking) requires B and C. If B or C is down, A will not start.

```bash
# Check which service failed
sudo systemctl status driver-matching
sudo systemctl status ride-dispatch

# Restart in dependency order
sudo systemctl restart ride-dispatch
sudo systemctl restart driver-matching
sudo systemctl restart ride-booking
```

### Reverse proxy failure

```bash
# Test Nginx config
sudo nginx -t

# Check status
sudo systemctl status nginx

# A 502 from Nginx means Service A is down
curl -s http://localhost:3001/health
```

### Service discovery failure

```bash
# Check entries exist
grep service /etc/hosts

# Test resolution
getent hosts service-b.internal
getent hosts service-c.internal

# Re-add if missing
echo '127.0.0.1   service-b.internal' | sudo tee -a /etc/hosts
echo '127.0.0.1   service-c.internal' | sudo tee -a /etc/hosts
```

### Network access failure

```bash
# Check firewall rules
sudo ufw status verbose

# Check port binding
sudo ss -tulpn | grep -E '3001|3002|3003|80'
```

### Missing logs

```bash
# Check if service is running
sudo systemctl status ride-booking

# Check journal for errors
sudo journalctl -xe -u ride-booking
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
sudo systemctl status ride-booking driver-matching ride-dispatch nginx
curl -s http://localhost/nginx-health
curl -s -X POST http://localhost/ride/request
```

All services should be running without manual intervention.

---

## Final Notes

This project demonstrates how a small production system should be deployed, operated, secured, monitored, and recovered.

The focus is not only functionality but operational reliability — the ability to diagnose, recover from, and explain failures in a live environment.
