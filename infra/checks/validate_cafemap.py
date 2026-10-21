"""Protected local checks; unavailable live place data never becomes a PASS."""
import json
import sys
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

base, mode = sys.argv[1:3]
opener = build_opener(ProxyHandler({}))


def call(path, data=None):
    try:
        response = opener.open(Request(base + path, data=json.dumps(data).encode() if data is not None else None,
                                       headers={"Content-Type": "application/json"}), timeout=5)
    except HTTPError as error:
        response = error
    with response:
        return response.status, json.loads(response.read(131073))


if mode == "exercise":
    status, health = call('/health')
    checks = dict(health=status == 200 and health == dict(status='ok'))
    source_status, source = call('/api/map/source')
    status, result = call('/api/map/search', dict(latitude=37.5, longitude=127.0, query='', external_consent=False))
    checks['provider_unconfigured'] = source_status == 200 and source.get('status') == 'unconfigured' and source.get('external_requests') is False and status == 503 and result.get('error', {}).get('code') == 'PROVIDER_UNCONFIGURED'
    status, _ = call('/api/map/search', dict(latitude=91, longitude=127, query=''))
    checks['query_validation'] = status == 422
    status, value = call('/api/preferences', dict(radius_m=2000, internet_only=True))
    checks['preferences_write'] = status == 200 and value == dict(radius_m=2000, internet_only=True)
else:
    status, value = call('/api/preferences')
    checks = dict(persistent_preferences=status == 200 and value == dict(radius_m=2000, internet_only=True))
print(json.dumps(dict(checks=checks, not_run=['location_consent', 'map_search', 'nearby_recommendation'],
                      reason='Geoapify Free is selected but credentials/isolated integration are not configured; no live data or actual location permission was tested.')))
