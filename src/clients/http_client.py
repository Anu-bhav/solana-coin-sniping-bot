import asyncio
import logging
from typing import Any, Dict, Optional

import aiohttp
from aiohttp import ClientError, ClientResponseError, ClientSession, ClientTimeout

# Assuming logger is configured elsewhere, e.g., in src.core.logger
logger = logging.getLogger(__name__)

DEFAULT_RATE_LIMIT_DELAY = 5.0  # Default seconds to wait on 429
DEFAULT_ENABLE_RATE_LIMIT = True


class HttpClientError(Exception):
    """Base exception for HttpClient errors."""

    def __init__(
        self, message: str, status: Optional[int] = None, url: Optional[str] = None
    ):
        self.status = status
        self.url = url
        super().__init__(f"HTTP Client Error: {message} [Status: {status}, URL: {url}]")


class HttpClient:
    """Asynchronous HTTP client with retry and rate limit handling."""

    def __init__(
        self,
        config: Dict[str, Any],
        session: Optional[ClientSession] = None,
        api_keys: Optional[Dict[str, str]] = None,
    ):
        """
        Initializes the HttpClient.

        Args:
            config: A dictionary containing configuration, expected to have
                    an 'http_client' key with settings like 'timeout',
                    'retry_policy', 'enable_rate_limit_handling',
                    'rate_limit_delay_seconds'.
            session: An optional existing aiohttp ClientSession.
            api_keys: Optional dictionary of API keys for convenience.
                      Keys are service names (e.g., 'helius'), values are keys.
                      These are NOT automatically added to requests; use them
                      when constructing headers for specific requests.
        """
        self._config = config.get("http_client", {})
        self._api_keys = api_keys or config.get(
            "api_keys", {}
        )  # Load from config if not passed
        self._session = session
        self._owns_session = session is None

        # --- Configuration Extraction ---
        self._timeout_seconds = float(self._config.get("timeout", 10.0))
        retry_policy = self._config.get("retry_policy", {})
        self._max_retries = int(
            retry_policy.get("max_attempts", 3)
        )  # Default to 3 retries
        self._retry_delay = float(
            retry_policy.get("backoff_factor", 0.5)
        )  # Simple delay for now
        self._retry_statuses = set(
            retry_policy.get("status_forcelist", [500, 502, 503, 504])
        )

        self._enable_rate_limit = self._config.get(
            "enable_rate_limit_handling", DEFAULT_ENABLE_RATE_LIMIT
        )
        self._rate_limit_delay = float(
            self._config.get("rate_limit_delay_seconds", DEFAULT_RATE_LIMIT_DELAY)
        )

        if "enable_rate_limit_handling" not in self._config:
            logger.warning(
                f"Config key 'http_client.enable_rate_limit_handling' not found. Defaulting to {DEFAULT_ENABLE_RATE_LIMIT}."
            )
        if "rate_limit_delay_seconds" not in self._config:
            logger.warning(
                f"Config key 'http_client.rate_limit_delay_seconds' not found. Defaulting to {DEFAULT_RATE_LIMIT_DELAY}s."
            )

        logger.info(
            f"HttpClient initialized. Timeout: {self._timeout_seconds}s, "
            f"Max Retries: {self._max_retries}, Retry Delay: {self._retry_delay}s, "
            f"Retry Statuses: {self._retry_statuses}, Rate Limit Handling: {self._enable_rate_limit}, "
            f"Rate Limit Delay: {self._rate_limit_delay}s"
        )

    async def _init_session(self) -> ClientSession:
        """Initializes the aiohttp ClientSession if not provided."""
        if self._session is None:
            logger.debug("Creating new aiohttp ClientSession.")
            # Consider adding connector settings from config (e.g., pool size)
            # connector = aiohttp.TCPConnector(limit=self._config.get('connection_pool_size', 100))
            # timeout = ClientTimeout(total=self._timeout_seconds)
            self._session = (
                aiohttp.ClientSession()
            )  # timeout=timeout, connector=connector
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        """Closes the aiohttp ClientSession if it was created by this instance."""
        if self._session and self._owns_session:
            logger.debug("Closing owned aiohttp ClientSession.")
            await self._session.close()
            self._session = None
        elif self._session and not self._owns_session:
            logger.debug("HttpClient using shared ClientSession, not closing it.")

    async def request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Performs an asynchronous HTTP request with retries and rate limit handling.

        Args:
            method: HTTP method (e.g., 'GET', 'POST').
            url: The URL to request.
            params: Dictionary of URL parameters.
            json_data: JSON payload for the request body.
            headers: Dictionary of request headers.
            **kwargs: Additional arguments passed to aiohttp's request method.

        Returns:
            The parsed JSON response.

        Raises:
            HttpClientError: If the request fails after retries or encounters
                             an unrecoverable error.
        """
        session = await self._init_session()
        attempt = 0
        last_exception = None

        # Prepare timeout object
        request_timeout = ClientTimeout(total=self._timeout_seconds)

        while attempt <= self._max_retries:
            attempt += 1
            log_prefix = f"Attempt {attempt}/{self._max_retries + 1}"
            logger.debug(f"{log_prefix} - Requesting {method} {url}")
            if params:
                logger.debug(f"{log_prefix} - Params: {params}")
            if json_data:
                logger.debug(
                    f"{log_prefix} - JSON Body: {json_data}"
                )  # Consider logging sensitivity
            if headers:
                # Avoid logging sensitive headers like Authorization
                safe_headers = {
                    k: v for k, v in headers.items() if k.lower() != "authorization"
                }
                logger.debug(f"{log_prefix} - Headers: {safe_headers}")

            try:
                async with session.request(
                    method,
                    url,
                    params=params,
                    json=json_data,
                    headers=headers,
                    timeout=request_timeout,
                    **kwargs,
                ) as response:
                    logger.debug(
                        f"{log_prefix} - Response Status: {response.status} for {url}"
                    )

                    # Handle successful response
                    if 200 <= response.status < 300:
                        try:
                            # Try to parse JSON, return raw text if fails or content type isn't JSON
                            if "application/json" in response.content_type:
                                return await response.json()
                            else:
                                return await response.text()
                        except (
                            ValueError,
                            ClientError,
                        ) as e:  # Includes JSONDecodeError
                            logger.error(
                                f"{log_prefix} - Failed to parse JSON response from {url}: {e}"
                            )
                            raise HttpClientError(
                                f"Failed to parse JSON response: {e}",
                                status=response.status,
                                url=url,
                            ) from e

                    # Handle Rate Limiting (429)
                    elif response.status == 429 and self._enable_rate_limit:
                        if attempt > self._max_retries:
                            logger.error(
                                f"{log_prefix} - Rate limit hit on final attempt for {url}. Giving up."
                            )
                            raise HttpClientError(
                                "Rate limit exceeded after max retries",
                                status=response.status,
                                url=url,
                            )

                        delay = self._rate_limit_delay * (
                            2 ** (attempt - 1)
                        )  # Exponential backoff for rate limits
                        logger.warning(
                            f"{log_prefix} - Rate limit hit (429) for {url}. Waiting {delay:.2f}s before retry {attempt + 1}."
                        )
                        await asyncio.sleep(delay)
                        last_exception = ClientResponseError(
                            response.request_info,
                            response.history,
                            status=response.status,
                            message="Rate Limited",
                            headers=response.headers,
                        )
                        continue  # Go to next attempt

                    # Handle Retriable Server Errors (e.g., 5xx)
                    elif response.status in self._retry_statuses:
                        if attempt > self._max_retries:
                            logger.error(
                                f"{log_prefix} - Retriable error {response.status} on final attempt for {url}. Giving up."
                            )
                            response.raise_for_status()  # Raise standard ClientResponseError

                        delay = self._retry_delay * (
                            2 ** (attempt - 1)
                        )  # Exponential backoff
                        logger.warning(
                            f"{log_prefix} - Received retriable status {response.status} for {url}. Retrying in {delay:.2f}s..."
                        )
                        await asyncio.sleep(delay)
                        last_exception = ClientResponseError(
                            response.request_info,
                            response.history,
                            status=response.status,
                            message="Retriable Server Error",
                            headers=response.headers,
                        )
                        continue  # Go to next attempt

                    # Handle Non-Retriable Client/Server Errors (4xx, other 5xx)
                    else:
                        error_text = await response.text()
                        logger.error(
                            f"{log_prefix} - HTTP Error {response.status} for {url}. Response: {error_text[:500]}"
                        )  # Log snippet
                        # Raise specific error to be caught outside or handled
                        response.raise_for_status()  # Raises ClientResponseError for 4xx/5xx

            except ClientResponseError as e:
                # This catches the raise_for_status() for non-retriable errors
                logger.error(
                    f"{log_prefix} - Unrecoverable HTTP Error: {e.status} {e.message} for {url}"
                )
                last_exception = e
                raise HttpClientError(
                    f"Unrecoverable HTTP Error: {e.message}", status=e.status, url=url
                ) from e

            except asyncio.TimeoutError as e:
                logger.warning(
                    f"{log_prefix} - Request timed out ({self._timeout_seconds}s) for {url}."
                )
                last_exception = e
                if attempt > self._max_retries:
                    logger.error(
                        f"{log_prefix} - Request timed out on final attempt for {url}. Giving up."
                    )
                    raise HttpClientError(
                        f"Request timed out after {self._max_retries + 1} attempts",
                        url=url,
                    ) from e
                # Apply retry delay for timeouts as well? Maybe shorter? Using standard retry delay for now.
                delay = self._retry_delay * (2 ** (attempt - 1))
                logger.warning(
                    f"{log_prefix} - Retrying timed out request in {delay:.2f}s..."
                )
                await asyncio.sleep(delay)
                continue  # Go to next attempt

            except (
                ClientError
            ) as e:  # Catch other connection errors (DNS, connection refused, etc.)
                logger.warning(
                    f"{log_prefix} - Connection Error for {url}: {e.__class__.__name__} - {e}"
                )
                last_exception = e
                if attempt > self._max_retries:
                    logger.error(
                        f"{log_prefix} - Connection error on final attempt for {url}. Giving up."
                    )
                    raise HttpClientError(
                        f"Connection error after {self._max_retries + 1} attempts: {e}",
                        url=url,
                    ) from e

                delay = self._retry_delay * (2 ** (attempt - 1))
                logger.warning(
                    f"{log_prefix} - Retrying connection error in {delay:.2f}s..."
                )
                await asyncio.sleep(delay)
                continue  # Go to next attempt

            except Exception as e:  # Catch unexpected errors
                logger.exception(
                    f"{log_prefix} - An unexpected error occurred during request to {url}: {e}",
                    exc_info=True,
                )
                raise HttpClientError(
                    f"An unexpected error occurred: {e}", url=url
                ) from e

        # Should not be reached if loop completes normally, but as a safeguard:
        logger.error(
            f"Request failed for {url} after {self._max_retries + 1} attempts. Last known error: {last_exception}"
        )
        raise HttpClientError(
            f"Request failed after {self._max_retries + 1} attempts. Last error: {type(last_exception).__name__}",
            status=getattr(last_exception, "status", None),
            url=url,
        ) from last_exception

    async def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> Any:
        """Performs a GET request."""
        return await self.request("GET", url, params=params, headers=headers, **kwargs)

    async def post(
        self,
        url: str,
        json_data: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> Any:
        """Performs a POST request."""
        return await self.request(
            "POST", url, params=params, json_data=json_data, headers=headers, **kwargs
        )

    # --- Context Manager ---
    async def __aenter__(self):
        await self._init_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
