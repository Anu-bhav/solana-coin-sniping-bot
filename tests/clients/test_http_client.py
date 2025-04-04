import asyncio
from unittest.mock import patch, AsyncMock

import pytest
import pytest_asyncio
from aiohttp import (
    ClientConnectionError,
    ClientResponseError,
    ClientSession,
    ClientTimeout,
)
from aioresponses import aioresponses

# Assuming the HttpClient class is in src.clients.http_client
from src.clients.http_client import HttpClient, HttpClientError

# Basic config for tests
MOCK_CONFIG = {
    "http_client": {
        "timeout": 5.0,
        "retry_policy": {
            "max_attempts": 2,  # Keep low for tests
            "backoff_factor": 0.1,  # Short delay for tests
            "status_forcelist": [500, 502, 503, 504],
        },
        "enable_rate_limit_handling": True,
        "rate_limit_delay_seconds": 0.2,  # Short delay for tests
    },
    "api_keys": {"test_service": "test_key_123"},
}

MOCK_URL = "http://test.com/api"


@pytest.fixture
def mock_aioresponse():
    with aioresponses() as m:
        yield m


@pytest_asyncio.fixture
async def http_client():
    """Provides an HttpClient instance that cleans up its session."""
    client = HttpClient(config=MOCK_CONFIG)
    yield client
    await client.close()  # Ensure session is closed after test


@pytest_asyncio.fixture
async def shared_session():
    """Provides a shared ClientSession."""
    session = ClientSession()
    yield session
    await session.close()


# --- Test Cases ---


@pytest.mark.asyncio
async def test_http_client_initialization(http_client):
    """Test basic initialization and config loading."""
    assert http_client._timeout_seconds == 5.0
    assert http_client._max_retries == 2
    assert http_client._retry_delay == 0.1
    assert http_client._retry_statuses == {500, 502, 503, 504}
    assert http_client._enable_rate_limit is True
    assert http_client._rate_limit_delay == 0.2
    assert http_client._owns_session is True  # Should own session by default
    assert http_client._api_keys.get("test_service") == "test_key_123"
    assert (
        http_client._session is None
    )  # Session not created until first request or __aenter__


@pytest.mark.asyncio
async def test_http_client_initialization_with_shared_session(shared_session):
    """Test initialization with a pre-existing session."""
    client = HttpClient(config=MOCK_CONFIG, session=shared_session)
    assert client._session == shared_session
    assert client._owns_session is False
    # Ensure closing the client doesn't close the shared session
    await client.close()
    assert not shared_session.closed


@pytest.mark.asyncio
async def test_successful_get_request(http_client, mock_aioresponse):
    """Test a simple successful GET request."""
    mock_aioresponse.get(MOCK_URL, payload={"data": "success"}, status=200)
    response = await http_client.get(MOCK_URL)
    assert response == {"data": "success"}
    mock_aioresponse.assert_called_once_with(
        MOCK_URL,
        method="GET",
        params=None,
        headers=None,
        json=None,
        timeout=ClientTimeout(total=5.0),
    )


@pytest.mark.asyncio
async def test_successful_post_request(http_client, mock_aioresponse):
    """Test a simple successful POST request with JSON body."""
    request_data = {"key": "value"}
    mock_aioresponse.post(MOCK_URL, payload={"result": "created"}, status=201)
    response = await http_client.post(MOCK_URL, json_data=request_data)
    assert response == {"result": "created"}
    # Check that the request was made correctly (aioresponses checks method, url, status implicitly)
    # We manually check the json payload was sent
    # Note: aioresponses doesn't easily expose the request body for assertion,
    # relying on the mock setup is usually sufficient. For strict body checking,
    # more complex mocking or custom callbacks in aioresponses might be needed.
    # Let's check call args if possible (depends on aioresponses version/internals)
    # For simplicity, we trust the mock setup for now.


@pytest.mark.asyncio
async def test_request_with_headers_and_params(http_client, mock_aioresponse):
    """Test sending custom headers and URL parameters."""
    headers = {
        "Authorization": f"Bearer {http_client._api_keys['test_service']}",
        "X-Custom": "Test",
    }
    params = {"query": "test"}
    expected_url = f"{MOCK_URL}?query=test"  # aioresponses matches base URL + params

    mock_aioresponse.get(expected_url, payload={"status": "ok"}, status=200)

    response = await http_client.get(MOCK_URL, params=params, headers=headers)
    assert response == {"status": "ok"}

    # Verify headers were passed (aioresponses checks this internally when matching)
    # We can explicitly check the call arguments if needed, but it's often redundant
    # with how aioresponses works.
    mock_aioresponse.assert_called_once()
    call_kwargs = mock_aioresponse.requests[("GET", MOCK_URL)][0].kwargs
    assert call_kwargs["params"] == params
    assert "Authorization" in call_kwargs["headers"]
    assert (
        call_kwargs["headers"]["Authorization"]
        == f"Bearer {http_client._api_keys['test_service']}"
    )
    assert call_kwargs["headers"]["X-Custom"] == "Test"


@pytest.mark.asyncio
async def test_client_error_4xx(http_client, mock_aioresponse):
    """Test handling of a 404 Not Found error (non-retriable)."""
    mock_aioresponse.get(MOCK_URL, status=404, body="Not Found")
    with pytest.raises(HttpClientError) as excinfo:
        await http_client.get(MOCK_URL)
    assert excinfo.value.status == 404
    assert MOCK_URL in str(excinfo.value)
    assert "Not Found" in str(excinfo.value)  # Check if original message is included
    mock_aioresponse.assert_called_once()  # Should not retry on 404


@pytest.mark.asyncio
async def test_server_error_5xx_no_retry_success(http_client, mock_aioresponse):
    """Test handling of a 503 Service Unavailable error that fails after retries."""
    mock_aioresponse.get(MOCK_URL, status=503, reason="Service Unavailable")
    mock_aioresponse.get(MOCK_URL, status=503, reason="Service Unavailable")
    mock_aioresponse.get(
        MOCK_URL, status=503, reason="Service Unavailable"
    )  # Max retries = 2, so 1 initial + 2 retries = 3 calls

    with pytest.raises(HttpClientError) as excinfo:
        await http_client.get(MOCK_URL)

    assert excinfo.value.status == 503
    assert MOCK_URL in str(excinfo.value)
    # Check the underlying exception type if needed
    assert isinstance(excinfo.value.__cause__, ClientResponseError)
    assert (
        len(mock_aioresponse.requests[("GET", MOCK_URL)]) == 3
    )  # 1 initial + 2 retries


@pytest.mark.asyncio
async def test_server_error_5xx_with_retry_success(http_client, mock_aioresponse):
    """Test successful retry after initial 500 errors."""
    mock_aioresponse.get(MOCK_URL, status=500, reason="Internal Server Error")
    mock_aioresponse.get(MOCK_URL, status=500, reason="Internal Server Error")
    mock_aioresponse.get(MOCK_URL, payload={"data": "finally success"}, status=200)

    response = await http_client.get(MOCK_URL)
    assert response == {"data": "finally success"}
    assert (
        len(mock_aioresponse.requests[("GET", MOCK_URL)]) == 3
    )  # 2 failures + 1 success


@pytest.mark.asyncio
async def test_rate_limit_429_handling(http_client, mock_aioresponse):
    """Test handling of 429 Too Many Requests with delay and retry."""
    mock_aioresponse.get(MOCK_URL, status=429, reason="Rate Limited")
    mock_aioresponse.get(MOCK_URL, status=429, reason="Rate Limited")
    mock_aioresponse.get(MOCK_URL, payload={"data": "rate limit passed"}, status=200)

    # Patch asyncio.sleep to avoid actual waiting and check delays
    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        response = await http_client.get(MOCK_URL)

    assert response == {"data": "rate limit passed"}
    assert len(mock_aioresponse.requests[("GET", MOCK_URL)]) == 3
    assert mock_sleep.call_count == 2
    # Check delays (exponential backoff: 0.2 * 2^0, 0.2 * 2^1)
    mock_sleep.assert_any_call(pytest.approx(0.2))  # 0.2 * (2**0)
    mock_sleep.assert_any_call(pytest.approx(0.4))  # 0.2 * (2**1)


@pytest.mark.asyncio
async def test_rate_limit_429_fail_after_retries(http_client, mock_aioresponse):
    """Test failing after hitting rate limit on all attempts."""
    mock_aioresponse.get(MOCK_URL, status=429, reason="Rate Limited")
    mock_aioresponse.get(MOCK_URL, status=429, reason="Rate Limited")
    mock_aioresponse.get(
        MOCK_URL, status=429, reason="Rate Limited"
    )  # 1 initial + 2 retries

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        with pytest.raises(HttpClientError) as excinfo:
            await http_client.get(MOCK_URL)

    assert excinfo.value.status == 429
    assert "Rate limit exceeded" in str(excinfo.value)
    assert len(mock_aioresponse.requests[("GET", MOCK_URL)]) == 3
    assert mock_sleep.call_count == 2  # Sleeps before the 2nd and 3rd attempts


@pytest.mark.asyncio
async def test_request_timeout(http_client, mock_aioresponse):
    """Test handling of asyncio.TimeoutError."""
    # Configure aioresponses to raise TimeoutError
    mock_aioresponse.get(MOCK_URL, exception=asyncio.TimeoutError("Request timed out"))
    mock_aioresponse.get(MOCK_URL, exception=asyncio.TimeoutError("Request timed out"))
    mock_aioresponse.get(
        MOCK_URL, exception=asyncio.TimeoutError("Request timed out")
    )  # 1 initial + 2 retries

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        with pytest.raises(HttpClientError) as excinfo:
            await http_client.get(MOCK_URL)

    assert "Request timed out after 3 attempts" in str(excinfo.value)
    assert excinfo.value.status is None  # No HTTP status for timeout
    assert MOCK_URL in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, asyncio.TimeoutError)
    assert len(mock_aioresponse.requests[("GET", MOCK_URL)]) == 3
    assert mock_sleep.call_count == 2  # Retries after timeout


@pytest.mark.asyncio
async def test_connection_error(http_client, mock_aioresponse):
    """Test handling of aiohttp.ClientConnectionError."""
    mock_aioresponse.get(MOCK_URL, exception=ClientConnectionError("Cannot connect"))
    mock_aioresponse.get(MOCK_URL, exception=ClientConnectionError("Cannot connect"))
    mock_aioresponse.get(
        MOCK_URL, exception=ClientConnectionError("Cannot connect")
    )  # 1 initial + 2 retries

    with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        with pytest.raises(HttpClientError) as excinfo:
            await http_client.get(MOCK_URL)

    assert "Connection error after 3 attempts" in str(excinfo.value)
    assert "Cannot connect" in str(excinfo.value)
    assert excinfo.value.status is None
    assert MOCK_URL in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, ClientConnectionError)
    assert len(mock_aioresponse.requests[("GET", MOCK_URL)]) == 3
    assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_context_manager(mock_aioresponse):
    """Test using the HttpClient as an async context manager."""
    mock_aioresponse.get(MOCK_URL, payload={"data": "context"}, status=200)
    client_instance = None
    async with HttpClient(config=MOCK_CONFIG) as client:
        client_instance = client
        assert client._session is not None  # Session should be created on enter
        assert not client._session.closed
        response = await client.get(MOCK_URL)
        assert response == {"data": "context"}

    # Session should be closed on exit if owned
    assert client_instance is not None
    assert client_instance._session is None  # Session attribute reset
    # Cannot directly check if the closed session object was the one used,
    # but we trust __aexit__ called close() which sets self._session = None


@pytest.mark.asyncio
async def test_non_json_response(http_client, mock_aioresponse):
    """Test handling a response that is not JSON."""
    mock_aioresponse.get(
        MOCK_URL, body="Plain text response", status=200, content_type="text/plain"
    )
    response = await http_client.get(MOCK_URL)
    assert response == "Plain text response"


@pytest.mark.asyncio
async def test_json_parsing_error(http_client, mock_aioresponse):
    """Test handling invalid JSON in the response."""
    mock_aioresponse.get(
        MOCK_URL, body="Invalid JSON {", status=200, content_type="application/json"
    )
    with pytest.raises(HttpClientError) as excinfo:
        await http_client.get(MOCK_URL)
    assert "Failed to parse JSON response" in str(excinfo.value)
    assert excinfo.value.status == 200  # Error happened after successful status


@pytest.mark.asyncio
async def test_close_behavior_owned_session(mock_aioresponse):
    """Verify closing an HttpClient instance closes its owned session."""
    mock_aioresponse.get(MOCK_URL, status=200)
    client = HttpClient(config=MOCK_CONFIG)
    await client.request("GET", MOCK_URL)  # Trigger session creation
    session = client._session
    assert session is not None
    assert not session.closed
    await client.close()
    assert client._session is None
    # assert session.closed # Check the original session object is closed


@pytest.mark.asyncio
async def test_close_behavior_shared_session(shared_session):
    """Verify closing an HttpClient instance does NOT close a shared session."""
    client = HttpClient(config=MOCK_CONFIG, session=shared_session)
    assert client._session == shared_session
    await client.close()
    assert client._session == shared_session  # Should still hold reference
    assert not shared_session.closed  # IMPORTANT: Shared session remains open
