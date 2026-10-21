"""Geoapify Free preparation; not connected to generated apps or the preview yet."""
from dataclasses import dataclass, field
import math
from pathlib import Path
import re

from pydantic import BaseModel, Field

from backend.contracts import ROOT, DomainError, require
from backend.map_access import private_settings, provider_json

KEY_FILE = ROOT / 'runtime-data/secrets/geoapify.json'
MAP_ORIGIN = 'http://localhost:8017'
DAILY_LIMIT = 200  # Conservative local search/geocoding cap; not the project-wide remaining credits.
ATTRIBUTION = dict(geoapify='https://www.geoapify.com/', openstreetmap='https://www.openstreetmap.org/copyright')


@dataclass(frozen=True)
class GeoapifyConfig:
    api_key: str = field(repr=False)
    free_plan_confirmed: bool

    def require_ready(self):
        require(self.free_plan_confirmed is True, 'RUNTIME_UNAVAILABLE', 'Geoapify 프로젝트의 Free 플랜을 먼저 확인하세요. 외부 호출하지 않았습니다.')
        require(isinstance(self.api_key, str) and re.fullmatch(r'[A-Za-z0-9_-]{16,128}', self.api_key),
                'RUNTIME_UNAVAILABLE', 'Geoapify API 키를 비공개 로컬 설정에 준비하세요.')


def load_config(path=KEY_FILE):
    return GeoapifyConfig(**private_settings(path, ('api_key',), ('free_plan_confirmed',)))


class GeoapifyQuery(BaseModel):
    model_config = {'extra': 'forbid'}
    query: str = Field(default='', max_length=120)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False, strict=True)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False, strict=True)
    radius_m: int = Field(default=1500, ge=100, le=5000, strict=True)
    internet_only: bool = Field(default=False, strict=True)
    external_consent: bool = Field(default=False, strict=True)


class GeoapifyPlaces:
    def __init__(self, config, usage_database, transport=None):
        self.config, self.path, self.transport = config, Path(usage_database), transport

    async def request(self, path, params, consent):
        self.config.require_ready()
        require(consent is True, 'FORBIDDEN', '검색어·선택 좌표를 Geoapify로 보내는 데 동의한 뒤 검색하세요.', 403)
        return await provider_json('geoapify', path, params, {'x-api-key': self.config.api_key}, self.path, DAILY_LIMIT, self.transport)

    @staticmethod
    def coordinates(properties):
        x, y = properties['lon'], properties['lat']
        require(type(x) in (int, float) and type(y) in (int, float) and math.isfinite(x) and math.isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90,
                'TEMPORARILY_UNAVAILABLE', 'Geoapify 좌표 형식이 맞지 않습니다.', 503)
        return dict(longitude=x, latitude=y)

    async def geocode(self, text, external_consent=False):
        require(isinstance(text, str) and 0 < len(text.strip()) <= 120, 'INVALID_COMMAND', '지역·주소 검색어가 필요합니다.', 422)
        data = await self.request('/v1/geocode/search', dict(text=text.strip(), lang='ko', limit=5, filter='countrycode:kr'), external_consent)
        try:
            require(isinstance(data['features'], list) and len(data['features']) <= 5, 'TEMPORARILY_UNAVAILABLE', 'Geoapify 지역 응답 형식이 맞지 않습니다.', 503)
            areas = []
            for feature in data['features']:
                p = feature['properties']
                require(p['country_code'] == 'kr' and isinstance(p['formatted'], str) and 0 < len(p['formatted']) <= 500,
                        'TEMPORARILY_UNAVAILABLE', 'Geoapify 지역 응답 형식이 맞지 않습니다.', 503)
                areas.append(dict(label=p['formatted'], **self.coordinates(p)))
            return dict(provider='geoapify', areas=areas, selection_required=True, attribution=ATTRIBUTION)
        except (TypeError, KeyError, ValueError):
            raise DomainError('TEMPORARILY_UNAVAILABLE', 'Geoapify 지역 응답을 확인할 수 없습니다.', 503) from None

    async def search(self, query):
        require(isinstance(query, GeoapifyQuery), 'INVALID_COMMAND', '검증된 카페 검색 요청이 필요합니다.', 422)
        params = dict(categories='catering.cafe', limit=20, lang='ko',
                      filter=f'circle:{query.longitude},{query.latitude},{query.radius_m}',
                      bias=f'proximity:{query.longitude},{query.latitude}')
        if query.query.strip():
            params['name'] = query.query.strip()
        if query.internet_only:
            params['conditions'] = 'internet_access'
        data = await self.request('/v2/places', params, query.external_consent)
        try:
            require(isinstance(data['features'], list) and len(data['features']) <= 20, 'TEMPORARILY_UNAVAILABLE', 'Geoapify 카페 응답 형식이 맞지 않습니다.', 503)
            places = []
            for feature in data['features']:
                p = feature['properties']
                require(isinstance(p['categories'], list) and 'catering.cafe' in p['categories'] and
                        isinstance(p['place_id'], str) and 0 < len(p['place_id']) <= 2048 and
                        isinstance(p['name'], str) and 0 < len(p['name']) <= 200 and
                        isinstance(p['formatted'], str) and len(p['formatted']) <= 500,
                        'TEMPORARILY_UNAVAILABLE', 'Geoapify 카페 응답 형식이 맞지 않습니다.', 503)
                places.append(dict(id=p['place_id'], name=p['name'], address=p['formatted'],
                                   **self.coordinates(p), study_suitability='unknown'))
            return dict(provider='geoapify', places=places, recommendation_basis='distance', attribution=ATTRIBUTION,
                        notice='OSM 기반 장소 정보이며 조용함·콘센트·장시간 이용 적합성은 미확인입니다. 인터넷 필터도 출처 정보이며 현장 보증이 아닙니다.')
        except (TypeError, KeyError, ValueError):
            raise DomainError('TEMPORARILY_UNAVAILABLE', 'Geoapify 카페 응답을 확인할 수 없습니다.', 503) from None
