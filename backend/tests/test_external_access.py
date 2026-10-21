"""The generic external-access broker: private settings files, a fixed approved origin and paths, a daily ledger, no secrets in errors.
No provider is named here; the grant comes from the caller (later: the user-approved plan's external access request)."""
import asyncio
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

import httpx

from backend.contracts import DomainError
from backend.external_access import ExternalGrant, external_json, private_settings, reserve_usage

KEY = 'synthetic_' + 'k' * 24
GRANT = ExternalGrant(name='data_source', origin='https://api.example.invalid', paths=frozenset({'/v1/items', '/v1/lookup'}), daily_limit=3)


class PrivateSettings(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = self.root / 'settings.json'

    def write(self, value, mode=0o600):
        self.path.write_text(value if isinstance(value, str) else json.dumps(value))
        self.path.chmod(mode)

    def code(self):
        with self.assertRaises(DomainError) as caught:
            private_settings(self.path, ('api_key',), ('confirmed',))
        return caught.exception.code

    def test_a_private_regular_file_with_exactly_the_expected_fields_is_read(self):
        self.write(dict(api_key=KEY, confirmed=True))
        self.assertEqual(private_settings(self.path, ('api_key',), ('confirmed',)), dict(api_key=KEY, confirmed=True))

    def test_loose_permissions_symlinks_missing_files_and_other_shapes_are_refused_without_leaking_the_key(self):
        self.write(dict(api_key=KEY, confirmed=True), mode=0o644)
        self.assertEqual(self.code(), 'FORBIDDEN')
        self.write(dict(api_key=KEY, confirmed=True))
        link = self.root / 'link.json'
        os.symlink(self.path, link)
        with self.assertRaises(DomainError):
            private_settings(link, ('api_key',), ('confirmed',))
        self.path.unlink()
        self.assertEqual(self.code(), 'RUNTIME_UNAVAILABLE')
        for bad in ('{"api_key": "x", "api_key": "y", "confirmed": true}', '{"api_key": 1, "confirmed": true}', '{"api_key": "x", "confirmed": "yes"}',
                    '{"api_key": "x"}', '{"api_key": "x", "confirmed": true, "extra": 1}', '[]', 'not json', '{"api_key": "' + 'x' * 5000 + '", "confirmed": true}'):
            self.write(bad)
            self.assertIn(self.code(), ('INVALID_COMMAND', 'RUNTIME_UNAVAILABLE'), bad[:30])
        self.write(dict(api_key=KEY, confirmed=True), mode=0o666)
        with self.assertRaises(DomainError) as caught:
            private_settings(self.path, ('api_key',), ('confirmed',))
        self.assertNotIn(KEY, caught.exception.message)


class Grant(unittest.TestCase):
    def test_a_grant_is_a_fixed_https_origin_and_absolute_paths_with_a_safe_name(self):
        for bad in (dict(origin='http://api.example.invalid'), dict(origin='https://user:pw@api.example.invalid'), dict(origin='https://api.example.invalid/x'),
                    dict(origin='https://api.example.invalid?x=1'), dict(paths=frozenset({'relative'})), dict(paths=frozenset()), dict(name='Bad Name'),
                    dict(name='a' * 40), dict(daily_limit=0), dict(daily_limit=100000)):
            with self.assertRaises(DomainError, msg=bad):
                ExternalGrant(**{**dict(name='data_source', origin='https://api.example.invalid', paths=frozenset({'/v1/items'}), daily_limit=3), **bad})


class Broker(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.db = self.root / 'usage.sqlite3'
        self.calls = []

    def transport(self, status=200, body=None, raw=None):
        def handle(request):
            self.calls.append(request)
            return httpx.Response(status, content=raw, json=None if raw is not None else (body if body is not None else {'ok': True}))
        return httpx.MockTransport(handle)

    def call(self, path='/v1/items', transport=None, params=None, headers=None):
        return asyncio.run(external_json(GRANT, path, params or {}, headers or {'x-api-key': KEY}, self.db, transport=transport or self.transport()))

    def test_only_the_approved_origin_and_paths_are_called_and_unapproved_ones_never_reach_the_network_or_the_ledger(self):
        for path in ('/v1/other', '/v1/items/../secret', 'https://untrusted.invalid/v1/items', '//untrusted.invalid/v1/items', ''):
            with self.assertRaises(DomainError):
                self.call(path)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.db.exists())
        self.assertEqual(self.call('/v1/items')['ok'], True)
        self.assertEqual(str(self.calls[0].url).split('?')[0], 'https://api.example.invalid/v1/items')
        self.assertEqual(self.calls[0].headers['x-api-key'], KEY)

    def test_the_daily_limit_blocks_further_calls_without_a_network_attempt(self):
        for _ in range(3):
            self.call()
        with self.assertRaises(DomainError) as caught:
            self.call()
        self.assertEqual(caught.exception.status, 429)
        self.assertEqual(len(self.calls), 3)

    def test_a_429_from_the_provider_blocks_the_rest_of_the_day_and_nothing_retries(self):
        with self.assertRaises(DomainError):
            self.call(transport=self.transport(status=429))
        calls_after_429 = len(self.calls)
        with self.assertRaises(DomainError):
            self.call()
        self.assertEqual(len(self.calls), calls_after_429)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT blocked FROM data_source_usage').fetchone()[0], 1)

    def test_errors_never_carry_the_key_or_the_raw_provider_message(self):
        with self.assertRaises(DomainError) as caught:
            self.call(transport=self.transport(status=500, body={'message': 'secret ' + KEY}))
        self.assertNotIn(KEY, caught.exception.message)
        self.assertNotIn('secret', caught.exception.message)

    def test_oversized_and_undecodable_responses_are_refused(self):
        with self.assertRaises(DomainError):
            self.call(transport=self.transport(raw=b'x' * 200000))
        with self.assertRaises(DomainError):
            self.call(transport=self.transport(raw=b'not json'))

    def test_redirects_are_not_followed(self):
        def handle(request):
            self.calls.append(request)
            return httpx.Response(302, headers={'location': 'https://untrusted.invalid/'})
        with self.assertRaises(DomainError):
            self.call(transport=httpx.MockTransport(handle))
        self.assertEqual(len(self.calls), 1)

    def test_usage_is_counted_per_grant_and_day(self):
        reserve_usage(self.db, 'data_source', 3)
        reserve_usage(self.db, 'other_source', 3)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT count FROM data_source_usage').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count FROM other_source_usage').fetchone()[0], 1)
        with self.assertRaises(DomainError):
            reserve_usage(self.db, 'bad name;drop', 3)


if __name__ == '__main__':
    unittest.main()
