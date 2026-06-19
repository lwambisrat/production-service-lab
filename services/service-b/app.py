from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from datetime import datetime
import httpx
import json
import math
import uuid

app = FastAPI(title="Service B - Driver Matching Service")

SERVICE_NAME = "service-b"
SERVICE_PORT = 3002
SERVICE_C_URL = "http://service-c.internal:3003/greet-c"

MOCK_DRIVERS = [
    {"driver_id": "DRV-101", "name": "Brian", "area": "Westlands", "lat": -1.2650, "lng": 36.8120},
    {"driver_id": "DRV-202", "name": "Mary", "area": "Kilimani", "lat": -1.2921, "lng": 36.7834},
    {"driver_id": "DRV-303", "name": "Kevin", "area": "CBD", "lat": -1.2864, "lng": 36.8172},
]


def now():
    return datetime.utcnow().isoformat() + "Z"


def log_event(event, request_id, path, status, extra=None):
    log = {
        "timestamp": now(),
        "service": SERVICE_NAME,
        "event": event,
        "request_id": request_id,
        "path": path,
        "status": status,
    }
    if extra:
        log.update(extra)
    print(json.dumps(log), flush=True)


def distance_score(lat1, lng1, lat2, lng2):
    return math.sqrt((lat1 - lat2) ** 2 + (lng1 - lng2) ** 2)


@app.get("/health")
def health():
    return {
        "service": SERVICE_NAME,
        "status": "healthy",
        "port": SERVICE_PORT,
        "message": "Hello service-b listening on 3002",
    }


@app.get("/greet")
async def greet(request: Request):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    ride_header = request.headers.get("X-Ride-Request")

    try:
        ride_request = json.loads(ride_header) if ride_header else {}
        pickup = ride_request.get("pickup", {})

        best_driver = min(
            MOCK_DRIVERS,
            key=lambda d: distance_score(
                pickup.get("lat", 0),
                pickup.get("lng", 0),
                d["lat"],
                d["lng"],
            ),
        )

        matched_driver = {
            "driver_id": best_driver["driver_id"],
            "driver_name": best_driver["name"],
            "area": best_driver["area"],
            "driver_location": {
                "lat": best_driver["lat"],
                "lng": best_driver["lng"],
            },
            "eta_minutes": 3,
            "match_reason": "Closest available driver to pickup location",
        }

        dispatch_payload = {
            "request_id": request_id,
            "ride_request": ride_request,
            "matched_driver": matched_driver,
        }

        log_event(
            "driver_matched",
            request_id,
            "/greet",
            200,
            {"matched_driver": matched_driver},
        )

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                SERVICE_C_URL,
                headers={
                    "X-Request-ID": request_id,
                    "X-Dispatch-Payload": json.dumps(dispatch_payload),
                },
            )

        log_event(
            "request_forwarded",
            request_id,
            "/greet",
            response.status_code,
            {"target": "service-c"},
        )

        return {
            "request_id": request_id,
            "status": "forwarded",
            "target": "service-c",
        }

    except Exception as e:
        log_event(
            "request_failed",
            request_id,
            "/greet",
            500,
            {"error": str(e)},
        )

        return JSONResponse(
            status_code=500,
            content={
                "request_id": request_id,
                "status": "error",
                "message": "Driver matching failed",
            },
        )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    log_event(
        "route_not_found",
        request_id,
        str(request.url.path),
        404,
        {"method": request.method},
    )

    return JSONResponse(
        status_code=404,
        content={
            "error": "Endpoint not found",
            "service": SERVICE_NAME,
            "path": str(request.url.path),
            "request_id": request_id,
        },
    )
