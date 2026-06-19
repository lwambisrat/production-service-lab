from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from datetime import datetime
import httpx
import json
import uuid

app = FastAPI(title="Service B - Payment Validator")

SERVICE_NAME = "service-b"
SERVICE_C_URL = "http://service-c.internal:3003/process"


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


@app.post("/validate")
async def validate_payment(request: Request):
    body = await request.json()
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    log_event("payment_validation_started", request_id, extra={"payload": body})

    validation_result = {
        "request_id": request_id,
        "payment_status": "validated",
        "message": "Payment validated successfully",
        "original_payload": body,
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            service_c_response = await client.post(
                SERVICE_C_URL,
                json=validation_result,
                headers={"X-Request-ID": request_id},
            )

        log_event(
            "forwarded_to_service_c",
            request_id,
            status="success",
            extra={"service_c_status_code": service_c_response.status_code},
        )

        return JSONResponse(
            content={
                "request_id": request_id,
                "service": SERVICE_NAME,
                "status": "success",
                "service_c_response": service_c_response.json(),
            }
        )

    except Exception as e:
        log_event(
            "service_c_call_failed",
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
                "message": "Failed to reach Service C",
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
