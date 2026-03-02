"""Integration tests for health and root endpoints."""

import pytest


@pytest.mark.asyncio
async def test_root_returns_200(client):
    """GET / returns 200 with {"message": "ok"}."""
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "ok"}


@pytest.mark.asyncio
async def test_health_returns_200(client):
    """GET /health returns 200 with {"status": "ok"}."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_metrics_returns_200(client):
    """GET /metrics returns 200 with integer metric values."""
    response = await client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    for key in ("total_files", "total_size_bytes", "total_signed_urls"):
        assert key in data
        assert isinstance(data[key], int)


@pytest.mark.asyncio
async def test_unknown_route_returns_404(client):
    """GET /unknown returns 404 with {"error": "not found"}."""
    response = await client.get("/unknown")
    assert response.status_code == 404
    assert response.json() == {"error": "not found"}
