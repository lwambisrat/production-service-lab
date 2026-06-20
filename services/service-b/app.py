"""
Service B — Driver Matching Service (port 3002).

Internal service. Receives ride requests from Service A, matches
the nearest available driver, and forwards to Service C for dispatch.

Responsibilities:
  - GET  /health        — liveness probe
  - POST /driver/match  — match nearest driver, forward to dispatch
"""

import math
import os
import uuid

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from common.logging_setup import get_logger, log_event

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SERVICE_NAME  = "service-b"
BIND_HOST     = os.getenv("BIND_HOST", "127.0.0.1")
SERVICE_PORT  = int(os.getenv("SERVICE_PORT", "3002"))
DISPATCH_URL  = os.getenv("DISPATCH_URL", "http://service-c.internal:3003/ride/dispatch")
DOWNSTREAM_TIMEOUT = float(os.getenv("DOWNSTREAM_TIMEOUT", "5"))

MOCK_DRIVERS = [
    {"driver_id": "DRV-101", "name": "Brian", "area": "Westlands", "lat": -1.2650, "lng": 36.8120},
    {"driver_id": "DRV-202", "name": "Mary",  "area": "Kilimani",  "lat": -1.2921, "lng": 36.7834},
    {"driver_id": "DRV-303", "name": "Kevin", "area": "CBD",       "lat": -1.2864, "lng": 36.8172},
]

logger = get_logger(SERVICE_NAME)
app    = FastAPI(title="Service B — Driver Matching Service")

log_event(logger, "service_starting", f"{SERVICE_NAME} starting on {BIND_HOST}:{SERVICE_PORT}",
          request_id="startup", target=DISPATCH_URL)

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
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

    log_event(logger, "driver_matching_started", "Driver matching started",
              request_id, ride_id=body.get("ride_id"), customer=body.get("customer"))

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
              request_id,
              driver_id=matched_driver["driver_id"],
              driver_name=matched_driver["driver_name"],
              eta_minutes=matched_driver["eta_minutes"])

    dispatch_payload = {
        "request_id":    request_id,
        "ride_id":       body.get("ride_id"),
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
                headers={"X-Request-ID": request_id},
            )

        log_event(logger, "dispatch_request_forwarded", "Dispatch request forwarded to service-c",
                  request_id, target="service-c", status=response.status_code)

        return JSONResponse(content={
            "request_id":    request_id,
            "status":        "driver_matched",
            "matched_driver": matched_driver,
        })

    except Exception as exc:
        log_event(logger, "dispatch_service_unreachable",
                  "Ride dispatch service is unavailable",
                  request_id, "ERROR", target="service-c", error=str(exc))

        return JSONResponse(status_code=502, content={
            "request_id": request_id,
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
