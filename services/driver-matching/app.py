"""
Driver Matching Service (port 3002).

Internal service. Receives ride requests from the ride-booking service,
matches the nearest available driver, and forwards to the ride-dispatch
service for dispatch.

Responsibilities:
  - GET  /health        — liveness probe
  - POST /driver/match  — match nearest driver, forward to dispatch
"""

import math
import os
import time
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from common.logging_setup import get_logger, log_event

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SERVICE_NAME  = "driver-matching"
BIND_HOST     = os.getenv("BIND_HOST", "127.0.0.1")
SERVICE_PORT  = int(os.getenv("SERVICE_PORT", "3002"))
DISPATCH_URL  = os.getenv("DISPATCH_URL", "http://ride-dispatch.internal:3003/ride/dispatch")
DOWNSTREAM_TIMEOUT = float(os.getenv("DOWNSTREAM_TIMEOUT", "5"))

REQUEST_ID_HEADER = "X-Request-ID"   # random per-request trace id
RIDE_ID_HEADER    = "X-Ride-ID"      # business id, propagated end to end

MOCK_DRIVERS = [
    {"driver_id": "DRV-101", "name": "Brian", "area": "Westlands", "lat": -1.2650, "lng": 36.8120},
    {"driver_id": "DRV-202", "name": "Mary",  "area": "Kilimani",  "lat": -1.2921, "lng": 36.7834},
    {"driver_id": "DRV-303", "name": "Kevin", "area": "CBD",       "lat": -1.2864, "lng": 36.8172},
]

logger = get_logger(SERVICE_NAME)

log_event(logger, "service_starting", f"{SERVICE_NAME} starting on {BIND_HOST}:{SERVICE_PORT}",
          request_id="startup", target=DISPATCH_URL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Log a structured event when the service becomes ready and when it shuts down."""
    log_event(logger, "service_started", f"{SERVICE_NAME} ready on {BIND_HOST}:{SERVICE_PORT}",
              request_id="startup")
    yield
    log_event(logger, "service_stopping", f"{SERVICE_NAME} shutting down — no longer accepting requests",
              request_id="shutdown")


app = FastAPI(title="Driver Matching Service", lifespan=lifespan)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _distance(lat1, lng1, lat2, lng2) -> float:
    return math.sqrt((lat1 - lat2) ** 2 + (lng1 - lng2) ** 2)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"service": SERVICE_NAME, "status": "healthy", "port": SERVICE_PORT}


@app.post("/driver/match")
async def driver_match(request: Request):
    """Match the nearest available driver and forward to ride dispatch."""
    body       = await request.json()
    request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
    ride_id    = request.headers.get(RIDE_ID_HEADER) or body.get("ride_id")
    started    = time.perf_counter()

    log_event(logger, "driver_matching_started", "Driver matching started",
              request_id, ride_id=ride_id, customer=body.get("customer"))

    pickup = body.get("pickup", {})
    best   = min(MOCK_DRIVERS,
                 key=lambda d: _distance(pickup.get("lat", 0), pickup.get("lng", 0), d["lat"], d["lng"]))

    matched_driver = {
        "driver_id":       best["driver_id"],
        "driver_name":     best["name"],
        "area":            best["area"],
        "driver_location": {"lat": best["lat"], "lng": best["lng"]},
        "eta_minutes":     3,
        "match_reason":    "Closest available driver to pickup location",
    }

    log_event(logger, "driver_matched", "Nearest driver matched",
              request_id, ride_id=ride_id,
              driver_id=matched_driver["driver_id"],
              driver_name=matched_driver["driver_name"],
              eta_minutes=matched_driver["eta_minutes"])

    dispatch_payload = {
        "request_id":    request_id,
        "ride_id":       ride_id,
        "customer":      body.get("customer"),
        "pickup":        body.get("pickup"),
        "dropoff":       body.get("dropoff"),
        "matched_driver": matched_driver,
    }

    try:
        async with httpx.AsyncClient(timeout=DOWNSTREAM_TIMEOUT) as client:
            response = await client.post(
                DISPATCH_URL,
                json=dispatch_payload,
                headers={REQUEST_ID_HEADER: request_id, RIDE_ID_HEADER: ride_id or ""},
            )

        duration_ms = round((time.perf_counter() - started) * 1000, 1)

        # ride-dispatch answered with an error status: driver was matched but the
        # ride could not be dispatched. Propagate the failure upstream.
        if response.status_code >= 400:
            log_event(logger, "dispatch_failed",
                      "Ride dispatch returned an error status",
                      request_id, "ERROR", ride_id=ride_id, target="ride-dispatch",
                      status=response.status_code, outcome="failure", duration_ms=duration_ms)
            return JSONResponse(status_code=502, content={
                "request_id": request_id,
                "ride_id":    ride_id,
                "status":     "error",
                "message":    "Ride dispatch service is unavailable. Driver was matched but ride could not be dispatched.",
            })

        log_event(logger, "dispatch_request_forwarded", "Dispatch request forwarded to ride-dispatch",
                  request_id, ride_id=ride_id, target="ride-dispatch", status=response.status_code,
                  outcome="success", duration_ms=duration_ms)

        return JSONResponse(content={
            "request_id":    request_id,
            "ride_id":       ride_id,
            "status":        "driver_matched",
            "matched_driver": matched_driver,
        })

    except Exception as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        log_event(logger, "dispatch_service_unreachable",
                  "Ride dispatch service is unavailable",
                  request_id, "ERROR", ride_id=ride_id, target="ride-dispatch",
                  error=str(exc), outcome="failure", duration_ms=duration_ms)

        return JSONResponse(status_code=502, content={
            "request_id": request_id,
            "ride_id":    ride_id,
            "status":     "error",
            "message":    "Ride dispatch service is unavailable. Driver was matched but ride could not be dispatched.",
        })


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
        "available_endpoints": ["GET /health", "POST /driver/match"],
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
