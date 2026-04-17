from time import perf_counter

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import init_db
from .routes import api_router
from .utils import configure_logging, get_logger


configure_logging()
init_db()
request_logger = get_logger("app.http")

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_http_requests(request, call_next):
    started_at = perf_counter()
    request_logger.info(
        "HTTP request start | method=%s | path=%s | client=%s",
        request.method,
        request.url.path,
        request.client.host if request.client else "unknown",
    )
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = round((perf_counter() - started_at) * 1000, 1)
        request_logger.exception(
            "HTTP request failed | method=%s | path=%s | elapsed_ms=%s",
            request.method,
            request.url.path,
            elapsed_ms,
        )
        raise
    elapsed_ms = round((perf_counter() - started_at) * 1000, 1)
    request_logger.info(
        "HTTP request end | method=%s | path=%s | status=%s | elapsed_ms=%s",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


app.include_router(api_router)
