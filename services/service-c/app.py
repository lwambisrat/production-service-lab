"""
Service C — Ride Dispatch Service (port 3003).

Internal service. Receives matched driver from Service B, finalises
the ride dispatch, and sends a confirmation callback to Service A.

Responsibilities:
  - GET  /health         — liveness probe
  - POST /ride/dispatch  — finalise dispatch, callback to service-a

Note: Failure to reach Service A for the callback does NOT fail the
dispatch — the driver has already been assigned. The error is logged
at WARNING level so it can be investigated without alarming on-call.
"""

import os
import uuid

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from common.logging_setup import get_logger, log_event

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
SERVICE_NAME  = "service-c"
BIND_HOST     = os.getenv("BIND_HOST", "127.0.0.1")
SERVICE_PORT  = int(os.getenv("SERVICE_PORT", "3003"))
CALLBACK_URL  = os.getenv("CALLBACK_URL", "http://service-a.internal:3001/ride/callback")
DOWNSTREAM_TIMEOUT = float(os.getenv("DOWNSTREAM_TIMEOUT", "5"))

logger = get_logger(SERVICE_NAME)
app    = FastAPI(title="Service C — Ride Dispatch Service")

log_event(logger, "service_starting", f"{SERVICE_NAME} starting on {BIND_HOST}:{SERVICE_PORT}",
          request_id="startup", callback=CALLBACK_URL)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"service": SERVICE_NAME, "status": "healthy", "port": SERVICE_PORT}


@app.post("/ride/dispatch")
async def ride_dispatch(request: Request):
    """Finalise ride dispatch and notify Service A via callback."""
    body       = await request.json()
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

    log_event(logger, "ride_dispatch_started", "Ride dispatch started",
              request_id,
              ride_id=body.get("ride_id"),
              customer=body.get("customer"),
              driver_id=body.get("matched_driver", {}).get("driver_id"),
              driver_name=body.get("matched_driver", {}).get("driver_name"))

    callback_payload = {
        "request_id":      request_id,
        "source_service":  SERVICE_NAME,
        "ride_id":         body.get("ride_id"),
        "ride_status":     "driver_assigned",
        "message":         "Ride dispatched successfully. Driver is on the way.",
        "pickup":          body.get("pickup"),
        "dropoff":         body.get("dropoff"),
        "assigned_driver": body.get("matched_driver"),
    }

    try:
        async with httpx.AsyncClient(timeout=DOWNSTREAM_TIMEOUT) as client:
            cb_response = await client.post(
                CALLBACK_URL,
                json=callback_payload,
                headers={"X-Request-ID": request_id},
            )

        log_event(logger, "dispatch_callback_sent", "Dispatch callback sent to service-a",
                  request_id, target="service-a", status=cb_response.status_code)

    except Exception as exc:
        # Driver is already assigned — do not fail the dispatch.
        # Log at WARNING so the team can investigate without triggering an alert.
        log_event(logger, "booking_service_callback_failed",
                  "Could not reach service-a for dispatch callback — ride is still dispatched",
                  request_id, "WARNING", target="service-a", error=str(exc))

    return JSONResponse(content={
        "request_id":      request_id,
        "status":          "dispatched",
        "ride_id":         body.get("ride_id"),
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
