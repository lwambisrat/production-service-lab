"""
Ride Dispatch Service (port 3003).

Internal service. Receives the matched driver from the driver-matching
service, finalises the ride dispatch, and sends a confirmation callback
to the ride-booking service.

Responsibilities:
  - GET  /health         — liveness probe
  - POST /ride/dispatch  — finalise dispatch, callback to ride-booking

Note: Failure to reach the ride-booking service for the callback does NOT
fail the dispatch — the driver has already been assigned. The error is
logged at WARNING level so it can be investigated without alarming on-call.
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
# Configuration
# ---------------------------------------------------------------------------
SERVICE_NAME  = "ride-dispatch"
BIND_HOST     = os.getenv("BIND_HOST", "127.0.0.1")
SERVICE_PORT  = int(os.getenv("SERVICE_PORT", "3003"))
CALLBACK_URL  = os.getenv("CALLBACK_URL", "http://ride-booking.internal:3001/ride/callback")
DOWNSTREAM_TIMEOUT = float(os.getenv("DOWNSTREAM_TIMEOUT", "5"))

REQUEST_ID_HEADER = "X-Request-ID"   # random per-request trace id
RIDE_ID_HEADER    = "X-Ride-ID"      # business id, propagated end to end

logger = get_logger(SERVICE_NAME)

log_event(logger, "service_starting", f"{SERVICE_NAME} starting on {BIND_HOST}:{SERVICE_PORT}",
          request_id="startup", callback=CALLBACK_URL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Log a structured event when the service becomes ready and when it shuts down."""
    log_event(logger, "service_started", f"{SERVICE_NAME} ready on {BIND_HOST}:{SERVICE_PORT}",
              request_id="startup")
    yield
    log_event(logger, "service_stopping", f"{SERVICE_NAME} shutting down — no longer accepting requests",
              request_id="shutdown")


app = FastAPI(title="Ride Dispatch Service", lifespan=lifespan)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"service": SERVICE_NAME, "status": "healthy", "port": SERVICE_PORT}


@app.post("/ride/dispatch")
async def ride_dispatch(request: Request):
    """Finalise ride dispatch and notify the ride-booking service via callback."""
    body       = await request.json()
    request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
    ride_id    = request.headers.get(RIDE_ID_HEADER) or body.get("ride_id")
    started    = time.perf_counter()

    log_event(logger, "ride_dispatch_started", "Ride dispatch started",
              request_id, ride_id=ride_id,
              customer=body.get("customer"),
              driver_id=body.get("matched_driver", {}).get("driver_id"),
              driver_name=body.get("matched_driver", {}).get("driver_name"))

    callback_payload = {
        "request_id":      request_id,
        "source_service":  SERVICE_NAME,
        "ride_id":         ride_id,
        "ride_status":     "driver_assigned",
        "message":         "Ride dispatched successfully. Driver is on the way.",
        "pickup":          body.get("pickup"),
        "dropoff":         body.get("dropoff"),
        "assigned_driver": body.get("matched_driver"),
    }

    outcome = "success"
    try:
        async with httpx.AsyncClient(timeout=DOWNSTREAM_TIMEOUT) as client:
            cb_response = await client.post(
                CALLBACK_URL,
                json=callback_payload,
                headers={REQUEST_ID_HEADER: request_id, RIDE_ID_HEADER: ride_id or ""},
            )

        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        log_event(logger, "dispatch_callback_sent", "Dispatch callback sent to ride-booking",
                  request_id, ride_id=ride_id, target="ride-booking", status=cb_response.status_code,
                  outcome="success", duration_ms=duration_ms)

    except Exception as exc:
        # Driver is already assigned — do not fail the dispatch.
        # Log at WARNING so the team can investigate without triggering an alert.
        outcome = "degraded"
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        log_event(logger, "booking_service_callback_failed",
                  "Could not reach ride-booking for dispatch callback — ride is still dispatched",
                  request_id, "WARNING", ride_id=ride_id, target="ride-booking",
                  error=str(exc), outcome="degraded", duration_ms=duration_ms)

    return JSONResponse(content={
        "request_id":      request_id,
        "ride_id":         ride_id,
        "status":          "dispatched",
        "outcome":         outcome,
        "message":         "Ride dispatched successfully",
        "assigned_driver": body.get("matched_driver"),
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
        "available_endpoints": ["GET /health", "POST /ride/dispatch"],
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
