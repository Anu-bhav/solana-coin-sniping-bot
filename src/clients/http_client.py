import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Literal, Optional, Dict, List
import aiohttp
from aiohttp import ClientSession, ClientResponse

logger = logging.getLogger(__name__)


class CircuitBreaker:
    def __init__(self, failure_threshold: int, recovery_timeout: int):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.state: Literal["closed", "open", "half-open"] = "closed"
        self.last_failure_time: float = 0.0

    async def track_failure(self):
        self.failures += 1
        if self.failures >= self.failure_threshold:
            self.state = "open"
            self.last_failure_time = asyncio.get_event_loop().time()
            logger.warning("Circuit breaker tripped to OPEN state")

    async def allow_request(self) -> bool:
        if self.state == "closed":
            return True

        if self.state == "open":
            elapsed = asyncio.get_event_loop().time() - self.last_failure_time
            if elapsed > self.recovery_timeout:
                self.state = "half-open"
                logger.info("Circuit breaker transitioning to HALF-OPEN")
                return True
            return False

        return True  # half-open allows limited attempts

    async def record_success(self):
        if self.state == "half-open":
            self.reset()
            logger.info("Circuit breaker reset to CLOSED state")

    def reset(self):
        self.state = "closed"
        self.failures = 0


class ResilientHTTPClient:
    def __init__(self, config: Dict):
        self.config = config["http_client"]
        self.circuit_breaker = CircuitBreaker(
            self.config["circuit_breaker"]["failure_threshold"],
            self.config["circuit_breaker"]["recovery_timeout"],
        )
        self.session: Optional[ClientSession] = None

    @asynccontextmanager
    async def session_context(self):
        timeout = aiohttp.ClientTimeout(
            total=self.config["timeouts"]["total"],
            connect=self.config["timeouts"]["connect"],
        )

        async with ClientSession(
            timeout=timeout, headers=self._get_auth_headers()
        ) as session:
            self.session = session
            try:
                yield
            finally:
                self.session = None

    def _get_auth_headers(self) -> Dict[str, str]:
        # API keys loaded from environment/config
        return {
            "Authorization": f"Bearer {os.getenv('API_KEY')}",
            "Content-Type": "application/json",
        }

    async def _validate_request(self, method: str, url: str, payload: Optional[Dict]):
        # Validate against config settings
        if method not in self.config["rate_limit"]["retry_methods"]:
            raise ValueError(f"Unsupported HTTP method: {method}")

        if len(str(payload)) > self.config["validation"]["max_content_length"]:
            raise ValueError("Payload exceeds maximum content length")

    async def _handle_rate_limits(self, response: ClientResponse):
        headers = response.headers
        prefix = self.config["rate_limit"]["header_prefix"]

        return {
            "limit": headers.get(f"{prefix}Limit"),
            "remaining": headers.get(f"{prefix}Remaining"),
            "reset": headers.get(f"{prefix}Reset"),
        }

    async def request(
        self, method: str, url: str, payload: Optional[Dict] = None, retries: int = 0
    ) -> ClientResponse:
        await self._validate_request(method, url, payload)

        if not await self.circuit_breaker.allow_request():
            raise Exception("Circuit breaker blocked request")

        try:
            async with self.session.request(method, url, json=payload) as response:
                if response.status in self.config["rate_limit"]["retry_statuses"]:
                    rate_info = await self._handle_rate_limits(response)
                    retry_after = rate_info.get("reset", 1)
                    await asyncio.sleep(retry_after)
                    return await self.request(method, url, payload, retries + 1)

                if response.status >= 500:
                    await self.circuit_breaker.track_failure()

                response.raise_for_status()
                await self.circuit_breaker.record_success()
                return response

        except Exception as e:
            if retries < self.config["rate_limit"]["max_retries"]:
                backoff = self.config["rate_limit"]["backoff_factor"] ** retries
                await asyncio.sleep(backoff)
                return await self.request(method, url, payload, retries + 1)
            raise
