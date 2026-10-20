"""Explicit, role-filtered local corpus; keyword retrieval, not embeddings."""

import json
import re
from datetime import datetime, timezone

from backend.contracts import ROOT, SECRET, digest, require


class Corpus:
    def __init__(self, store):
        self.store = store
        self.active = set()
        with store.transaction() as db:
            db.execute("CREATE TABLE IF NOT EXISTS knowledge (id TEXT PRIMARY KEY, metadata TEXT NOT NULL, body TEXT NOT NULL)")
            for source in json.loads((ROOT / "knowledge/corpus.json").read_text()):
                path = ROOT / source["path"]
                require(path.resolve().is_relative_to(ROOT) and not path.is_symlink(), "FORBIDDEN", "허용된 코퍼스가 아닙니다.", 403)
                text = path.read_text()
                require(not SECRET.search(text), "FORBIDDEN", "비밀 형식이 포함된 문서는 인덱싱하지 않습니다.", 403)
                for offset in range(0, len(text), 1800):
                    body = text[offset:offset + 1800]
                    metadata = {**source, "content_digest": digest(body), "offset": offset,
                                "collected_at": datetime.now(timezone.utc).isoformat()}
                    key = digest([source["path"], source["version"], offset])
                    self.active.add(key)
                    db.execute("INSERT OR REPLACE INTO knowledge VALUES (?, ?, ?)", (key, json.dumps(metadata), body))

    def search(self, role, query):
        require(role in ("planner", "builder", "validator", "security"), "FORBIDDEN", "검색 역할을 확인하세요.", 403)
        require(isinstance(query, str) and 0 < len(query) <= 500, "INVALID_COMMAND", "검색어 길이를 확인하세요.", 422)
        terms = set(re.findall(r"\w+", query.casefold()))
        results = []
        with self.store.transaction() as db:
            for row in db.execute("SELECT * FROM knowledge"):
                if row["id"] not in self.active:
                    continue
                metadata = json.loads(row["metadata"])
                if role not in metadata["roles"]:
                    continue
                score = sum(row["body"].casefold().count(term) for term in terms)
                if score:
                    results.append(dict(chunk_id=row["id"], **metadata, text=row["body"], score=score))
        return sorted(results, key=lambda r: (-r["score"], r["chunk_id"]))[:5]
