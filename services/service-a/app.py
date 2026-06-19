from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from datetime import datetime
import httpx
import json
import uuid

app = FastAPI(title="Service A - Ride Booking API")

SERVICE_NAME = "service-a"
SERVICE_PORT = 3001
SERVICE_B_URL = "http://service-b.internal:3002/greet"


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


@app.get("/health")
def health():
    return {
        "service": SERVICE_NAME,
        "status": "healthy",
        "port": SERVICE_PORT,
        "message": "Hello service-a listening on 3001",
    }


@app.get("/greet-service-b")
async def greet_service_b(request: Request):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    ride_request = {
        "ride_id": "RIDE-001",
        "customer": "Lwam",
        "pickup": {
            "area": "Westlands",
            "lat": -1.2676,
            "lng": 36.8108,
        },
        "dropoff": {
            "area": "CBD",
            "lat": -1.2864,
            "lng": 36.8172,
        },
    }

    log_event(
        "ride_request_received",
        request_id,
        "/greet-service-b",
        200,
        {"method": "GET", "ride_request": ride_request},
    )

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                SERVICE_B_URL,
                headers={
                    "X-Request-ID": request_id,
                    "X-Ride-Request": json.dumps(ride_request),
                },
            )

        log_event(
            "request_forwarded",
            request_id,
            "/greet-service-b",
            response.status_code,
            {"target": "service-b"},
        )

        return {
            "request_id": request_id,
            "status": "success",
            "message": "Request completed successfully",
        }

    except Exception as e:
        log_event(
            "request_failed",
            request_id,
            "/greet-service-b",
            500,
            {"error": str(e)},
        )
        return JSONResponse(
            status_code=500,
            content={
                "request_id": request_id,
                "status": "error",
                "message": "Failed to reach service-b",
            },
        )


@app.post("/greeting-rcvd")
async def greeting_received(request: Request):
    body = await request.json()
    request_id = body.get("request_id", request.headers.get("X-Request-ID", str(uuid.uuid4())))

    log_event(
        "callback_received",
        request_id,
        "/greeting-rcvd",
        200,
        {
            "source_service": body.get("source_service"),
            "callback_payload": body,
        },
    )

    return {"status": "received"}


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
