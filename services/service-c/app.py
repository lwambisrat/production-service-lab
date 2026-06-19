from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from datetime import datetime
import httpx
import json
import uuid

app = FastAPI(title="Service C - Inventory Processor")

SERVICE_NAME = "service-c"
SERVICE_A_CALLBACK_URL = "http://service-a.internal:3001/callback"


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
    return {
        "service": SERVICE_NAME,
        "status": "healthy"
    }


@app.post("/process")
async def process_inventory(request: Request):
    body = await request.json()
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    log_event(
        "inventory_processing_started",
        request_id=request_id,
        extra={"payload": body}
    )

    result = {
        "request_id": request_id,
        "inventory_status": "reserved",
        "message": "Inventory reserved successfully"
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            callback_response = await client.post(
                SERVICE_A_CALLBACK_URL,
                json=result,
                headers={"X-Request-ID": request_id}
            )

        log_event(
            "callback_sent_to_service_a",
            request_id=request_id,
            status="success",
            extra={"callback_status_code": callback_response.status_code}
        )

    except Exception as e:
        log_event(
            "callback_to_service_a_failed",
            request_id=request_id,
            status="error",
            extra={"error": str(e)}
        )

    return JSONResponse(content=result)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    log_event(
        "invalid_endpoint",
        request_id=request_id,
        status="error",
        extra={"path": str(request.url.path)}
    )

    return JSONResponse(
        status_code=404,
        content={
            "error": "Endpoint not found",
            "service": SERVICE_NAME,
            "path": str(request.url.path),
            "request_id": request_id
        }
    )
