"""FastAPI application entry point.

Creates the FastAPI app with a lifespan context manager, structured JSON
request logging middleware, global exception handlers, and a root
health-check endpoint.
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logger import setup_logging
from app.api.routes.health import router as health_router

setup_logging()

logger = logging.getLogger(__name__)


class ErrorResponse(BaseModel):
    """Standard error response body.

    Attributes:
        error: A short error description string.
        details: Optional validation error details.
    """

    error: str
    details: Optional[Any] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle.

    Args:
        app: The FastAPI application instance.

    Yields:
        None: Control is yielded to the application between startup and shutdown.
    """
    # Startup logic will go here (database connection, upload dir creation)
    yield
    # Shutdown logic will go here (close database connections)


app = FastAPI(lifespan=lifespan)

app.include_router(health_router)


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
    404: "not found",
    409: "file already exists",
    429: "too many requests",
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
