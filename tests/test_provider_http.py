import asyncio
import unittest

from app.data.provider_http import (
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderRequestError,
    fetch_json_with_retries,
)


class FakeResponse:
    def __init__(self, status_code, data=None, headers=None):
        self.status_code = status_code
        self._data = data if data is not None else {}
        self.headers = headers or {}

    def json(self):
        return self._data


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    async def get(self, url, params=None, headers=None, timeout=15):
        self.calls += 1
        return self.responses.pop(0)


async def no_sleep(seconds):
    return None


class ProviderHttpTests(unittest.TestCase):
    def test_429_response_triggers_rate_limit_handling(self):
        client = FakeClient([FakeResponse(429)])

        with self.assertRaises(ProviderRateLimitError):
            asyncio.run(fetch_json_with_retries(client, "https://example.test", sleep=no_sleep))

        self.assertEqual(1, client.calls)

    def test_401_and_403_trigger_configuration_error_path(self):
        for status_code in (401, 403):
            with self.subTest(status_code=status_code):
                client = FakeClient([FakeResponse(status_code)])

                with self.assertRaises(ProviderConfigurationError):
                    asyncio.run(fetch_json_with_retries(client, "https://example.test", sleep=no_sleep))

                self.assertEqual(1, client.calls)

    def test_transient_500_retries_then_succeeds(self):
        client = FakeClient(
            [
                FakeResponse(500),
                FakeResponse(200, data={"ok": True}),
            ]
        )

        response = asyncio.run(
            fetch_json_with_retries(client, "https://example.test", max_retries=2, sleep=no_sleep)
        )

        self.assertEqual({"ok": True}, response.data)
        self.assertEqual(2, client.calls)

    def test_repeated_failure_raises_request_error_after_bounded_retries(self):
        client = FakeClient([FakeResponse(500), FakeResponse(502), FakeResponse(503)])

        with self.assertRaises(ProviderRequestError):
            asyncio.run(fetch_json_with_retries(client, "https://example.test", max_retries=2, sleep=no_sleep))

        self.assertEqual(3, client.calls)

    def test_quota_headers_are_captured(self):
        client = FakeClient(
            [
                FakeResponse(
                    200,
                    data=[],
                    headers={"X-Requests-Remaining": "42", "X-Requests-Used": "8"},
                )
            ]
        )

        response = asyncio.run(fetch_json_with_retries(client, "https://example.test", sleep=no_sleep))

        self.assertEqual({"x-requests-remaining": "42", "x-requests-used": "8"}, response.quota_headers)


if __name__ == "__main__":
    unittest.main()
