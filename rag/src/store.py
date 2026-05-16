from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

import chromadb
from chromadb.config import Settings as ChromaSettings
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import settings


_client = OpenAI(api_key=settings.openai_api_key)
_chroma = chromadb.PersistentClient(
    path=str(settings.chroma_dir),
    settings=ChromaSettings(anonymized_telemetry=False),
)
_collection = _chroma.get_or_create_collection(
    name="qic_corpus",
    metadata={"hnsw:space": "cosine"},
)


def chunk_id(url: str, idx: int) -> str:
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    return f"{h}-{idx:05d}"


def url_hash(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=30))
def embed_batch(texts: List[str]) -> List[List[float]]:
    resp = _client.embeddings.create(model=settings.embedding_model, input=texts)
    return [d.embedding for d in resp.data]


def embed_query(text: str) -> List[float]:
    return embed_batch([text])[0]


def add_document(url: str, chunks: List[Dict[str, Any]]) -> int:
    """Replace any existing chunks for `url` with these new ones."""
    delete_document(url)

    if not chunks:
        return 0

    ids: List[str] = []
    docs: List[str] = []
    metas: List[Dict[str, Any]] = []
    for i, c in enumerate(chunks):
        ids.append(chunk_id(url, i))
        docs.append(c["text"])
        meta = {k: v for k, v in c.items() if k != "text" and v is not None}
        meta["url"] = url
        meta["chunk_index"] = i
        metas.append(meta)

    batch = 96
    for start in range(0, len(docs), batch):
        sub_docs = docs[start : start + batch]
        sub_ids = ids[start : start + batch]
        sub_metas = metas[start : start + batch]
        vectors = embed_batch(sub_docs)
        _collection.add(ids=sub_ids, embeddings=vectors, documents=sub_docs, metadatas=sub_metas)

    return len(docs)


def delete_document(url: str) -> None:
    try:
        _collection.delete(where={"url": url})
    except Exception:
        pass


def query(text: str, k: int | None = None, fetch_k: int | None = None) -> List[Dict[str, Any]]:
    k = k or settings.retrieval_k
    fetch_k = fetch_k or settings.retrieval_fetch_k
    vec = embed_query(text)
    res = _collection.query(query_embeddings=[vec], n_results=fetch_k)
    out: List[Dict[str, Any]] = []
    seen_urls: Dict[str, int] = {}
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    for d, m, dist in zip(docs, metas, dists):
        url = (m or {}).get("url", "")
        # Cap chunks per URL to encourage source diversity
        if seen_urls.get(url, 0) >= 3:
            continue
        seen_urls[url] = seen_urls.get(url, 0) + 1
        out.append({"text": d, "meta": m or {}, "score": 1.0 - float(dist)})
        if len(out) >= k:
            break
    return out


def count() -> int:
    try:
        return _collection.count()
    except Exception:
        return 0


def list_sources(limit: int = 1000) -> List[Dict[str, Any]]:
    try:
        res = _collection.get(include=["metadatas"], limit=20000)
    except Exception:
        return []
    metas = res.get("metadatas") or []
    seen: Dict[str, Dict[str, Any]] = {}
    for m in metas:
        url = (m or {}).get("url")
        if not url or url in seen:
            continue
        seen[url] = {
            "url": url,
            "title": (m or {}).get("title") or url,
            "content_type": (m or {}).get("content_type"),
            "indexed_at": (m or {}).get("indexed_at"),
        }
        if len(seen) >= limit:
            break
    return list(seen.values())


class StateStore:
    """Tracks per-URL content hashes so we can skip unchanged docs on recrawl."""

    def __init__(self, path: Path):
        self.path = path
        self.data: Dict[str, Dict[str, Any]] = {}
        if path.exists():
            try:
                self.data = json.loads(path.read_text())
            except Exception:
                self.data = {}

    def get(self, url: str) -> Dict[str, Any] | None:
        return self.data.get(url)

    def set(self, url: str, content_hash: str, etag: str | None = None) -> None:
        self.data[url] = {
            "hash": content_hash,
            "etag": etag,
            "indexed_at": int(time.time()),
        }

    def remove(self, url: str) -> None:
        self.data.pop(url, None)

    def all_urls(self) -> Iterable[str]:
        return list(self.data.keys())

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2))
