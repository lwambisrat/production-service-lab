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
