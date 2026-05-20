import asyncio
import logging
import os
import unittest
from unittest.mock import patch

from app.data.fetcher import OddsApiProvider


class OddsApiProviderConfigTests(unittest.TestCase):
    def test_missing_keys_returns_unavailable_without_network_request(self):
        with patch.dict(os.environ, {"ODDS_API_KEY": "", "ODDS_API_BACKUP_KEYS": ""}, clear=False):
            provider = OddsApiProvider()

        with patch("app.data.fetcher.httpx.AsyncClient") as client_cls:
            with self.assertLogs("app.data.fetcher", level=logging.ERROR) as logs:
                matches = asyncio.run(provider.get_upcoming_matches())

        self.assertEqual([], matches)
        client_cls.assert_not_called()
        self.assertIn("ODDS_API_KEY is not configured", "\n".join(logs.output))

    def test_primary_key_comes_only_from_environment(self):
        with patch.dict(os.environ, {"ODDS_API_KEY": "primary-key", "ODDS_API_BACKUP_KEYS": ""}, clear=False):
            provider = OddsApiProvider()

        self.assertEqual(["primary-key"], provider.api_keys)
        self.assertEqual("primary-key", provider.api_key)

    def test_backup_keys_come_only_from_environment(self):
        with patch.dict(
            os.environ,
            {"ODDS_API_KEY": "primary-key", "ODDS_API_BACKUP_KEYS": "backup-one, backup-two ,, "},
            clear=False,
        ):
            provider = OddsApiProvider()

        self.assertEqual(["primary-key", "backup-one", "backup-two"], provider.api_keys)
        self.assertEqual("primary-key", provider.api_key)
        self.assertTrue(provider._rotate_key())
        self.assertEqual("backup-one", provider.api_key)


if __name__ == "__main__":
    unittest.main()
