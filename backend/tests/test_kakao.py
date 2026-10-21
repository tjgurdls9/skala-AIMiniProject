"""Synthetic credentials/MockTransport only: no Kakao account, quota or location use."""
import asyncio
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import httpx
from pydantic import ValidationError

from backend.contracts import DomainError
from backend.kakao import KakaoConfig, KakaoPlaces, KakaoQuery, load_config


KEYS = dict(javascript_key='j' * 32, rest_api_key='r' * 32, free_quota_confirmed=True, paid_api_disabled_confirmed=True)
RESULT = dict(meta=dict(is_end=True), documents=[dict(id='123', place_name='합성 카페', address_name='합성 주소',
              category_group_code='CE7', x='127.0', y='37.5')])


class KakaoChecks(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = self.root/'kakao.json'
        self.path.write_text(json.dumps(KEYS))
        self.path.chmod(0o600)
        self.calls = []
        def handle(request):
            self.calls.append(request)
            return httpx.Response(200, json=RESULT)
        self.transport = httpx.MockTransport(handle)

    def client(self, config=None, transport=None):
        return KakaoPlaces(config or load_config(self.path), self.root/'usage.sqlite3', transport or self.transport)

    def test_private_key_file_and_no_credential_repr(self):
        config = load_config(self.path)
        config.require_ready()
        self.assertNotIn(KEYS['rest_api_key'], repr(config))
        self.assertNotIn(KEYS['javascript_key'], repr(config))
        self.path.chmod(0o644)
        with self.assertRaises(DomainError): load_config(self.path)
        self.path.chmod(0o600)
        link = self.root/'link.json';link.symlink_to(self.path)
        with self.assertRaises(DomainError): load_config(link)
        self.path.write_text('{"javascript_key":"a","javascript_key":"b"}')
        with self.assertRaises(DomainError): load_config(self.path)

    def test_missing_eligibility_key_or_consent_never_calls_provider(self):
        for change in (dict(free_quota_confirmed=False), dict(free_quota_confirmed='false'), dict(paid_api_disabled_confirmed=False), dict(rest_api_key='')):
            with self.assertRaises(DomainError):
                asyncio.run(self.client(KakaoConfig(**(KEYS | change))).search(KakaoQuery(query='합성', external_consent=True)))
        with self.assertRaises(DomainError):
            asyncio.run(self.client().search(KakaoQuery(query='합성')))
        with self.assertRaises(DomainError):
            asyncio.run(self.client().search(KakaoQuery(latitude=37.5, external_consent=True)))
        self.assertFalse(self.calls)
        self.assertFalse((self.root/'usage.sqlite3').exists())
        with self.assertRaises(ValidationError): KakaoQuery(query='합성', external_consent='true')
        with self.assertRaises(ValidationError): KakaoQuery(latitude=float('nan'))

    def test_fixed_search_cafe_category_and_no_coordinate_storage(self):
        nearby = asyncio.run(self.client().search(KakaoQuery(latitude=37.5, longitude=127, external_consent=True)))
        named = asyncio.run(self.client().search(KakaoQuery(query='합성 지역 카페', external_consent=True)))
        request = self.calls[0]
        self.assertEqual(str(request.url).split('?')[0], 'https://dapi.kakao.com/v2/local/search/category.json')
        self.assertEqual(request.url.params['category_group_code'], 'CE7')
        self.assertEqual(request.url.params['x'], '127.0')
        self.assertEqual(request.headers['Authorization'], 'KakaoAK ' + KEYS['rest_api_key'])
        self.assertEqual(self.calls[1].url.path, '/v2/local/search/keyword.json')
        self.assertNotIn('x', self.calls[1].url.params)
        self.assertEqual(nearby['recommendation_basis'], 'distance')
        self.assertEqual(named['recommendation_basis'], 'keyword_relevance')
        self.assertEqual(nearby['places'][0]['study_suitability'], 'unknown')
        with sqlite3.connect(self.root/'usage.sqlite3') as db:
            self.assertEqual([row[1] for row in db.execute('PRAGMA table_info(kakao_usage)')], ['day','count','blocked'])
            self.assertEqual(db.execute('SELECT count FROM kakao_usage').fetchone()[0], 2)

    def test_quota_stops_across_clients_without_paid_retry(self):
        query = KakaoQuery(query='합성', external_consent=True)
        with patch('backend.kakao.DAILY_LIMIT', 1):
            asyncio.run(self.client().search(query))
            with self.assertRaises(DomainError): asyncio.run(self.client().search(query))
        self.assertEqual(len(self.calls), 1)
        errors = []
        def exhausted(request):
            errors.append(request)
            return httpx.Response(429, text='private upstream body must not escape')
        client = self.client(transport=httpx.MockTransport(exhausted))
        for _ in range(2):
            with self.assertRaises(DomainError) as failure: asyncio.run(client.search(query))
            self.assertNotIn('private upstream', failure.exception.message)
        self.assertEqual(len(errors), 1)

    def test_redirect_bad_or_oversized_payload_never_becomes_places(self):
        for response in (httpx.Response(302, headers={'Location':'https://untrusted.invalid'}),
                         httpx.Response(200, json=dict(meta=dict(is_end=True), documents=[RESULT['documents'][0] | dict(category_group_code='FD6')])),
                         httpx.Response(200, content=b'x' * 131073),
                         httpx.Response(200, json=dict(meta=dict(is_end=True), documents=[RESULT['documents'][0] | dict(x='nan')]))):
            seen = []
            def handle(request):
                seen.append(request)
                return response
            with self.assertRaises(DomainError):
                asyncio.run(self.client(transport=httpx.MockTransport(handle)).search(KakaoQuery(query='합성',external_consent=True)))
            self.assertEqual(len(seen), 1)
