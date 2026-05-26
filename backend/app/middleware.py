import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cid = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        request.state.correlationId = cid
        request.state.correlation_id = cid

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = cid
        return response
