"""FastAPI application entry point.

Creates the FastAPI app with a lifespan context manager, structured JSON
request logging middleware, global exception handlers, and a root
health-check endpoint.
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes.health import router as health_router
from app.api.routes.file_routes import router as file_router
from app.api.routes.download_routes import router as download_router
from app.config import get_settings
from app.core.logger import setup_logging
from app.database import Base, engine
from app.schemas.file_schema import ErrorResponse

# Import models so SQLAlchemy registers them before create_all
import app.models.file_model  # noqa: F401
import app.models.audit_model  # noqa: F401

setup_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle.

    On startup:
    - Retry database connection up to 5 times (2-second backoff).
    - Create all tables via ``Base.metadata.create_all``.
    - Ensure the upload directory exists.

    On shutdown:
    - Dispose of the database engine.

    Args:
        app: The FastAPI application instance.

    Yields:
        None: Control is yielded to the application between startup and shutdown.
    """
    # Database connection with retry
    for attempt in range(1, 6):
        try:
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("database connected", extra={"attempt": attempt})
            break
        except Exception:
            logger.warning(
                "database connection failed",
                extra={"attempt": attempt, "max_attempts": 5},
            )
            if attempt == 5:
                logger.error("database unreachable after 5 attempts")
                raise
            await asyncio.sleep(2)

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("database tables created")

    # Ensure upload directory exists
    settings = get_settings()
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    logger.info("upload directory ready", extra={"path": settings.UPLOAD_DIR})

    yield

    # Shutdown
    await engine.dispose()
    logger.info("database engine disposed")


app = FastAPI(lifespan=lifespan)

app.include_router(health_router)
app.include_router(file_router)
app.include_router(download_router)


# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every request as a single JSON line.

    Captures method, path, status_code, and latency (seconds, 3 decimal places)
    and logs at INFO level.

    Args:
        request: The incoming HTTP request.
        call_next: The next middleware or route handler.

    Returns:
        Response: The HTTP response from the downstream handler.
    """
    start = time.perf_counter()
    response = await call_next(request)
    latency = round(time.perf_counter() - start, 3)
    logger.info(
        "request",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "latency": latency,
        },
    )
    return response


# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------

_STATUS_MAP = {
    401: "unauthorized",
    403: "forbidden",
    404: "not found",
    410: "link expired",
    413: "file too large",
}


def _build_http_error_response(exc: HTTPException | StarletteHTTPException):
    """Build a JSONResponse for an HTTP exception.

    Maps known status codes to standard error messages. Falls back to
    the exception's detail for unmapped codes.

    Args:
        exc: The HTTP exception raised by a route or Starlette.

    Returns:
        JSONResponse: A JSON error response with the appropriate status code.
    """
    message = _STATUS_MAP.get(exc.status_code)
    if message:
        body = ErrorResponse(error=message)
    else:
        body = ErrorResponse(error=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=body.model_dump(exclude_none=True),
    )


@app.exception_handler(HTTPException)
async def fastapi_http_exception_handler(request: Request, exc: HTTPException):
    """Handle FastAPI HTTPException with standardised error bodies.

    Args:
        request: The incoming HTTP request.
        exc: The FastAPI HTTPException.

    Returns:
        JSONResponse: A JSON error response.
    """
    return _build_http_error_response(exc)


@app.exception_handler(StarletteHTTPException)
async def starlette_http_exception_handler(
    request: Request, exc: StarletteHTTPException
):
    """Handle Starlette HTTPException (e.g. 404 for unknown routes).

    Args:
        request: The incoming HTTP request.
        exc: The Starlette HTTPException.

    Returns:
        JSONResponse: A JSON error response.
    """
    return _build_http_error_response(exc)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
):
    """Handle request validation errors with cleaned error details.

    Strips the ``ctx`` key from each error dict, as it may contain raw
    Python exception objects that are not JSON serializable.

    Args:
        request: The incoming HTTP request.
        exc: The RequestValidationError raised by Pydantic.

    Returns:
        JSONResponse: A 422 JSON response with error details.
    """
    cleaned = []
    for err in exc.errors():
        clean_err = {k: v for k, v in err.items() if k != "ctx"}
        cleaned.append(clean_err)
    body = ErrorResponse(error="validation error", details=cleaned)
    return JSONResponse(
        status_code=422,
        content=body.model_dump(exclude_none=True),
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Handle unhandled exceptions with a 500 response.

    Logs the full traceback at ERROR level before returning a generic
    error message.

    Args:
        request: The incoming HTTP request.
        exc: The unhandled exception.

    Returns:
        JSONResponse: A 500 JSON response.
    """
    logger.exception(
        "unhandled exception",
        extra={"method": request.method, "path": request.url.path},
    )
    body = ErrorResponse(error="internal server error")
    return JSONResponse(
        status_code=500,
        content=body.model_dump(exclude_none=True),
    )


@app.get("/")
async def root() -> dict:
    """Root endpoint for basic liveness check.

    Returns:
        dict: A simple ok message indicating the server is running.
    """
    return {"message": "ok"}
