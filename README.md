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

The system has:

| Component | Port | Role                    |
| --------- | ---: | ----------------------- |
| Service A | 3001 | Ride Booking API        |
| Service B | 3002 | Driver Matching Service |
| Service C | 3003 | Ride Dispatch Service   |
| Nginx     |   80 | Public Entry Point      |

### Request Flow

Client
↓
Nginx
↓
Service A
↓
Service B
↓
Service C
↓
Service A Callback

### Responsibilities

#### Service A

Service A is the public-facing service.

Responsibilities:

* Accept user requests
* Start ride booking flow
* Generate request IDs
* Forward requests to Service B
* Receive callback from Service C

Endpoints:

* GET `/health`
* GET `/greet-service-b`
* POST `/greeting-rcvd`

---

#### Service B

Service B is internal.

Responsibilities:

* Receive request from Service A
* Match nearest available driver
* Forward matched driver to Service C

Endpoints:

* GET `/health`
* GET `/greet`

---

#### Service C

Service C is internal.

Responsibilities:

* Receive dispatch request
* Finalize ride dispatch
* Notify Service A when complete

Endpoints:

* GET `/health`
* GET `/greet-c`

---

## Service Discovery

Services communicate using names instead of IPs.

Example:

* `http://service-b.internal:3002`
* `http://service-c.internal:3003`

This is configured in:

`/etc/hosts`

Example:

127.0.0.1 service-a.internal
127.0.0.1 service-b.internal
127.0.0.1 service-c.internal

### Why this matters

Using names instead of IPs makes systems easier to manage if infrastructure changes.

### Troubleshooting service discovery

Check:

```bash
cat /etc/hosts
getent hosts service-b.internal
getent hosts service-c.internal
```

If name resolution fails:

* verify `/etc/hosts`
* verify spelling
* verify network access

---

## Reverse Proxy

Nginx is the public entry point.

Public route:

`http://localhost/service-a/`

Nginx forwards traffic to:

`127.0.0.1:3001`

Internal services are not exposed.

### Why Nginx?

Nginx:

* hides internal services
* manages routing
* controls access
* centralizes traffic

### Troubleshooting Nginx

Check:

```bash
sudo nginx -t
sudo systemctl status nginx
sudo journalctl -u nginx -n 50
```

---

## Network Security

Only Service A is public.

Service B and Service C listen only on:

`127.0.0.1`

This prevents external access.

Protection mechanism:

Loopback binding.

Verification:

```bash
sudo ss -tulpn
```

Expected:

3002 and 3003 bound to localhost only.

---

## Installation

Clone repository:

```bash
git clone <repo-url>
cd production-service-lab
```

Create environment:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Copy systemd services:

```bash
sudo cp systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
```

Enable services:

```bash
sudo systemctl enable service-a service-b service-c
```

Start services:

```bash
sudo systemctl start service-c service-b service-a
```

Setup Nginx:

```bash
sudo cp nginx/production-service-lab.conf /etc/nginx/sites-available/
sudo ln -s /etc/nginx/sites-available/production-service-lab /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

---

## Operation

Start:

```bash
./scripts/start.sh
```

Stop:

```bash
./scripts/stop.sh
```

Restart:

```bash
./scripts/restart.sh
```

Health check:

```bash
./scripts/healthcheck.sh
```

---

## Validation

Check health:

```bash
curl http://localhost/service-a/health
curl http://service-b.internal:3002/health
curl http://service-c.internal:3003/health
```

Run full flow:

```bash
curl http://localhost/service-a/greet-service-b
```

Expected:

Request should pass across all services successfully.

---

## Logging

Logs are structured JSON.

Logs contain:

* timestamp
* service
* event
* request_id
* path
* status

View logs:

```bash
journalctl -u service-a -n 50
journalctl -u service-b -n 50
journalctl -u service-c -n 50
```

This allows tracing a request across all services.

---

## Request Tracing

Each request uses:

`X-Request-ID`

If missing:

Service A generates one.

This request ID is passed through:

* Service A
* Service B
* Service C
* Service A callback

This makes debugging easy.

---

## Common Failures and Troubleshooting

### 1. Service startup failure

Symptoms:

* service not running

Check:

```bash
systemctl status service-a
journalctl -u service-a -n 50
```

Possible causes:

* syntax errors
* missing dependencies
* wrong paths

---

### 2. Port already in use

Symptoms:

Address already in use

Check:

```bash
sudo ss -tulpn
```

Fix:

Kill process:

```bash
sudo pkill -f uvicorn
```

---

### 3. Nginx 404

Cause:

wrong route mapping

Check:

```bash
sudo nginx -T
```

---

### 4. Nginx 502 Bad Gateway

Cause:

Service A is down

Check:

```bash
curl http://127.0.0.1:3001/health
```

---

### 5. Service discovery failure

Cause:

missing `/etc/hosts`

Check:

```bash
getent hosts service-b.internal
```

---

### 6. Internal communication failure

Cause:

dependency service stopped

Check:

```bash
systemctl status service-b
systemctl status service-c
```

---

### 7. Missing logs

Cause:

service crashed before logging

Check:

```bash
journalctl -xe
```

---

### 8. Invalid routes

Cause:

wrong endpoint called

Expected behavior:

404 + structured logs

---

## Reboot Recovery

Services are managed by systemd.

They automatically:

* start on boot
* restart after failure

Test:

```bash
sudo reboot
```

After reboot:

```bash
systemctl status service-a service-b service-c nginx
```

---

## Final Notes

This project demonstrates how a small production system should be deployed, operated, secured, monitored, and recovered.

The focus is not only functionality, but operational reliability.
