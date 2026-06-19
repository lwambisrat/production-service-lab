from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from datetime import datetime
import httpx
import json
import uuid

app = FastAPI(title="Service A - Order API")

SERVICE_NAME = "service-a"
SERVICE_B_URL = "http://service-b.internal:3002/validate"


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


@app.get("/health")
def health():
    return {"service": SERVICE_NAME, "status": "healthy"}


@app.post("/orders")
async def create_order(request: Request):
    body = await request.json()
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    log_event("order_received", request_id, extra={"payload": body})

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            service_b_response = await client.post(
                SERVICE_B_URL,
                json=body,
                headers={"X-Request-ID": request_id},
            )

        log_event(
            "forwarded_to_service_b",
            request_id,
            status="success",
            extra={"service_b_status_code": service_b_response.status_code},
        )

        return JSONResponse(
            content={
                "request_id": request_id,
                "service": SERVICE_NAME,
                "status": "accepted",
                "message": "Order received and sent for processing",
                "service_b_response": service_b_response.json(),
            }
        )

    except Exception as e:
        log_event(
            "service_b_call_failed",
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
                "message": "Failed to reach Service B",
                "error": str(e),
            },
        )


@app.post("/callback")
async def callback(request: Request):
    body = await request.json()
    request_id = request.headers.get("X-Request-ID", body.get("request_id", str(uuid.uuid4())))

    log_event(
        "callback_received_from_service_c",
        request_id,
        status="success",
        extra={"callback_payload": body},
    )

    return {
        "service": SERVICE_NAME,
        "status": "callback_received",
        "request_id": request_id,
    }


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
import uuid

app = FastAPI(title="Service A - Ride Booking API")

SERVICE_NAME = "service-a"
SERVICE_B_URL = "http://service-b.internal:3002/match-driver"


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


@app.get("/health")
def health():
    return {"service": SERVICE_NAME, "status": "healthy"}


@app.post("/rides")
async def request_ride(request: Request):
    body = await request.json()
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    log_event("ride_request_received", request_id, extra={"ride_request": body})

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            service_b_response = await client.post(
                SERVICE_B_URL,
                json=body,
                headers={"X-Request-ID": request_id},
            )

        log_event(
            "ride_request_forwarded_to_driver_matching",
            request_id,
            status="success",
            extra={"service_b_status_code": service_b_response.status_code},
        )

        return JSONResponse(
            content={
                "request_id": request_id,
                "service": SERVICE_NAME,
                "status": "ride_request_accepted",
                "message": "Ride request received and sent for driver matching",
                "driver_matching_response": service_b_response.json(),
            }
        )

    except Exception as e:
        log_event(
            "driver_matching_call_failed",
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
                "message": "Failed to reach Driver Matching Service",
                "error": str(e),
            },
        )


@app.post("/callback")
async def dispatch_callback(request: Request):
    body = await request.json()
    request_id = request.headers.get(
        "X-Request-ID",
        body.get("request_id", str(uuid.uuid4()))
    )

    log_event(
        "dispatch_callback_received",
        request_id,
        status="success",
        extra={"callback_payload": body},
    )

    return {
        "service": SERVICE_NAME,
        "status": "callback_received",
        "request_id": request_id,
        "message": "Ride booking service received dispatch confirmation",
    }


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
