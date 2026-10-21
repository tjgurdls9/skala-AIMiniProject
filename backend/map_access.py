"""Shared private-file, quota and fixed-endpoint boundaries for trusted map adapters."""
from datetime import datetime, timezone
import json
import os
import sqlite3
import stat

import httpx

from backend.contracts import DomainError, require

ENDPOINTS = {
    'kakao': ('https://dapi.kakao.com', {'/v2/local/search/keyword.json', '/v2/local/search/category.json'}),
    'geoapify': ('https://api.geoapify.com', {'/v2/places', '/v1/geocode/search'}),
}


def private_settings(path, keys, flags):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as source:
            info = os.fstat(source.fileno())
            require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600 and info.st_uid == os.getuid(),
                    'FORBIDDEN', '지도 키 파일은 현재 사용자 소유의 일반 파일·권한 600이어야 합니다.', 403)
            raw = source.read(4097)
        require(len(raw) <= 4096, 'INVALID_COMMAND', '지도 로컬 설정 형식을 확인하세요.', 422)
        def unique(pairs):
            require(len(dict(pairs)) == len(pairs), 'INVALID_COMMAND', '지도 설정에 중복 항목이 있습니다.', 422)
            return dict(pairs)
        value = json.loads(raw, object_pairs_hook=unique)
        require(isinstance(value, dict) and set(value) == set(keys) | set(flags) and
                all(isinstance(value[k], str) for k in keys) and all(type(value[k]) is bool for k in flags),
                'INVALID_COMMAND', '지도 로컬 설정 형식을 확인하세요.', 422)
        return value
    except (OSError, ValueError, RecursionError):
        raise DomainError('RUNTIME_UNAVAILABLE', '지도 키 파일이 없거나 읽을 수 없습니다. 키 값을 로그/채팅에 붙이지 마세요.') from None


def reserve_usage(database, provider, limit, block=False):
    require(provider in ENDPOINTS, 'FORBIDDEN', '고정 지도 공급자만 사용할 수 있습니다.', 403)
    day = datetime.now(timezone.utc).date().isoformat()
    try:
        with sqlite3.connect(database) as db:
            db.execute('BEGIN IMMEDIATE')
            table = provider + '_usage'  # Provider names come only from the fixed whitelist above.
            db.execute(f'CREATE TABLE IF NOT EXISTS {table} (day TEXT PRIMARY KEY, count INTEGER NOT NULL, blocked INTEGER NOT NULL)')
            db.execute(f'INSERT OR IGNORE INTO {table} VALUES (?,0,0)', (day,))
            count, blocked = db.execute(f'SELECT count,blocked FROM {table} WHERE day=?', (day,)).fetchone()
            if block:
                db.execute(f'UPDATE {table} SET blocked=1 WHERE day=?', (day,))
            else:
                require(not blocked and count < limit, 'RUNTIME_UNAVAILABLE', '지도 테스트 쿼터가 소진/차단됐습니다. 자동 재시도·유료 전환하지 않습니다.', 429)
                db.execute(f'UPDATE {table} SET count=count+1 WHERE day=?', (day,))
    except sqlite3.Error:
        raise DomainError('TEMPORARILY_UNAVAILABLE', '지도 사용량 원장을 확인할 수 없어 호출을 차단했습니다.', 503) from None


async def provider_json(provider, path, params, headers, database, limit=200, transport=None):
    require(provider in ENDPOINTS and path in ENDPOINTS[provider][1], 'FORBIDDEN', '등록된 지도 검색 경로만 호출할 수 있습니다.', 403)
    reserve_usage(database, provider, limit)
    try:
        async with httpx.AsyncClient(base_url=ENDPOINTS[provider][0], trust_env=False, follow_redirects=False,
                                     timeout=8, transport=transport) as client:
            async with client.stream('GET', path, params=params, headers=headers) as response:
                if response.status_code == 429:
                    reserve_usage(database, provider, limit, block=True)
                require(response.status_code == 200, 'RUNTIME_UNAVAILABLE',
                        '지도 검색이 거절/실패했습니다. 무료 자격·키·권한·쿼터를 확인하세요. 자동 재시도하지 않습니다.', 503)
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    require(len(raw) <= 131072, 'TEMPORARILY_UNAVAILABLE', '지도 응답 크기 한도를 초과했습니다.', 503)
        return json.loads(raw)
    except (httpx.HTTPError, ValueError):
        raise DomainError('TEMPORARILY_UNAVAILABLE', '지도 연결/응답 확인에 실패했습니다. 원본 오류·위치·키는 공개하지 않습니다.', 503) from None
