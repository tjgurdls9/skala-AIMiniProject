"""Versioned role-filtered corpus; keyword and optional native Ollama embeddings."""

import json
import math
import re
from datetime import datetime, timezone

import httpx

from backend.contracts import ROOT, SECRET, DomainError, digest, require, validate
from runner.model import ModelUnavailable


class Corpus:
    def __init__(self, store):
        self.store, self.active, self.conflict = store, set(), False
        with store.transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS knowledge (id TEXT PRIMARY KEY, metadata TEXT NOT NULL, body TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS embeddings (chunk_id TEXT NOT NULL, model TEXT NOT NULL, vector TEXT NOT NULL, PRIMARY KEY(chunk_id,model))')
            for source in json.loads((ROOT / 'knowledge/corpus.json').read_text()):
                path = ROOT / source['path']
                require(path.resolve().is_relative_to(ROOT) and not path.is_symlink(), 'FORBIDDEN', '허용된 코퍼스가 아닙니다.', 403)
                text = path.read_text()
                require(not SECRET.search(text), 'FORBIDDEN', '비밀 형식이 포함된 문서는 인덱싱하지 않습니다.', 403)
                # The local living contract uses its exact content as its immutable document version.
                if source['path'] == 'docs/planning/contracts.md':
                    source['version'] += '@' + digest(text)
                for offset in range(0, len(text), 1800):
                    body = text[offset:offset + 1800]
                    metadata = {**source, 'content_digest': digest(body), 'offset': offset,
                                'collected_at': datetime.now(timezone.utc).isoformat()}
                    for existing in db.execute('SELECT metadata FROM knowledge'):
                        old = json.loads(existing[0])
                        if (old['url'], old['version'], old['offset']) == (source['url'], source['version'], offset) and old['content_digest'] != metadata['content_digest']:
                            self.conflict = True
                    key = digest([source['path'], source['version'], offset, metadata['content_digest']])
                    self.active.add(key)
                    db.execute('INSERT OR IGNORE INTO knowledge VALUES (?, ?, ?)', (key, json.dumps(metadata), body))

    def rows(self, role, query):
        require(role in ('planner', 'builder', 'validator', 'security'), 'FORBIDDEN', '검색 역할을 확인하세요.', 403)
        require(isinstance(query, str) and 0 < len(query) <= 500 and not SECRET.search(query), 'INVALID_COMMAND', '검색어 길이/비밀 형식을 확인하세요.', 422)
        require(not self.conflict, 'VERSION_CONFLICT', '동일 출처/버전의 본문이 충돌합니다. 코퍼스 버전을 확인하세요.')
        results = []
        with self.store.transaction() as db:
            for row in db.execute('SELECT * FROM knowledge'):
                metadata = json.loads(row['metadata'])
                if row['id'] in self.active and role in metadata['roles']:
                    require(digest(row['body']) == metadata['content_digest'], 'INVALID_COMMAND', '코퍼스 본문 해시가 일치하지 않습니다.', 422)
                    results.append(dict(chunk_id=row['id'], **metadata, text=row['body']))
        return results

    def search(self, role, query):
        terms = set(re.findall(r'\w+', query.casefold()))
        results = []
        for row in self.rows(role, query):
            score = sum(row['text'].casefold().count(term) for term in terms)
            if score:
                results.append(dict(row, score=score))
        return sorted(results, key=lambda r: (-r['score'], r['chunk_id']))[:5]

    async def retrieve(self, role, query, model=None):
        require(role in ('planner', 'builder', 'validator', 'security'), 'FORBIDDEN', '검색 역할을 확인하세요.', 403)
        evidence = dict(role=role, method='semantic' if model else 'keyword', status='no_results', model=None, sources=[])
        documents = []
        try:
            if model is None:
                documents = self.search(role, query)
            else:
                rows = self.rows(role, query)  # ACL precedes vector/cache reads and model calls.
                identity = await model.embedding_identity()
                evidence['model'] = identity
                vectors, missing = {}, []
                with self.store.transaction() as db:
                    for row in rows:
                        saved = db.execute('SELECT vector FROM embeddings WHERE chunk_id=? AND model=?', (row['chunk_id'], identity)).fetchone()
                        if saved:
                            vectors[row['chunk_id']] = json.loads(saved[0])
                        else:
                            missing.append(row)
                for index in range(0, len(missing), 8):
                    batch = missing[index:index + 8]
                    embedded = await model.embed([r['text'] for r in batch])
                    require(await model.embedding_identity() == identity, 'VERSION_CONFLICT', '임베딩 모델 버전이 검색 중 바뀌었습니다.')
                    require(len(embedded) == len(batch), 'INVALID_COMMAND', '임베딩 개수가 일치하지 않습니다.', 422)
                    with self.store.transaction() as db:
                        for row, vector in zip(batch, embedded):
                            vectors[row['chunk_id']] = vector
                            db.execute('INSERT OR IGNORE INTO embeddings VALUES (?, ?, ?)', (row['chunk_id'], identity, json.dumps(vector, allow_nan=False)))
                query_vector = (await model.embed(['Instruct: Retrieve technical documentation relevant to the query\nQuery: ' + query]))[0]
                require(await model.embedding_identity() == identity, 'VERSION_CONFLICT', '임베딩 모델 버전이 검색 중 바뀌었습니다.')
                for row in rows:
                    vector = vectors[row['chunk_id']]
                    require(len(vector) == len(query_vector) and all(isinstance(n, (int, float)) and math.isfinite(n) for n in vector + query_vector), 'INVALID_COMMAND', '임베딩 버전을 확인하세요.', 422)
                    norm = math.sqrt(sum(n*n for n in vector) * sum(n*n for n in query_vector))
                    require(norm > 0, 'INVALID_COMMAND', '빈 임베딩은 검색 근거가 아닙니다.', 422)
                    score = sum(a*b for a, b in zip(vector, query_vector)) / norm
                    if score >= 0.35:
                        documents.append(dict(row, score=score))
                documents = sorted(documents, key=lambda r: (-r['score'], r['chunk_id']))[:5]
            evidence['status'] = 'found' if documents else 'no_results'
            evidence['sources'] = [{key: row[key] for key in ('chunk_id', 'url', 'version', 'license', 'collected_at', 'content_digest', 'roles', 'score')} for row in documents]
        except (ModelUnavailable, httpx.HTTPError):
            evidence.update(status='search_error', error_code='MODEL_UNAVAILABLE')
        except DomainError as error:
            evidence.update(status='search_error', error_code='VERSION_CONFLICT' if error.code == 'VERSION_CONFLICT' else 'INVALID_SOURCE')
        except (ValueError, KeyError, TypeError, IndexError):
            evidence.update(status='search_error', error_code='SEARCH_FAILED')
        if evidence['status'] == 'search_error':
            documents = []
            evidence['sources'] = []
        validate('RetrievalEvidence', evidence)
        return dict(evidence=evidence, documents=documents)
