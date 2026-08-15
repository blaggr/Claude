# QIC Research RAG

A retrieval-augmented generation system built on the public content of
[qic-wa.org](https://www.qic-wa.org) and [qic-wd.org](https://qic-wd.org), all
documents linked from those sites (PDF / DOCX / PPTX / XLSX), and one hop of
external research links from those pages.

- **Stack:** FastAPI + Chroma (on-disk) + OpenAI (`gpt-4o` + `text-embedding-3-large`).
- **Interface:** Web app (chat) and REST API (single bearer token).
- **Deployment:** Render web service with a persistent disk.
- **Refresh:** Weekly incremental recrawl via APScheduler (skips unchanged docs by content hash).

## Architecture

```
┌──────────────────────────┐
│ Browser chat UI (/)      │──┐
└──────────────────────────┘  │   Authorization: Bearer <token>
┌──────────────────────────┐  │
│ External chatbot         │──┴──▶  FastAPI  ──▶  RAG pipeline  ──▶  OpenAI
└──────────────────────────┘                 │
                                              │
                                   ┌──────────▼──────────┐
                                   │ Chroma (persistent) │
                                   └──────────▲──────────┘
                                              │
                                   ┌──────────┴──────────┐
                                   │   Async crawler     │  ←  qic-wa.org, qic-wd.org
                                   │   + extractors      │     + linked PDFs/docs
                                   │   + chunker         │     + 1-hop external HTML
                                   └─────────────────────┘
```

Project layout:

```
rag/
├── src/
│   ├── main.py        FastAPI app, /api/* endpoints, static UI mount
│   ├── config.py      Settings loaded from environment
│   ├── auth.py        Bearer-token guard
│   ├── rag.py         Retrieval + generation, streaming
│   ├── store.py       Chroma wrapper, embeddings, state tracking
│   ├── crawler.py     Async crawler with robots.txt + domain rules
│   ├── extractor.py   HTML / PDF / DOCX / PPTX / XLSX extraction
│   ├── chunker.py     Token-aware chunking with overlap
│   ├── ingest.py      Pipeline: crawl → extract → chunk → embed → upsert
│   └── scheduler.py   Weekly reindex job
├── web/               Single-file chat UI (no build step)
├── scripts/reindex.py CLI reindex
├── Dockerfile
├── render.yaml        Render Blueprint
└── requirements.txt
```

## Running locally

```bash
cd rag
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Fill in OPENAI_API_KEY and pick an API_BEARER_TOKEN
export DATA_DIR=./data

# First-time index (this takes a while — embeds the entire corpus)
PYTHONPATH=. python scripts/reindex.py --full

# Start the app (UI at http://localhost:8000, API under /api/*)
PYTHONPATH=. uvicorn src.main:app --reload --port 8000
```

The web UI is a single static page; sign in with the same bearer token you put
in `API_BEARER_TOKEN`.

## Deploying to Render

1. Push this branch to GitHub.
2. In Render, **New → Blueprint** and pick this repo. `render.yaml` provisions:
   - a Docker web service from `rag/Dockerfile`
   - a 10 GB persistent disk mounted at `/var/data` (Chroma + crawl state)
   - `API_BEARER_TOKEN` auto-generated
   - `OPENAI_API_KEY` left blank — set it in the Render dashboard before the
     first deploy
3. After it boots, kick off the initial crawl:
   ```bash
   curl -X POST https://<your-render-host>/api/ingest?full=true \
        -H "Authorization: Bearer <token>"
   ```
   Subsequent reindexes happen automatically Mondays 07:00 UTC.

## REST API

All endpoints except `/api/health` require `Authorization: Bearer <API_BEARER_TOKEN>`.

| Method | Path             | Body / Query                              | Notes                                       |
| ------ | ---------------- | ----------------------------------------- | ------------------------------------------- |
| GET    | `/api/health`    | —                                         | Open. Returns chunk count + last ingest.    |
| GET    | `/api/status`    | —                                         | Index stats + scheduler config.             |
| GET    | `/api/sources`   | —                                         | Lists every URL currently in the corpus.    |
| POST   | `/api/chat`      | `{messages: [...], stream: false\|true}`  | Returns JSON or SSE stream.                 |
| POST   | `/api/ingest`    | `?full=true&background=true`              | Manually trigger a recrawl.                 |

### Chat (non-stream)

```bash
curl -X POST https://<host>/api/chat \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [
      {"role": "user", "content": "What strategies has QIC-WD studied for child welfare workforce retention?"}
    ]
  }'
```

Response:

```json
{
  "answer": "QIC-WD evaluated several site-level interventions… [1][3]",
  "sources": [
    {"n": 1, "title": "Site Intervention Summary", "url": "https://qic-wd.org/...", "page_start": 4, "is_external": false, "score": 0.81},
    ...
  ]
}
```

### Chat (streaming, SSE)

Send `"stream": true`. The server emits:

- `{"event": "sources", "data": [...]}` once, before tokens arrive
- `{"event": "token", "data": "..."}` for each token chunk
- `{"event": "done", "data": ""}` when finished

### Wiring an external chatbot

Treat `/api/chat` as a drop-in synchronous endpoint: send chat history, get an
answer plus a sources array. Cite the array's `n` field next to claims, and link
to `url` (+ optional page numbers) in the UI.

## How the corpus is built

1. **Crawl.** Async `httpx` worker pool seeded at `https://www.qic-wa.org` and
   `https://qic-wd.org`. For each seed-domain HTML page:
   - same-domain links → enqueued (HTML)
   - PDF/DOCX/PPTX/XLSX links (any host) → fetched and parsed
   - other external HTML links → fetched at depth 1, **not** followed further
   - social / analytics hosts are filtered out
   - `robots.txt` is honored per host
2. **Extract.** HTML via BeautifulSoup; PDF via `pypdf` (page-numbered); Office
   formats via `python-docx`, `python-pptx`, `openpyxl`.
3. **Chunk.** Token-aware (`tiktoken cl100k_base`), target 600 tokens, 80
   overlap, paragraph-aware, page markers preserved.
4. **Embed.** Batched `text-embedding-3-large` calls with retry/backoff.
5. **Store.** Chroma `PersistentClient` on `/var/data/chroma`, one collection
   with rich metadata (url, title, page range, content type, external flag,
   indexed_at).
6. **Track state.** `state.json` keeps per-URL content hash so the weekly
   recrawl only re-embeds changed documents and prunes pages that disappear.

## Retrieval & generation

- Query is embedded with the same model.
- Top `RETRIEVAL_FETCH_K=40` candidates from Chroma, capped at 3 chunks per URL
  for diversity, narrowed to `RETRIEVAL_K=12` for the prompt.
- System prompt forces inline `[n]`-style citations matching the sources list
  and refuses unsupported claims.
- Streaming uses OpenAI's native streaming API piped through FastAPI SSE.

## Operations

- **Manual reindex (full):** `POST /api/ingest?full=true` or
  `PYTHONPATH=. python scripts/reindex.py --full`.
- **Incremental reindex:** same endpoint with `full=false` (default). Skips
  unchanged docs and prunes deleted ones.
- **Schedule:** `REINDEX_CRON` (cron, UTC). Default Mondays 07:00.
- **Disk:** Chroma + crawl state live under `DATA_DIR`. 10 GB is plenty for
  these two sites.
- **Costs:** OpenAI charges for both embeddings (first index + changes only on
  reindex) and chat completions. With `gpt-4o` and `text-embedding-3-large`,
  expect a few dollars for the initial build and pennies per query.

## Tuning

| Variable                | Default              | Effect                                       |
| ----------------------- | -------------------- | -------------------------------------------- |
| `CHUNK_TOKENS`          | 600                  | Bigger = fewer chunks, less granular recall. |
| `CHUNK_OVERLAP`         | 80                   | More overlap = better recall, more storage.  |
| `RETRIEVAL_K`           | 12                   | Chunks shown to the LLM.                     |
| `RETRIEVAL_FETCH_K`     | 40                   | Candidates fetched before dedup.             |
| `MAX_PAGES_PER_DOMAIN`  | 2000                 | Safety cap on the crawler.                   |
| `CRAWL_CONCURRENCY`     | 8                    | Async fetcher pool size.                     |
| `REINDEX_CRON`          | `0 7 * * 1`          | Cron expression (UTC).                       |
