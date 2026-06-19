from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from datetime import datetime
import httpx
import json
import math
import uuid

app = FastAPI(title="Service B - Driver Matching Service")

SERVICE_NAME = "service-b"
SERVICE_C_URL = "http://service-c.internal:3003/dispatch"


MOCK_DRIVERS = [
    {
        "driver_id": "DRV-101",
        "driver_name": "Brian",
        "area": "Westlands",
        "lat": -1.2650,
        "lng": 36.8120,
        "vehicle": "Toyota Axio",
        "available": True,
    },
    {
        "driver_id": "DRV-202",
        "driver_name": "Mary",
        "area": "Kilimani",
        "lat": -1.2921,
        "lng": 36.7834,
        "vehicle": "Mazda Demio",
        "available": True,
    },
    {
        "driver_id": "DRV-303",
        "driver_name": "Kevin",
        "area": "CBD",
        "lat": -1.2864,
        "lng": 36.8172,
        "vehicle": "Toyota Vitz",
        "available": True,
    },
]


def log_event(event, request_id=None, status="info", extra=None):
    log = {
        "timestamp": datetime.utcnow().isoformat(),
        "service": SERVICE_NAME,
        "event": event,
        "request_id": request_id,
        "status": status,
    }
    if extra:
        log.update(extra)
    print(json.dumps(log), flush=True)


def distance_score(lat1, lng1, lat2, lng2):
    return math.sqrt((lat1 - lat2) ** 2 + (lng1 - lng2) ** 2)


def estimate_eta_minutes(distance):
    return max(3, round(distance * 1000))


@app.get("/health")
def health():
    return {"service": SERVICE_NAME, "status": "healthy"}


@app.post("/match-driver")
async def match_driver(request: Request):
    body = await request.json()
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    log_event("driver_matching_started", request_id, extra={"ride_request": body})

    pickup = body.get("pickup", {})
    pickup_lat = pickup.get("lat")
    pickup_lng = pickup.get("lng")

    if pickup_lat is None or pickup_lng is None:
        log_event(
            "driver_matching_failed_missing_pickup_coordinates",
            request_id,
            status="error",
            extra={"pickup": pickup},
        )

        return JSONResponse(
            status_code=400,
            content={
                "request_id": request_id,
                "service": SERVICE_NAME,
                "status": "error",
                "message": "pickup.lat and pickup.lng are required",
            },
        )

    available_drivers = [driver for driver in MOCK_DRIVERS if driver["available"]]

    best_driver = min(
        available_drivers,
        key=lambda driver: distance_score(
            pickup_lat,
            pickup_lng,
            driver["lat"],
            driver["lng"],
        ),
    )

    distance = distance_score(
        pickup_lat,
        pickup_lng,
        best_driver["lat"],
        best_driver["lng"],
    )

    matched_driver = {
        "driver_id": best_driver["driver_id"],
        "driver_name": best_driver["driver_name"],
        "area": best_driver["area"],
        "vehicle": best_driver["vehicle"],
        "driver_location": {
            "lat": best_driver["lat"],
            "lng": best_driver["lng"],
        },
        "eta_minutes": estimate_eta_minutes(distance),
        "match_reason": "Closest available driver to pickup location",
    }

    dispatch_payload = {
        "request_id": request_id,
        "ride_id": body.get("ride_id"),
        "customer": body.get("customer"),
        "pickup": body.get("pickup"),
        "dropoff": body.get("dropoff"),
        "matched_driver": matched_driver,
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            service_c_response = await client.post(
                SERVICE_C_URL,
                json=dispatch_payload,
                headers={"X-Request-ID": request_id},
            )

        log_event(
            "matched_driver_forwarded_to_dispatch",
            request_id,
            status="success",
            extra={
                "matched_driver": matched_driver,
                "service_c_status_code": service_c_response.status_code,
            },
        )

        return JSONResponse(
            content={
                "request_id": request_id,
                "service": SERVICE_NAME,
                "status": "driver_matched",
                "matched_driver": matched_driver,
                "dispatch_response": service_c_response.json(),
            }
        )

    except Exception as e:
        log_event(
            "dispatch_service_call_failed",
            request_id,
            status="error",
            extra={"error": str(e)},
        )

        return JSONResponse(
            status_code=502,
            content={
                "request_id": request_id,
                "service": SERVICE_NAME,
                "status": "error",
                "message": "Failed to reach Ride Dispatch Service",
                "error": str(e),
            },
        )


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    log_event(
        "invalid_endpoint",
        request_id,
        status="error",
        extra={"path": str(request.url.path)},
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
