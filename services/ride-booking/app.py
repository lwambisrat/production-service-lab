"""
Ride Booking API (port 3001).

Public entrypoint for the ride booking system. All external traffic
enters here through Nginx. Responsible for:
  - Accepting ride requests from users
  - Forwarding to the driver-matching service for processing
  - Receiving the dispatch callback from the ride-dispatch service
  - Logging all activity with a shared request_id for tracing
"""

import os
import time
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from common.logging_setup import get_logger, log_event

# ---------------------------------------------------------------------------
# Configuration — all via environment, nothing hardcoded
# ---------------------------------------------------------------------------
SERVICE_NAME = "ride-booking"
BIND_HOST    = os.getenv("BIND_HOST", "127.0.0.1")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "3001"))
DRIVER_MATCHING_URL  = os.getenv("DRIVER_MATCHING_URL", "http://driver-matching.internal:3002/driver/match")
DOWNSTREAM_TIMEOUT   = float(os.getenv("DOWNSTREAM_TIMEOUT", "5"))

REQUEST_ID_HEADER = "X-Request-ID"   # random per-request trace id
RIDE_ID_HEADER    = "X-Ride-ID"      # business id (one per ride), propagated end to end

logger = get_logger(SERVICE_NAME)

log_event(logger, "service_starting", f"{SERVICE_NAME} starting on {BIND_HOST}:{SERVICE_PORT}",
          request_id="startup", target=DRIVER_MATCHING_URL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Log a structured event when the service becomes ready and when it shuts down."""
    log_event(logger, "service_started", f"{SERVICE_NAME} ready on {BIND_HOST}:{SERVICE_PORT}",
              request_id="startup")
    yield
    log_event(logger, "service_stopping", f"{SERVICE_NAME} shutting down — no longer accepting requests",
              request_id="shutdown")


app = FastAPI(title="Ride Booking API", lifespan=lifespan)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"service": SERVICE_NAME, "status": "healthy", "port": SERVICE_PORT}


@app.post("/ride/request")
async def ride_request(request: Request):
    """Accept a ride request and forward to driver matching."""
    request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
    # Business id: reuse a client-supplied one, else mint a fresh ride id here
    # (this is the front door). It rides alongside request_id on every hop.
    ride_id    = request.headers.get(RIDE_ID_HEADER) or f"RIDE-{uuid.uuid4().hex[:6].upper()}"
    started    = time.perf_counter()

    # Originating client IP — prefer Nginx-forwarded headers, fall back to the
    # direct socket peer. Lets us trace which client started each ride request.
    client_ip = (
        request.headers.get("X-Forwarded-For")
        or request.headers.get("X-Real-IP")
        or (request.client.host if request.client else "unknown")
    )

    ride_payload = {
        "ride_id":  ride_id,
        "customer": "Lwam",
        "pickup":   {"area": "Westlands", "lat": -1.2676, "lng": 36.8108},
        "dropoff":  {"area": "CBD",       "lat": -1.2864, "lng": 36.8172},
    }

    log_event(logger, "ride_request_received", "Ride request received from client",
              request_id, ride_id=ride_id, customer=ride_payload["customer"],
              client_ip=client_ip)

    try:
        async with httpx.AsyncClient(timeout=DOWNSTREAM_TIMEOUT) as client:
            response = await client.post(
                DRIVER_MATCHING_URL,
                json=ride_payload,
                headers={REQUEST_ID_HEADER: request_id, RIDE_ID_HEADER: ride_id},
            )
        duration_ms = round((time.perf_counter() - started) * 1000, 1)

        # driver-matching answered but reported an error (e.g. ride-dispatch was
        # down, so the driver was matched but the ride could not be dispatched).
        # Do NOT tell the customer the ride was accepted — surface the failure.
        if response.status_code >= 400:
            log_event(logger, "ride_request_failed",
                      "Downstream returned an error status; ride not completed",
                      request_id, "ERROR", ride_id=ride_id, target="driver-matching",
                      status=response.status_code, outcome="failure", duration_ms=duration_ms)
            return JSONResponse(status_code=502, content={
                "request_id": request_id,
                "ride_id":    ride_id,
                "status":     "error",
                "message":    "Ride could not be completed — a downstream service is unavailable.",
            })

        result = response.json()
        matched_driver = result.get("matched_driver", {})

        log_event(logger, "ride_request_forwarded", "Ride request forwarded to driver matching",
                  request_id, ride_id=ride_id, target="driver-matching", status=response.status_code,
                  driver_name=matched_driver.get("driver_name"),
                  outcome="success", duration_ms=duration_ms)

        return JSONResponse(content={
            "request_id":     request_id,
            "status":         "accepted",
            "message":        "Ride request accepted. Driver matched and dispatched.",
            "ride_id":        ride_id,
            "customer":       ride_payload["customer"],
            "pickup":         ride_payload["pickup"],
            "dropoff":        ride_payload["dropoff"],
            "matched_driver": matched_driver,
        })

    except Exception as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        log_event(logger, "driver_matching_unreachable",
                  "Driver matching service is unavailable",
                  request_id, "ERROR", ride_id=ride_id, target="driver-matching",
                  error=str(exc), outcome="failure", duration_ms=duration_ms)

        return JSONResponse(status_code=502, content={
            "request_id": request_id,
            "ride_id":    ride_id,
            "status":     "error",
            "message":    "Driver matching service is unavailable. Please try again later.",
        })


@app.post("/ride/callback")
async def ride_callback(request: Request):
    """Receive dispatch confirmation callback from the ride-dispatch service."""
    body       = await request.json()
    request_id = body.get("request_id") or request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
    ride_id    = body.get("ride_id") or request.headers.get(RIDE_ID_HEADER)

    log_event(logger, "ride_dispatch_confirmed", "Dispatch confirmation received from ride-dispatch",
              request_id,
              ride_id=ride_id,
              ride_status=body.get("ride_status"),
              assigned_driver=body.get("assigned_driver"),
              outcome="ok")

    return {"status": "received", "message": "Dispatch confirmation acknowledged", "request_id": request_id}


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.exception_handler(404)
async def not_found(request: Request, exc):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    log_event(logger, "route_not_found", f"No route for {request.method} {request.url.path}",
              request_id, "WARNING", method=request.method, path=str(request.url.path))

    return JSONResponse(status_code=404, content={
        "error":               "Endpoint not found",
        "service":             SERVICE_NAME,
        "path":                str(request.url.path),
        "request_id":          request_id,
        "hint":                f"'{request.url.path}' does not exist on {SERVICE_NAME}",
        "available_endpoints": ["GET /health", "POST /ride/request", "POST /ride/callback"],
    })


@app.exception_handler(500)
async def internal_error(request: Request, exc):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    log_event(logger, "internal_error", "Unhandled internal error",
              request_id, "ERROR", path=str(request.url.path), error=str(exc))

    return JSONResponse(status_code=500, content={
        "error":      "Internal server error",
        "service":    SERVICE_NAME,
        "request_id": request_id,
    })
