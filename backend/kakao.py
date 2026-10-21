"""Trusted Kakao adapter; credentials never enter model packets or generated containers."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat

import httpx
from pydantic import BaseModel, Field

from backend.contracts import ROOT, DomainError, require

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
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as source:
            info = os.fstat(source.fileno())
            require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600 and info.st_uid == os.getuid(),
                    'FORBIDDEN', '카카오 키 파일은 현재 사용자 소유의 일반 파일·권한 600이어야 합니다.', 403)
            raw = source.read(4097)
        require(len(raw) <= 4096, 'INVALID_COMMAND', '카카오 로컬 설정 형식을 확인하세요.', 422)
        def unique(pairs):
            require(len(dict(pairs)) == len(pairs), 'INVALID_COMMAND', '카카오 설정에 중복 항목이 있습니다.', 422)
            return dict(pairs)
        value = json.loads(raw, object_pairs_hook=unique)
        require(isinstance(value, dict) and set(value) == {'javascript_key', 'rest_api_key', 'free_quota_confirmed', 'paid_api_disabled_confirmed'} and
                all(isinstance(value[k], str) for k in ('javascript_key', 'rest_api_key')) and
                all(type(value[k]) is bool for k in ('free_quota_confirmed', 'paid_api_disabled_confirmed')),
                'INVALID_COMMAND', '카카오 로컬 설정 형식을 확인하세요.', 422)
        return KakaoConfig(**value)
    except (OSError, ValueError, RecursionError):
        raise DomainError('RUNTIME_UNAVAILABLE', '카카오 키 파일이 없거나 읽을 수 없습니다. 키 값을 로그/채팅에 붙이지 마세요.') from None


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

    def usage(self, block=False):
        day = datetime.now(timezone.utc).date().isoformat()
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE IF NOT EXISTS kakao_usage (day TEXT PRIMARY KEY, count INTEGER NOT NULL, blocked INTEGER NOT NULL)')
            db.execute('INSERT OR IGNORE INTO kakao_usage VALUES (?,0,0)', (day,))
            count, blocked = db.execute('SELECT count,blocked FROM kakao_usage WHERE day=?', (day,)).fetchone()
            if block:
                db.execute('UPDATE kakao_usage SET blocked=1 WHERE day=?', (day,))
            else:
                require(not blocked and count < DAILY_LIMIT, 'RUNTIME_UNAVAILABLE', '카카오 검색 테스트 쿼터가 소진/차단됐습니다. 자동 재시도·유료 전환하지 않습니다.', 429)
                db.execute('UPDATE kakao_usage SET count=count+1 WHERE day=?', (day,))

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
        self.usage()  # Count attempts before I/O, including errors and lost responses.
        try:
            async with httpx.AsyncClient(base_url='https://dapi.kakao.com', trust_env=False, follow_redirects=False,
                                         timeout=8, transport=self.transport) as client:
                async with client.stream('GET', path, params=params, headers={'Authorization': 'KakaoAK ' + self.config.rest_api_key}) as response:
                    if response.status_code == 429:
                        self.usage(block=True)
                    require(response.status_code == 200, 'RUNTIME_UNAVAILABLE',
                            '카카오 검색이 거절/실패했습니다. 무료 자격·키·권한·쿼터를 확인하세요. 자동 재시도하지 않습니다.', 503)
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        require(len(raw) <= 131072, 'TEMPORARILY_UNAVAILABLE', '카카오 응답 크기 한도를 초과했습니다.', 503)
            data = json.loads(raw)
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
        except (httpx.HTTPError, ValueError, TypeError, KeyError):
            raise DomainError('TEMPORARILY_UNAVAILABLE', '카카오 연결/응답 확인에 실패했습니다. 원본 오류·위치·키는 공개하지 않습니다.', 503) from None
