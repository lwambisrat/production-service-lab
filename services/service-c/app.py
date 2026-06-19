from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from datetime import datetime
import httpx
import json
import uuid

app = FastAPI(title="Service C - Ride Dispatch Service")

SERVICE_NAME = "service-c"
SERVICE_PORT = 3003
SERVICE_A_CALLBACK_URL = "http://service-a.internal:3001/greeting-rcvd"


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
        "message": "Hello service-c listening on 3003",
    }


@app.get("/greet-c")
async def greet_c(request: Request):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    dispatch_header = request.headers.get("X-Dispatch-Payload")

    try:
        dispatch_payload = json.loads(dispatch_header) if dispatch_header else {}

        log_event(
            "ride_dispatch_started",
            request_id,
            "/greet-c",
            200,
            {"dispatch_payload": dispatch_payload},
        )

        callback_payload = {
            "request_id": request_id,
            "source_service": SERVICE_NAME,
            "message": "Greeting processed",
            "timestamp": now(),
            "ride_status": "driver_assigned",
            "ride_request": dispatch_payload.get("ride_request"),
            "assigned_driver": dispatch_payload.get("matched_driver"),
        }

        async with httpx.AsyncClient(timeout=5.0) as client:
            callback_response = await client.post(
                SERVICE_A_CALLBACK_URL,
                json=callback_payload,
                headers={"X-Request-ID": request_id},
            )

        log_event(
            "callback_sent",
            request_id,
            "/greet-c",
            callback_response.status_code,
            {"target": "service-a"},
        )

        return {
            "request_id": request_id,
            "status": "processed",
            "callback_sent": True,
        }

    except Exception as e:
        log_event(
            "request_failed",
            request_id,
            "/greet-c",
            500,
            {"error": str(e)},
        )

        return JSONResponse(
            status_code=500,
            content={
                "request_id": request_id,
                "status": "error",
                "message": "Ride dispatch failed",
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
