import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from typing import Dict, Any
import asyncio
import aiohttp

from src.clients.http_client import ResilientHTTPClient, CircuitBreaker


@pytest.fixture
def mock_config() -> Dict[str, Any]:
    return {
        "http_client": {
            "rate_limit": {
                "max_retries": 3,
                "backoff_factor": 1.5,
                "retry_statuses": [429, 502, 503, 504],
                "retry_methods": ["GET", "POST"],
                "header_prefix": "X-RateLimit-",
            },
            "circuit_breaker": {"failure_threshold": 3, "recovery_timeout": 10},
            "timeouts": {"total": 5, "connect": 2},
            "validation": {
                "max_content_length": 1024,
                "allowed_content_types": ["application/json"],
            },
        }
    }


@pytest.mark.asyncio
async def test_circuit_breaker_state_transitions(mock_config):
    cb = CircuitBreaker(
        mock_config["http_client"]["circuit_breaker"]["failure_threshold"],
        mock_config["http_client"]["circuit_breaker"]["recovery_timeout"],
    )

    # Test closed state allows requests
    assert await cb.allow_request()

    # Test failure tracking and opening
    for _ in range(cb.failure_threshold):
        await cb.track_failure()
    assert cb.state == "open"
    assert not await cb.allow_request()

    # Test half-open transition after timeout
    await asyncio.sleep(cb.recovery_timeout + 0.1)
    assert cb.state == "half_open"
    assert await cb.allow_request()

    # Test successful reset
    await cb.record_success()
    assert cb.state == "closed"


@pytest.mark.asyncio
async def test_retry_mechanism(mock_config):
    client = ResilientHTTPClient(mock_config)
    mock_response = AsyncMock()
    mock_response.status = 503
    mock_response.headers = {"X-RateLimit-Reset": "1"}

    with patch("aiohttp.ClientSession.request") as mock_request:
        mock_request.side_effect = [mock_response, mock_response, AsyncMock(status=200)]

        async with client.session_context():
            response = await client.request("GET", "http://test.com")
            assert response.status == 200
            assert mock_request.call_count == 3


@pytest.mark.asyncio
async def test_request_validation(mock_config):
    client = ResilientHTTPClient(mock_config)

    with pytest.raises(ValueError):
        await client.request("PUT", "http://test.com")  # Invalid method

    with pytest.raises(ValueError):
        await client.request(
            "POST", "http://test.com", {"data": "x" * 2048}
        )  # Payload too big


@pytest.mark.asyncio
async def test_circuit_breaker_blocking(mock_config):
    client = ResilientHTTPClient(mock_config)
    client.circuit_breaker.state = "open"

    with pytest.raises(Exception) as exc_info:
        async with client.session_context():
            await client.request("GET", "http://test.com")
    assert "Circuit breaker blocked" in str(exc_info.value)


@pytest.mark.asyncio
async def test_timeout_configuration(mock_config):
    client = ResilientHTTPClient(mock_config)

    async with client.session_context():
        assert (
            client.session.timeout.total
            == mock_config["http_client"]["timeouts"]["total"]
        )
        assert (
            client.session.timeout.connect
            == mock_config["http_client"]["timeouts"]["connect"]
        )
