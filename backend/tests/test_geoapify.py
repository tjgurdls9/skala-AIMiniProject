"""Geoapify adapter fixtures; no real API keys, coordinates or provider calls."""
import asyncio
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import httpx

from backend.contracts import DomainError
from backend.geoapify import GeoapifyConfig, GeoapifyPlaces, GeoapifyQuery, load_config
from backend.map_access import provider_json

KEY = 'synthetic_' + 'g' * 24
CAFE = dict(type='FeatureCollection', features=[dict(properties=dict(place_id='synthetic-cafe', name='합성 카페',
            formatted='합성 주소', categories=['catering','catering.cafe'], lat=37.5, lon=127.0))])
AREA = dict(type='FeatureCollection', features=[dict(properties=dict(formatted='합성 지역',country_code='kr',lat=37.5,lon=127.0))])


class GeoapifyChecks(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.path = self.root/'geoapify.json'
        self.path.write_text(json.dumps(dict(api_key=KEY,free_plan_confirmed=True)))
        self.path.chmod(0o600)
        self.calls = []
        def handle(request):
            self.calls.append(request)
            return httpx.Response(200,json=AREA if request.url.path=='/v1/geocode/search' else CAFE)
        self.transport = httpx.MockTransport(handle)

    def client(self, config=None, transport=None):
        return GeoapifyPlaces(config or load_config(self.path),self.root/'usage.sqlite3',transport or self.transport)

    def test_key_free_plan_consent_and_paths_fail_before_network(self):
        self.assertNotIn(KEY,repr(load_config(self.path)))
        q = GeoapifyQuery(latitude=37.5,longitude=127,external_consent=True)
        for config in (GeoapifyConfig(KEY,False),GeoapifyConfig(KEY,'false'),GeoapifyConfig('',True)):
            with self.assertRaises(DomainError): asyncio.run(self.client(config).search(q))
        with self.assertRaises(DomainError): asyncio.run(self.client().geocode('합성 지역'))
        with self.assertRaises(DomainError):
            asyncio.run(provider_json('geoapify','https://untrusted.invalid',{}, {},self.root/'usage.sqlite3',transport=self.transport))
        self.assertFalse(self.calls)
        self.assertFalse((self.root/'usage.sqlite3').exists())
        self.path.chmod(0o644)
        with self.assertRaises(DomainError): load_config(self.path)

    def test_geocoding_requires_selection_and_places_use_fixed_filter(self):
        areas = asyncio.run(self.client().geocode('합성 지역',True))
        self.assertTrue(areas['selection_required'])
        self.assertEqual(len(self.calls),1)  # Geocoding never silently chooses a cafe-search area.
        self.assertEqual(self.calls[0].url.params['filter'],'countrycode:kr')
        result = asyncio.run(self.client().search(GeoapifyQuery(latitude=37.5,longitude=127,query='합성',internet_only=True,external_consent=True)))
        request = self.calls[-1]
        self.assertEqual(str(request.url).split('?')[0],'https://api.geoapify.com/v2/places')
        self.assertEqual(request.url.params['categories'],'catering.cafe')
        self.assertEqual(request.url.params['conditions'],'internet_access')
        self.assertEqual(request.url.params['filter'],'circle:127.0,37.5,1500')
        self.assertEqual(request.url.params['limit'],'20')
        self.assertEqual(request.headers['x-api-key'],KEY)
        self.assertNotIn(KEY,str(request.url))
        self.assertEqual(result['places'][0]['study_suitability'],'unknown')
        self.assertIn('openstreetmap',result['attribution'])
        with sqlite3.connect(self.root/'usage.sqlite3') as db:
            self.assertEqual([r[1] for r in db.execute('PRAGMA table_info(geoapify_usage)')],['day','count','blocked'])
            self.assertEqual(db.execute('SELECT count FROM geoapify_usage').fetchone()[0],2)

    def test_shared_budget_redirect_payload_and_error_guards(self):
        q = GeoapifyQuery(latitude=37.5,longitude=127,external_consent=True)
        with patch('backend.geoapify.DAILY_LIMIT',1):
            asyncio.run(self.client().geocode('합성 지역',True))
            with self.assertRaises(DomainError): asyncio.run(self.client().search(q))
        self.assertEqual(len(self.calls),1)
        for response in (httpx.Response(302,headers={'Location':'https://untrusted.invalid'}),
                         httpx.Response(200,content=b'x'*131073),
                         httpx.Response(200,json=dict(features=[dict(properties=CAFE['features'][0]['properties']|dict(lon='nan'))]))):
            seen=[]
            def handle(request): seen.append(request);return response
            with self.assertRaises(DomainError): asyncio.run(self.client(transport=httpx.MockTransport(handle)).search(q))
            self.assertEqual(len(seen),1)
        errors=[]
        def exhausted(request): errors.append(request);return httpx.Response(429,text=KEY)
        for _ in range(2):
            with self.assertRaises(DomainError) as failure:
                asyncio.run(self.client(transport=httpx.MockTransport(exhausted)).search(q))
            self.assertNotIn(KEY,failure.exception.message)
        self.assertEqual(len(errors),1)
