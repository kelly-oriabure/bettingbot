"""HTTP helpers for provider calls with bounded retry and quota handling."""

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Optional


QUOTA_HEADERS = (
    "x-requests-remaining",
    "x-requests-used",
    "x-requests-last",
    "x-ratelimit-remaining",
    "x-ratelimit-limit",
)


class ProviderError(RuntimeError):
    """Base class for provider HTTP errors."""


class ProviderConfigurationError(ProviderError):
    """Raised when provider credentials/configuration are invalid."""


class ProviderRateLimitError(ProviderError):
    """Raised when a provider returns a rate-limit response."""


class ProviderRequestError(ProviderError):
    """Raised when a provider request repeatedly fails."""


@dataclass
class ProviderResponse:
    data: Any
    status_code: int
    quota_headers: Dict[str, str]


def extract_quota_headers(headers: Dict[str, Any]) -> Dict[str, str]:
    """Return quota/rate-limit headers using lowercase keys."""
    lowered = {str(key).lower(): str(value) for key, value in headers.items()}
    return {key: lowered[key] for key in QUOTA_HEADERS if key in lowered}


async def fetch_json_with_retries(
    client,
    url: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 15,
    max_retries: int = 2,
    backoff_seconds: float = 0.25,
    sleep=asyncio.sleep,
) -> ProviderResponse:
    """Fetch JSON with bounded retry/backoff for transient provider errors."""
    attempts = 0
    last_status = None
    while attempts <= max_retries:
        response = await client.get(url, params=params, headers=headers, timeout=timeout)
        status_code = response.status_code
        last_status = status_code
        quota_headers = extract_quota_headers(response.headers)

        if status_code == 200:
            return ProviderResponse(response.json(), status_code, quota_headers)
        if status_code in (401, 403):
            raise ProviderConfigurationError(f"Provider configuration error: HTTP {status_code}")
        if status_code == 429:
            raise ProviderRateLimitError("Provider rate limit reached: HTTP 429")
        if 500 <= status_code < 600 and attempts < max_retries:
            attempts += 1
            await sleep(backoff_seconds * attempts)
            continue

        raise ProviderRequestError(f"Provider request failed: HTTP {status_code}")

    raise ProviderRequestError(f"Provider request failed after retries: HTTP {last_status}")
