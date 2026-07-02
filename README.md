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

## Prerequisites

* An **Ubuntu VM**. This is a Linux/systemd project — it does **not** run on macOS or
  Windows directly. On a Mac, run it inside a Linux VM such as [Lima](https://lima-vm.io/):
  `limactl start`, then `limactl shell <vm-name>`.
* `sudo` access. `git`, `python3`, and `curl` (the installer adds anything missing).
* Work from a **native clone in the VM's home directory** (`~`), **not** a shared/mounted
  folder — see [Working in the VM](#working-in-the-vm-lima--shared-folder-gotcha).
* These services use ports **80, 3001, 3002, 3003** — make sure nothing else on the VM is
  using them (see [port conflicts](#wrong-service-answering--ports-already-in-use)).

## Quick Start

```bash
# inside the Ubuntu VM, from your home directory
git clone https://github.com/lwambisrat/production-service-lab.git
cd production-service-lab
bash scripts/install.sh     # installs deps, deploys to /opt/ridelab, starts all services

# confirm it's healthy and the full chain works
bash scripts/verify.sh
curl -s -X POST http://localhost/ride/request | python3 -m json.tool
```

`verify.sh` should end with `FAIL=0`, and the `curl` should return `"status": "accepted"`
with a `matched_driver`. If so, you're up. For the complete scenario-by-scenario
walkthrough, see **[docs/TESTING.md](docs/TESTING.md)**.

## Documentation

This README is the operational entry point. The files below contain the deeper
design notes, test procedures, and recorded evidence.

| Doc | What it covers |
|-----|----------------|
| [Architecture](docs/architecture.md) | Detailed component responsibilities, trust boundaries, and end-to-end request flow |
| [VM testing guide](docs/TESTING.md) | Ordered VM walkthrough: health, chain, failures, reboot, and security |
| [VM validation evidence](docs/VALIDATION_EVIDENCE.md) | Recorded VM results with commands, expected behavior, actual behavior, and verdicts |
| [Container validation evidence](docs/CONTAINER_VALIDATION.md) | Seven Docker Compose tests with expected results and screenshots |
| [systemd operations](docs/systemd.md) | VM service lifecycle, dependency ordering, readiness, and restart behavior |
| [Service discovery troubleshooting](docs/service-discovery-troubleshooting.md) | `/etc/hosts` and internal-name diagnosis for the VM runtime |
| [Driver-matching unavailable](docs/driver-matching-unavailable.md) | Controlled Service B failure and recovery behavior |
| [Failure scenarios](docs/failure-scenarios.md) | Failure injection and recovery procedures |
| [Troubleshooting](docs/troubleshooting.md) | General diagnosis for services, ports, Nginx, networking, and logs |

---

## Scenario

The platform simulates a ride booking workflow.

A customer requests a ride.

The system:

1. Receives the request via Nginx
2. Forwards to the Ride Booking API (ride-booking)
3. Matches the nearest available driver (driver-matching)
4. Dispatches the ride (ride-dispatch)
5. Sends a callback to confirm the ride back to ride-booking

The system uses mock location data to simulate real-world ride matching.

No external APIs are required.

---

## Architecture

The application behavior is the same in both runtimes; only lifecycle,
discovery, networking, and log collection change.

| Component | Application port | VM/systemd runtime | Docker Compose runtime |
|-----------|-----------------:|--------------------|------------------------|
| Nginx | 80 | Public entry on VM port 80 | Only published container: host `8080` → container `80` |
| `ride-booking` | 3001 | `127.0.0.1:3001`; reached through Nginx | Internal Compose service `ride-booking:3001` |
| `driver-matching` | 3002 | `127.0.0.1:3002`; internal only | Internal Compose service `driver-matching:3002` |
| `ride-dispatch` | 3003 | `127.0.0.1:3003`; internal only | Internal Compose service `ride-dispatch:3003` |

### Request Flow

```text
Client
  ↓
Nginx
  ↓
ride-booking (Service A)
  ↓
driver-matching (Service B)
  ↓
ride-dispatch (Service C)
  ↓
ride-booking callback
  ↓
Client response
```

One `X-Request-ID` and one `ride_id` are propagated through every hop so the
Nginx access log and all three application logs can be correlated.

### Runtime mapping

| Production concern | VM implementation | Compose implementation |
|--------------------|-------------------|------------------------|
| Lifecycle | systemd units | Compose services |
| Discovery | `/etc/hosts` names such as `driver-matching.internal` | Docker DNS names such as `driver-matching` |
| Isolation | loopback binding plus UFW | Internal Compose network plus no published application ports |
| Logs | `journalctl` and VM Nginx log files | Container stdout/stderr through `docker compose logs` |
| Readiness | `wait-for-deps.sh` in `ExecStartPre` | Container health checks plus `condition: service_healthy` |
| Restart | `Restart=on-failure` | `restart: unless-stopped` |

For the expanded design and trust boundaries, see
[docs/architecture.md](docs/architecture.md).

### Responsibilities

#### Nginx — Public Entry Point

The only externally reachable component. It terminates the public connection,
creates or preserves the trace ID, and forwards application traffic only to
`ride-booking`.

Endpoints:

- `GET /nginx-health` — Nginx-only health check; no application service is called
- `/*` — proxied to `ride-booking`

#### ride-booking — Ride Booking API (port 3001)

The first application service, but never directly published. It accepts traffic
only through Nginx, calls `driver-matching`, and receives the final callback.

Endpoints:

- `GET /health` — process health check
- `POST /ride/request` — starts the full request chain
- `POST /ride/callback` — receives dispatch confirmation

#### driver-matching — Driver Matching Service (port 3002)

Internal only. Receives requests from ride-booking, matches the nearest available driver, and forwards to ride-dispatch.

Endpoints:

- `GET /health` — process health check
- `POST /driver/match` — matches a driver and calls `ride-dispatch`

#### ride-dispatch — Ride Dispatch Service (port 3003)

Internal only. Receives the matched driver from driver-matching, finalizes dispatch, and sends a callback to ride-booking.

Endpoints:

- `GET /health` — process health check
- `POST /ride/dispatch` — dispatches the ride and calls back to `ride-booking`

---

## Service Discovery

Services communicate using names instead of IP addresses.

Examples:

* `http://driver-matching.internal:3002`
* `http://ride-dispatch.internal:3003`

This is implemented using `/etc/hosts` entries that map each service name to `127.0.0.1`.

```
127.0.0.1   ride-booking.internal
127.0.0.1   driver-matching.internal
127.0.0.1   ride-dispatch.internal
```

### How name resolution works

Linux resolves hostnames by checking `/etc/nsswitch.conf`, which specifies `hosts: files dns`. This means `/etc/hosts` is checked before any DNS query. Since all service names are defined there, they resolve without a DNS server.

### Troubleshooting service discovery

```bash
# Check entries exist
grep internal /etc/hosts

# Test resolution for each name
getent hosts ride-booking.internal
getent hosts driver-matching.internal
getent hosts ride-dispatch.internal

# Test connectivity
ping -c 1 driver-matching.internal
```

If resolution fails:

* Verify the entries exist in `/etc/hosts`
* Check for typos in the hostname
* Re-add missing entries manually

---

## Nginx Reverse Proxy

Nginx is the single public boundary in both runtimes. It exposes its own
`/nginx-health` endpoint and proxies every other path to `ride-booking`.
`driver-matching` and `ride-dispatch` are deliberately absent from the public
route configuration.

### Configuration by runtime

| Runtime | Configuration | Public address | Upstream | Log destination |
|---------|---------------|----------------|----------|-----------------|
| VM/systemd | [`nginx/production-service-lab.conf`](nginx/production-service-lab.conf) | VM port 80 | `ride-booking.internal:3001` through `/etc/hosts` | `/var/log/nginx/ride-booking_*.log` |
| Docker Compose | [`nginx/compose.conf`](nginx/compose.conf) | `localhost:8080` | `ride-booking:3001` through Docker DNS | `/dev/stdout` and `/dev/stderr` |

The Compose file mounts the container configuration read-only:

```yaml
volumes:
  - ./nginx/compose.conf:/etc/nginx/conf.d/default.conf:ro
```

Both configurations:

- Disable the Nginx version in response headers with `server_tokens off`.
- Reuse a client-supplied `X-Request-ID` or generate one at the front door.
- Add the trace ID, upstream address, status, and request time to access logs.
- Forward `Host`, client IP, and forwarding headers to `ride-booking`.
- Return `200 OK` from `/nginx-health` without calling an application service.

### Verify Nginx

VM/systemd:

```bash
sudo nginx -t
sudo systemctl status nginx
curl -i http://localhost/nginx-health
sudo tail -n 20 /var/log/nginx/ride-booking_access.log
```

Docker Compose:

```bash
docker compose exec nginx nginx -t
curl -i http://localhost:8080/nginx-health
docker compose logs nginx
```

If the Nginx health check succeeds but `/health` returns `502`, Nginx is
running and the fault is between Nginx and `ride-booking`. See
[docs/troubleshooting.md](docs/troubleshooting.md) for the diagnostic sequence.

---

## Network Security

driver-matching and ride-dispatch are protected in two ways:

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
git clone https://github.com/lwambisrat/production-service-lab.git
cd production-service-lab
bash scripts/install.sh
```

The script:

1. Installs system packages (python3, nginx, ufw, curl, rsync)
2. Adds `/etc/hosts` entries for service discovery
3. Creates a dedicated `ridelab` system account and deploys the code to
   `/opt/ridelab` (with its own venv), owned by that account
4. Installs the systemd service files
5. Configures Nginx
6. Configures the UFW firewall
7. Enables and starts all services
8. Runs `verify.sh` to confirm everything is working

### Deployment model

The code runs from **`/opt/ridelab`**, not from the git checkout you edit in,
and the services run as a **dedicated, unprivileged `ridelab` system account**
(no login shell, no home directory) rather than your login user. Two reasons:

* **Least privilege** — if a service is ever compromised, the blast radius is a
  locked-down account, not your full user.
* **Stable runtime** — `/opt/ridelab` is on native disk. Running services
  directly out of the repo can break on a VM that mounts the repo over a shared
  folder (e.g. Lima's virtiofs share of your Mac).

To **redeploy after a code change**, just re-run `bash scripts/install.sh` — it
re-syncs `/opt/ridelab` and restarts the services. (`install.sh` is idempotent.)

---

## Running with Docker Compose

Docker Compose runs the same production flow without systemd, `/etc/hosts`, or
UFW. Nginx remains the only public entry point; application containers
communicate over the private Compose network using Docker DNS.

```text
Host :8080
    ↓
Nginx :80
    ↓
ride-booking :3001
    ↓
driver-matching :3002
    ↓
ride-dispatch :3003
    ↓
ride-booking callback
```

**Prerequisite:** Docker Engine with the Compose plugin, or Docker Desktop.
Make sure no other project is using host port 8080.

### Container files

| File | Purpose |
|------|---------|
| [`docker-compose.yml`](docker-compose.yml) | Defines Nginx and the three application services, health checks, dependency readiness, restart policies, environment variables, and networking |
| [`Dockerfile`](Dockerfile) | Builds one shared Python image because all three services use the same Uvicorn runtime, dependencies, and source layout |
| [`.dockerignore`](.dockerignore) | Excludes Git data, virtual environments, caches, logs, VM files, and documentation from the image build context |
| [`nginx/compose.conf`](nginx/compose.conf) | Routes public traffic only to `ride-booking` and sends access/error logs to container stdout/stderr |
| [`docs/CONTAINER_VALIDATION.md`](docs/CONTAINER_VALIDATION.md) | Records the seven required Compose tests with expected behavior, actual results, and screenshots |

The shared image runs the Python services as the unprivileged user
`appuser` (UID/GID 10001). Compose selects the correct application by setting a
different working directory, command, port, and downstream URL for each service.

### Startup and readiness

Every container has a health check. `depends_on` with
`condition: service_healthy` produces this startup order:

```text
ride-dispatch healthy
    ↓
driver-matching healthy
    ↓
ride-booking healthy
    ↓
Nginx starts
```

`docker compose ps` should report all four containers as `healthy`. These
checks confirm that each process answers its own health endpoint; controlled
downstream failure is tested separately.

### Start the system

```bash
docker compose up --build -d
docker compose ps
```

Expected services:

- `nginx`
- `ride-booking`
- `driver-matching`
- `ride-dispatch`

### Verify health and the public route

```bash
curl -i http://localhost:8080/nginx-health
curl -s http://localhost:8080/health | python3 -m json.tool
curl -s -X POST http://localhost:8080/ride/request | python3 -m json.tool
```

Expected:

- `/nginx-health` returns `200 OK` and `ok`.
- `/health` identifies `ride-booking`.
- The ride request returns `"status":"accepted"` and a `matched_driver`.

### Networking and service discovery

Only Nginx has a `ports:` entry (`8080:80`). The Python services bind to
`0.0.0.0` inside their containers so peers can reach them, but they remain
private because their ports are not published to the host.

```bash
# Host access fails because these ports are not published:
curl -i --connect-timeout 3 http://localhost:3002/health
curl -i --connect-timeout 3 http://localhost:3003/health

# Internal access works through Docker DNS service names:
docker compose exec ride-booking   curl -s http://driver-matching:3002/health
docker compose exec driver-matching curl -s http://ride-dispatch:3003/health
```

Downstream URLs use Compose names rather than `localhost`:

- `ride-booking` → `http://driver-matching:3002/driver/match`
- `driver-matching` → `http://ride-dispatch:3003/ride/dispatch`
- `ride-dispatch` → `http://ride-booking:3001/ride/callback`

### View logs

Application JSON logs, Uvicorn logs, and Nginx logs all go to stdout/stderr:

```bash
docker compose logs -f
docker compose logs -f ride-booking
docker compose logs -f driver-matching
docker compose logs -f ride-dispatch
docker compose logs -f nginx
docker compose logs | grep <request-id>
```

### Trace a request

```bash
curl -s -X POST http://localhost:8080/ride/request \
  -H "X-Request-ID: demo-container-001" >/dev/null

docker compose logs | grep demo-container-001
```

The request ID should appear in Nginx, ride-booking, driver-matching, and
ride-dispatch logs with the same ride ID.

### Test failure and recovery

`driver-matching` is Service B. Stopping it leaves Nginx, ride-booking, and
ride-dispatch running, while new ride requests fail cleanly:

```bash
docker compose stop driver-matching

curl -i -X POST http://localhost:8080/ride/request \
  -H "X-Request-ID: fail-service-b-001"

docker compose logs ride-booking | grep fail-service-b-001
```

Expected: HTTP 502 and a `driver_matching_unreachable` error with
`outcome=failure`.

Recover:

```bash
docker compose start driver-matching
sleep 3
curl -i -X POST http://localhost:8080/ride/request \
  -H "X-Request-ID: recovery-001"
```

The recovery request should return HTTP 200. `restart: unless-stopped` restarts
containers after crashes or host restarts, but respects an intentional
`docker compose stop`.

### Shut everything down

```bash
docker compose down
```

This removes the containers and Compose network but keeps the built image.

### Compose documentation and evidence

- Follow [docs/CONTAINER_VALIDATION.md](docs/CONTAINER_VALIDATION.md) for the
  complete seven-test review sequence and screenshots.
- Read [docs/architecture.md](docs/architecture.md) for the expanded request
  flow and service boundaries.
- Use [docs/troubleshooting.md](docs/troubleshooting.md) when startup, ports,
  Nginx, discovery, or logs do not behave as expected.
- Compare [docs/VALIDATION_EVIDENCE.md](docs/VALIDATION_EVIDENCE.md) to see how
  the same behavior is proven under the VM/systemd runtime.

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

Answered by Nginx directly — no service involved. (If you ran `install.sh`, the
config is already in place; just run the `curl`.)

```bash
curl http://localhost/nginx-health
```

### Service health checks

```bash
# Through Nginx (public path — hits ride-booking)
curl http://localhost/health
```

Expected response:

```json
{"service": "ride-booking", "status": "healthy", "port": 3001}
```

```bash
# Direct to each service (from inside the VM only)
curl http://localhost:3001/health
curl http://localhost:3002/health
curl http://localhost:3003/health
```

Expected responses:

```json
{"service": "ride-booking",    "status": "healthy", "port": 3001}
{"service": "driver-matching", "status": "healthy", "port": 3002}
{"service": "ride-dispatch",   "status": "healthy", "port": 3003}
```

### Full chain test

This triggers the entire ride-booking → driver-matching → ride-dispatch → ride-booking flow in one request:

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

**ride-booking — trigger ride booking:**

```bash
curl -s -X POST http://localhost:3001/ride/request
```

**driver-matching — trigger driver matching:**

```bash
curl -s -X POST http://localhost:3002/driver/match \
  -H "Content-Type: application/json" \
  -d '{"request_id": "test-123", "pickup": {"lat": -1.28, "lng": 36.82}}'
```

**ride-dispatch — trigger ride dispatch:**

```bash
curl -s -X POST http://localhost:3003/ride/dispatch \
  -H "Content-Type: application/json" \
  -d '{"request_id": "test-123", "driver": "Brian", "pickup": {"lat": -1.28, "lng": 36.82}}'
```

**ride-booking — test callback endpoint:**

```bash
curl -s -X POST http://localhost:3001/ride/callback \
  -H "Content-Type: application/json" \
  -d '{"request_id": "test-123", "driver": "Brian", "status": "dispatched"}'
```

### Run the full verification script

```bash
bash scripts/verify.sh
```

For a step-by-step walkthrough of **every** scenario — health, full chain,
tracing, all failure cases, crash-restart, boot recovery, and network security —
see the consolidated [docs/TESTING.md](docs/TESTING.md).

### Evidence pack — prove it, don't just assert it

`verify.sh` proves the system works *inside the VM*. For a complete, reviewable
record — including the external/host checks that confirm internal services are
**not** publicly reachable — use the evidence pack:

```bash
# Gather the inside-VM evidence (paste output into the doc)
bash scripts/collect-evidence.sh | tee evidence-$(date +%Y%m%d).txt
```

Then fill in [docs/VALIDATION_EVIDENCE.md](docs/VALIDATION_EVIDENCE.md), which
lists every major claim with its command, where it was run, the expected result,
the actual result, and a pass/fail verdict. Host/external rows must be run from a
separate machine — the script reminds you which ones.

---

## Logging

All services produce structured JSON logs.

Each log entry contains:

| Field         | Description                              |
| ------------- | ---------------------------------------- |
| `timestamp`   | ISO 8601 UTC timestamp                   |
| `level`       | INFO, WARNING, or ERROR                  |
| `service`     | Which service produced the log (matches the systemd unit name) |
| `event`       | What happened                            |
| `request_id`  | Random per-request trace ID tying all logs for one request |
| `ride_id`     | Business ID for the ride (`RIDE-XXXXXX`), propagated end to end via `X-Ride-ID` |
| `message`     | Human-readable description               |
| `outcome`     | Result of the step: `success`, `failure`, `degraded`, or `ok` |
| `duration_ms` | Wall-clock time the downstream call took (latency), on completion/failure |

Some events carry extra context. Notably, the `ride_request_received` event on
ride-booking includes a `client_ip` field (taken from the Nginx-forwarded
`X-Forwarded-For` / `X-Real-IP` header, falling back to the socket peer), so you
can see which client started each ride. Nginx's own access log records the
client IP independently — see [View Nginx logs](#view-nginx-logs) below.

### Lifecycle events

Each service logs `service_starting` and `service_started` on boot and
`service_stopping` on shutdown, so a clean stop/restart is visible in the journal
(not just an abrupt disappearance):

```bash
sudo journalctl -u ride-booking | grep -E 'service_started|service_stopping'
```

### View logs

```bash
# Last 50 lines from each service
sudo journalctl -u ride-booking -n 50
sudo journalctl -u driver-matching -n 50
sudo journalctl -u ride-dispatch -n 50

# Follow live across all three services
sudo journalctl -f -u ride-booking -u driver-matching -u ride-dispatch
```

### View Nginx logs

Nginx writes a custom access log that includes the `trace` ID, so its lines can
be correlated with the JSON service logs above:

```bash
# Access log (includes client IP, status, trace ID, upstream, request time)
sudo tail -f /var/log/nginx/ride-booking_access.log

# Error log (502s, upstream connection failures, config issues)
sudo tail -f /var/log/nginx/ride-booking_error.log
```

### Trace a specific request

Every request gets a `request_id`. To follow one request across all services:

```bash
sudo journalctl -u ride-booking -u driver-matching -u ride-dispatch | grep <request_id>
```

---

## Request Tracing

Two correlation IDs flow through the whole chain:

* **`request_id`** (`X-Request-ID`) — a random UUID per request. Generated by
  ride-booking if the client didn't supply one.
* **`ride_id`** (`X-Ride-ID`) — the *business* ID for the ride (`RIDE-XXXXXX`),
  so you can follow one customer's ride, not just one HTTP request.

Both are:

* Passed to driver-matching, then to ride-dispatch, via headers on each hop
* Included in the callback from ride-dispatch back to ride-booking
* Logged by every service at every step

This means a single request can be traced across all four hops:

```
ride-booking:    ride_request_received     request_id=abc123  ride_id=RIDE-A1B2C3
driver-matching: driver_matched            request_id=abc123  ride_id=RIDE-A1B2C3
ride-dispatch:   ride_dispatch_started     request_id=abc123  ride_id=RIDE-A1B2C3
ride-booking:    ride_dispatch_confirmed   request_id=abc123  ride_id=RIDE-A1B2C3
```

To follow one ride end to end by its business ID:

```bash
sudo journalctl -u ride-booking -u driver-matching -u ride-dispatch -o cat | grep RIDE-A1B2C3
```

---

## Troubleshooting

### Working in the VM (Lima / shared-folder gotcha)

If your VM mounts this repo over a shared folder (e.g. Lima exposes your Mac at
`/Users/...` via virtiofs), `git` inside that path uses the **Mac's** SSH/remote
and you'll hit `Permission denied (publickey)` on clone/pull. Always work from a
**native clone** in the VM's own home directory:

```bash
cd ~                              # leave the shared folder
pwd                               # must show /home/<user>/..., not /Users/...
git clone https://github.com/lwambisrat/production-service-lab.git
cd production-service-lab
```

This also matters at runtime: services run from `/opt/ridelab` (native disk),
never from the shared folder, so a flaky mount can't take them down.

### Wrong service answering / ports already in use

Symptoms: `systemctl is-active ride-booking driver-matching ride-dispatch` shows
`activating` (crash-looping), the journal shows `address already in use`, or
`curl http://localhost/health` returns a **different** service than `ride-booking`.

Cause: another process already owns port 3001, 3002, or 3003 — commonly a second
lab (these ports are popular) or leftover processes from an earlier deploy. Only
one app can run on these ports at a time.

```bash
# see exactly what owns the ports (note the cgroup/unit and PID)
sudo ss -tulpn | grep -E ':3001|:3002|:3003'

# if it's another systemd service (e.g. a different lab), stop + disable it
sudo systemctl disable --now <that-service>

# if it's a stray process not managed by systemd, kill it
sudo pkill -f '<its command>'

# then clear the crash-loop state and start this stack in order
sudo systemctl reset-failed ride-booking driver-matching ride-dispatch
sudo systemctl start ride-dispatch driver-matching ride-booking
curl -s http://localhost/health    # should now report "ride-booking"
```

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

ride-booking requires driver-matching and ride-dispatch. If either is down, ride-booking will not start.

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

# A 502 from Nginx means ride-booking is down
curl -s http://localhost:3001/health
```

### Service discovery failure

```bash
# Check entries exist
grep internal /etc/hosts

# Test resolution
getent hosts driver-matching.internal
getent hosts ride-dispatch.internal

# Re-add if missing
echo '127.0.0.1   driver-matching.internal' | sudo tee -a /etc/hosts
echo '127.0.0.1   ride-dispatch.internal' | sudo tee -a /etc/hosts
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
curl -s http://driver-matching.internal:3002/health
curl -s http://ride-dispatch.internal:3003/health

# Check /etc/hosts
getent hosts driver-matching.internal
getent hosts ride-dispatch.internal
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
