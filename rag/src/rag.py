from __future__ import annotations

from typing import AsyncIterator, Dict, List

from openai import AsyncOpenAI, OpenAI

from .config import settings
from .store import query

_client = OpenAI(api_key=settings.openai_api_key)
_aclient = AsyncOpenAI(api_key=settings.openai_api_key)

SYSTEM_PROMPT = """You are a research assistant for the QIC-WA (Quality Improvement Center for Workforce Analytics) and QIC-WD (Quality Improvement Center for Workforce Development) projects. You answer questions strictly using the supplied source excerpts.

Rules:
- Ground every factual claim in the provided sources. If the sources do not cover the question, say so plainly.
- Cite sources inline using bracketed numbers like [1], [2], matching the numbered sources block. Multiple citations are fine: [1][3].
- Prefer concise, structured answers. Use bullet points or short sections when comparing findings.
- Quote exact figures, sample sizes, and definitions verbatim when relevant.
- Distinguish between findings reported by the projects vs. external references when the source list indicates it.
- Never invent citations. Never cite a number that is not in the list."""


def _format_sources(hits: List[Dict]) -> str:
    lines: List[str] = []
    for i, h in enumerate(hits, start=1):
        m = h["meta"]
        title = m.get("title") or m.get("url", "Untitled")
        url = m.get("url", "")
        loc = ""
        if m.get("page_start"):
            loc = f", p.{m['page_start']}"
            if m.get("page_end") and m["page_end"] != m["page_start"]:
                loc = f", pp.{m['page_start']}–{m['page_end']}"
        external = " [external]" if m.get("is_external") else ""
        lines.append(f"[{i}] {title}{loc}{external}\nURL: {url}\n---\n{h['text']}")
    return "\n\n".join(lines)


def build_messages(history: List[Dict[str, str]], hits: List[Dict]) -> List[Dict[str, str]]:
    sources_block = _format_sources(hits) if hits else "(no sources retrieved)"
    user_question = ""
    for m in reversed(history):
        if m["role"] == "user":
            user_question = m["content"]
            break

    augmented_user = (
        f"Question:\n{user_question}\n\n"
        f"Numbered sources (use these for citations):\n\n{sources_block}"
    )

    messages: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    # Carry prior conversation turns for context, but replace the latest user turn
    # with the augmented version that contains the retrieved sources.
    for m in history[:-1]:
        if m["role"] in {"user", "assistant"}:
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": augmented_user})
    return messages


def retrieve(question: str) -> List[Dict]:
    return query(question)


def answer(history: List[Dict[str, str]]) -> Dict:
    if not history or history[-1]["role"] != "user":
        return {"answer": "No question provided.", "sources": []}
    question = history[-1]["content"]
    hits = retrieve(question)
    messages = build_messages(history, hits)
    resp = _client.chat.completions.create(
        model=settings.chat_model,
        messages=messages,
        temperature=0.2,
    )
    text = resp.choices[0].message.content or ""
    return {"answer": text, "sources": _sources_payload(hits)}


async def stream_answer(history: List[Dict[str, str]]) -> AsyncIterator[Dict]:
    if not history or history[-1]["role"] != "user":
        yield {"event": "error", "data": "No question provided."}
        return
    question = history[-1]["content"]
    hits = retrieve(question)
    yield {"event": "sources", "data": _sources_payload(hits)}

    messages = build_messages(history, hits)
    stream = await _aclient.chat.completions.create(
        model=settings.chat_model,
        messages=messages,
        temperature=0.2,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            yield {"event": "token", "data": delta}
    yield {"event": "done", "data": ""}


def _sources_payload(hits: List[Dict]) -> List[Dict]:
    out: List[Dict] = []
    for i, h in enumerate(hits, start=1):
        m = h["meta"]
        out.append(
            {
                "n": i,
                "title": m.get("title") or m.get("url"),
                "url": m.get("url"),
                "page_start": m.get("page_start"),
                "page_end": m.get("page_end"),
                "is_external": bool(m.get("is_external")),
                "score": round(h.get("score", 0.0), 4),
            }
        )
    return out
