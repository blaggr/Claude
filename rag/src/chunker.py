from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator, List

import tiktoken

from .config import settings


_enc = tiktoken.get_encoding("cl100k_base")


@dataclass
class Chunk:
    text: str
    page_start: int | None = None
    page_end: int | None = None


_PAGE_RE = re.compile(r"^\[Page (\d+)\]", re.MULTILINE)


def _split_by_paragraphs(text: str) -> List[str]:
    parts = re.split(r"\n{2,}", text)
    return [p.strip() for p in parts if p.strip()]


def _token_len(s: str) -> int:
    return len(_enc.encode(s, disallowed_special=()))


def _truncate_tokens(s: str, n: int) -> str:
    toks = _enc.encode(s, disallowed_special=())
    return _enc.decode(toks[:n])


def chunk_text(text: str) -> Iterator[Chunk]:
    if not text.strip():
        return

    target = settings.chunk_tokens
    overlap = settings.chunk_overlap
    paragraphs = _split_by_paragraphs(text)

    buf: List[str] = []
    buf_tokens = 0

    def flush() -> Chunk | None:
        if not buf:
            return None
        joined = "\n\n".join(buf)
        page_markers = [int(m.group(1)) for m in _PAGE_RE.finditer(joined)]
        page_start = page_markers[0] if page_markers else None
        page_end = page_markers[-1] if page_markers else None
        return Chunk(text=joined, page_start=page_start, page_end=page_end)

    for para in paragraphs:
        ptok = _token_len(para)

        if ptok > target:
            chunk = flush()
            if chunk:
                yield chunk
            buf = []
            buf_tokens = 0
            toks = _enc.encode(para, disallowed_special=())
            step = target - overlap
            for i in range(0, len(toks), step):
                window = toks[i : i + target]
                if not window:
                    continue
                yield Chunk(text=_enc.decode(window))
            continue

        if buf_tokens + ptok > target and buf:
            chunk = flush()
            if chunk:
                yield chunk
            if overlap > 0 and buf:
                tail = _truncate_tokens("\n\n".join(buf), overlap)
                buf = [tail, para]
                buf_tokens = _token_len(tail) + ptok
            else:
                buf = [para]
                buf_tokens = ptok
        else:
            buf.append(para)
            buf_tokens += ptok

    final = flush()
    if final:
        yield final
