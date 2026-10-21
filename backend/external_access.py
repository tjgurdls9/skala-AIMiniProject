"""Provider-neutral boundaries for trusted external access: a private settings file, a fixed approved origin and paths,
a daily usage ledger and capped responses. The grant (origin, paths, limit) comes from the caller, never from this module."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import re
import sqlite3
import stat
from urllib.parse import urlsplit

import httpx

from backend.contracts import DomainError, require

NAME = re.compile(r'[a-z][a-z0-9_]{0,31}')
MAX_DAILY_LIMIT = 10000
MAX_RESPONSE_BYTES = 131072
MAX_SETTINGS_BYTES = 4096
TIMEOUT_SECONDS = 8


def _safe_name(name):
    require(isinstance(name, str) and NAME.fullmatch(name), 'INVALID_COMMAND', '외부 접근 이름 형식을 확인하세요.', 422)


@dataclass(frozen=True)
class ExternalGrant:
    name: str
    origin: str
    paths: frozenset
    daily_limit: int

    def __post_init__(self):
        _safe_name(self.name)
        parts = urlsplit(self.origin) if isinstance(self.origin, str) else None
        require(parts is not None and parts.scheme == 'https' and parts.hostname and '@' not in parts.netloc
                and parts.path in ('', '/') and not parts.query and not parts.fragment,
                'INVALID_COMMAND', '외부 접근 대상은 경로 없는 https 출처여야 합니다.', 422)
        require(self.paths and all(isinstance(p, str) and p.startswith('/') and not p.startswith('//') for p in self.paths),
                'INVALID_COMMAND', '외부 접근 경로는 /로 시작하는 고정 경로여야 합니다.', 422)
        require(type(self.daily_limit) is int and 0 < self.daily_limit <= MAX_DAILY_LIMIT,
                'INVALID_COMMAND', '외부 접근 일일 한도 범위를 확인하세요.', 422)


def private_settings(path, keys, flags):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as source:
            info = os.fstat(source.fileno())
            require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600 and info.st_uid == os.getuid(),
                    'FORBIDDEN', '비공개 설정 파일은 현재 사용자 소유의 일반 파일·권한 600이어야 합니다.', 403)
            raw = source.read(MAX_SETTINGS_BYTES + 1)
        require(len(raw) <= MAX_SETTINGS_BYTES, 'INVALID_COMMAND', '비공개 설정 형식을 확인하세요.', 422)

        def unique(pairs):
            require(len(dict(pairs)) == len(pairs), 'INVALID_COMMAND', '비공개 설정에 중복 항목이 있습니다.', 422)
            return dict(pairs)
        value = json.loads(raw, object_pairs_hook=unique)
        require(isinstance(value, dict) and set(value) == set(keys) | set(flags) and
                all(isinstance(value[k], str) for k in keys) and all(type(value[k]) is bool for k in flags),
                'INVALID_COMMAND', '비공개 설정 형식을 확인하세요.', 422)
        return value
    except (OSError, ValueError, RecursionError):
        raise DomainError('RUNTIME_UNAVAILABLE', '비공개 설정 파일이 없거나 읽을 수 없습니다. 키 값을 로그/채팅에 붙이지 마세요.') from None


def reserve_usage(database, name, limit, block=False):
    _safe_name(name)
    day = datetime.now(timezone.utc).date().isoformat()
    try:
        with sqlite3.connect(database) as db:
            db.execute('BEGIN IMMEDIATE')
            table = name + '_usage'  # the name passed _safe_name above
            db.execute(f'CREATE TABLE IF NOT EXISTS {table} (day TEXT PRIMARY KEY, count INTEGER NOT NULL, blocked INTEGER NOT NULL)')
            db.execute(f'INSERT OR IGNORE INTO {table} VALUES (?,0,0)', (day,))
            count, blocked = db.execute(f'SELECT count,blocked FROM {table} WHERE day=?', (day,)).fetchone()
            if block:
                db.execute(f'UPDATE {table} SET blocked=1 WHERE day=?', (day,))
            else:
                require(not blocked and count < limit, 'RUNTIME_UNAVAILABLE', '외부 접근 일일 쿼터가 소진/차단됐습니다. 자동 재시도·유료 전환하지 않습니다.', 429)
                db.execute(f'UPDATE {table} SET count=count+1 WHERE day=?', (day,))
    except sqlite3.Error:
        raise DomainError('TEMPORARILY_UNAVAILABLE', '외부 접근 사용량 원장을 확인할 수 없어 호출을 차단했습니다.', 503) from None


async def external_json(grant, path, params, headers, database, transport=None):
    require(path in grant.paths, 'FORBIDDEN', '승인된 경로만 호출할 수 있습니다.', 403)
    reserve_usage(database, grant.name, grant.daily_limit)
    try:
        async with httpx.AsyncClient(base_url=grant.origin, trust_env=False, follow_redirects=False,
                                     timeout=TIMEOUT_SECONDS, transport=transport) as client:
            async with client.stream('GET', path, params=params, headers=headers) as response:
                if response.status_code == 429:
                    reserve_usage(database, grant.name, grant.daily_limit, block=True)
                require(response.status_code == 200, 'RUNTIME_UNAVAILABLE',
                        '외부 접근이 거절/실패했습니다. 자격·키·권한·쿼터를 확인하세요. 자동 재시도하지 않습니다.', 503)
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    require(len(raw) <= MAX_RESPONSE_BYTES, 'TEMPORARILY_UNAVAILABLE', '외부 응답 크기 한도를 초과했습니다.', 503)
        return json.loads(raw)
    except (httpx.HTTPError, ValueError):
        raise DomainError('TEMPORARILY_UNAVAILABLE', '외부 연결/응답 확인에 실패했습니다. 원본 오류·위치·키는 공개하지 않습니다.', 503) from None
