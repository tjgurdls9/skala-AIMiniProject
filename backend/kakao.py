"""Trusted Kakao adapter; credentials never enter model packets or generated containers."""
from dataclasses import dataclass, field
import math
from pathlib import Path
import re

from pydantic import BaseModel, Field

from backend.contracts import ROOT, DomainError, require
from backend.map_access import private_settings, provider_json

KEY_FILE = ROOT / 'runtime-data/secrets/kakao.json'
MAP_ORIGIN = 'http://localhost:8017'
DAILY_LIMIT = 200  # Local test budget, not a statement about the account's remaining quota.


@dataclass(frozen=True)
class KakaoConfig:
    javascript_key: str = field(repr=False)
    rest_api_key: str = field(repr=False)
    free_quota_confirmed: bool
    paid_api_disabled_confirmed: bool

    def require_ready(self):
        require(self.free_quota_confirmed is True and self.paid_api_disabled_confirmed is True, 'RUNTIME_UNAVAILABLE',
                '카카오맵 무료 쿼터 배지와 유료 API 비활성을 먼저 확인하세요. 외부 호출하지 않았습니다.')
        require(all(isinstance(key, str) and re.fullmatch(r'[A-Za-z0-9_-]{16,128}', key) for key in (self.javascript_key, self.rest_api_key)),
                'RUNTIME_UNAVAILABLE', '같은 카카오 앱의 JavaScript 키와 REST API 키를 로컬 설정에 준비하세요.')


def load_config(path=KEY_FILE):
    return KakaoConfig(**private_settings(path, ('javascript_key', 'rest_api_key'), ('free_quota_confirmed', 'paid_api_disabled_confirmed')))


class KakaoQuery(BaseModel):
    model_config = {'extra': 'forbid'}
    query: str = Field(default='', max_length=120)
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False, strict=True)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False, strict=True)
    radius_m: int = Field(default=1500, ge=100, le=5000, strict=True)
    external_consent: bool = Field(default=False, strict=True)


class KakaoPlaces:
    def __init__(self, config, usage_database, transport=None):
        self.config, self.path, self.transport = config, Path(usage_database), transport

    async def search(self, query):
        require(isinstance(query, KakaoQuery), 'INVALID_COMMAND', '검증된 카페 검색 요청이 필요합니다.', 422)
        self.config.require_ready()
        require(query.external_consent, 'FORBIDDEN', '검색어·선택 좌표를 카카오로 보내는 데 동의한 뒤 검색하세요.', 403)
        located = query.latitude is not None and query.longitude is not None
        require((query.latitude is None) == (query.longitude is None) and (located or query.query.strip()),
                'INVALID_COMMAND', '지역·카페 검색어 또는 위도·경도 쌍이 필요합니다.', 422)
        params = dict(category_group_code='CE7', size=15, page=1)
        if query.query.strip():
            params['query'] = query.query.strip()
        if located:
            params.update(x=query.longitude, y=query.latitude, radius=query.radius_m, sort='distance')
        path = '/v2/local/search/' + ('keyword.json' if 'query' in params else 'category.json')
        data = await provider_json('kakao', path, params, {'Authorization': 'KakaoAK ' + self.config.rest_api_key},
                                   self.path, DAILY_LIMIT, self.transport)
        try:
            documents = data['documents']
            require(type(data['meta']['is_end']) is bool and isinstance(documents, list) and len(documents) <= 15,
                    'TEMPORARILY_UNAVAILABLE', '카카오 응답 형식이 맞지 않습니다.', 503)
            places = []
            for row in documents:
                require(row['category_group_code'] == 'CE7' and isinstance(row['id'], str) and re.fullmatch(r'[0-9]{1,64}', row['id']) and
                        all(isinstance(row[k], str) and 0 < len(row[k]) <= limit for k, limit in (('place_name', 200), ('address_name', 500))),
                        'TEMPORARILY_UNAVAILABLE', '카카오 카페 응답 형식이 맞지 않습니다.', 503)
                x, y = float(row['x']), float(row['y'])
                require(math.isfinite(x) and math.isfinite(y) and -180 <= x <= 180 and -90 <= y <= 90,
                        'TEMPORARILY_UNAVAILABLE', '카카오 장소 좌표 형식이 맞지 않습니다.', 503)
                places.append(dict(id=row['id'], name=row['place_name'], address=row['address_name'], longitude=x, latitude=y,
                                   study_suitability='unknown'))
            return dict(provider='kakao', places=places, is_end=data['meta']['is_end'],
                        recommendation_basis='distance' if located else 'keyword_relevance',
                        notice='카카오 장소 정보입니다. 조용함·콘센트·Wi-Fi·장시간 이용 가능 여부는 확인되지 않았습니다.')
        except (ValueError, TypeError, KeyError):
            raise DomainError('TEMPORARILY_UNAVAILABLE', '카카오 연결/응답 확인에 실패했습니다. 원본 오류·위치·키는 공개하지 않습니다.', 503) from None
