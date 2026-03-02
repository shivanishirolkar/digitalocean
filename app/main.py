"""FastAPI application entry point.

Creates the FastAPI app with a lifespan context manager and a root
health-check endpoint. Routers and middleware will be added in later steps.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI


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

# TODO: Add routers (health, file_routes, download_routes)
# TODO: Add middleware (request logging)
# TODO: Add exception handlers


@app.get("/")
async def root() -> dict:
    """Root endpoint for basic liveness check.

    Returns:
        dict: A simple ok message indicating the server is running.
    """
    return {"message": "ok"}
