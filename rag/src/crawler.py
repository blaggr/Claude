from __future__ import annotations

import asyncio
import hashlib
import urllib.robotparser
from dataclasses import dataclass, field
from typing import Iterable, Set, Tuple
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .config import settings


DOC_EXTENSIONS = (".pdf", ".docx", ".pptx", ".xlsx", ".doc", ".ppt", ".xls")

EXCLUDED_HOST_KEYWORDS = (
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "linkedin.com",
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "pinterest.com",
    "reddit.com",
    "vimeo.com",
    "doubleclick.net",
    "googletagmanager.com",
    "google-analytics.com",
)


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    content_type: str
    content: bytes
    etag: str | None = None


@dataclass
class CrawlPlan:
    seeds: Tuple[str, ...]
    seed_domains: Tuple[str, ...]
    visited: Set[str] = field(default_factory=set)
    queued: Set[str] = field(default_factory=set)


def normalize_url(u: str) -> str:
    u, _ = urldefrag(u)
    return u.strip()


def host_of(u: str) -> str:
    return urlparse(u).netloc.lower()


def is_seed_domain(u: str, seed_domains: Iterable[str]) -> bool:
    host = host_of(u)
    return any(host == d or host.endswith("." + d) for d in seed_domains)


def is_document_url(u: str) -> bool:
    return u.lower().split("?", 1)[0].endswith(DOC_EXTENSIONS)


def looks_excluded(u: str) -> bool:
    host = host_of(u)
    return any(k in host for k in EXCLUDED_HOST_KEYWORDS)


class RobotsCache:
    def __init__(self, user_agent: str):
        self.ua = user_agent
        self._cache: dict[str, urllib.robotparser.RobotFileParser] = {}

    async def allowed(self, client: httpx.AsyncClient, url: str) -> bool:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        rp = self._cache.get(base)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = await client.get(base + "/robots.txt", timeout=10)
                if r.status_code < 400 and r.text:
                    rp.parse(r.text.splitlines())
                else:
                    rp.parse([])
            except Exception:
                rp.parse([])
            self._cache[base] = rp
        try:
            return rp.can_fetch(self.ua, url)
        except Exception:
            return True


async def _fetch(client: httpx.AsyncClient, url: str) -> FetchResult | None:
    try:
        r = await client.get(url, timeout=settings.request_timeout_s, follow_redirects=True)
    except Exception as e:
        print(f"[crawler] fetch failed {url}: {e}")
        return None
    return FetchResult(
        url=url,
        final_url=str(r.url),
        status=r.status_code,
        content_type=r.headers.get("content-type", ""),
        content=r.content,
        etag=r.headers.get("etag"),
    )


def _extract_links(html: bytes, base_url: str) -> list[str]:
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return []
    out: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        absu = normalize_url(urljoin(base_url, href))
        if absu.startswith(("http://", "https://")):
            out.append(absu)
    return out


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def crawl(
    seed_urls: Iterable[str],
    seed_domains: Iterable[str],
    on_doc,  # async callable(FetchResult, depth, is_seed_html)
    progress=None,
) -> dict:
    seeds = tuple(normalize_url(u) for u in seed_urls)
    seed_domains_t = tuple(d.lower() for d in seed_domains)

    visited: Set[str] = set()
    # queue items: (url, depth, is_external_one_hop)
    queue: asyncio.Queue[tuple[str, int, bool]] = asyncio.Queue()
    for s in seeds:
        await queue.put((s, 0, False))

    stats = {"fetched": 0, "extracted": 0, "skipped": 0, "errors": 0}

    headers = {"User-Agent": settings.user_agent, "Accept": "*/*"}
    limits = httpx.Limits(max_connections=settings.crawl_concurrency * 2, max_keepalive_connections=settings.crawl_concurrency)

    async with httpx.AsyncClient(headers=headers, limits=limits) as client:
        robots = RobotsCache(settings.user_agent)
        per_domain_count: dict[str, int] = {}

        sem = asyncio.Semaphore(settings.crawl_concurrency)

        async def worker():
            while True:
                try:
                    url, depth, external = await asyncio.wait_for(queue.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    return
                try:
                    if url in visited:
                        queue.task_done()
                        continue
                    visited.add(url)

                    host = host_of(url)
                    if is_seed_domain(url, seed_domains_t):
                        if per_domain_count.get(host, 0) >= settings.max_pages_per_domain:
                            stats["skipped"] += 1
                            queue.task_done()
                            continue
                        per_domain_count[host] = per_domain_count.get(host, 0) + 1

                    if not await robots.allowed(client, url):
                        stats["skipped"] += 1
                        queue.task_done()
                        continue

                    async with sem:
                        res = await _fetch(client, url)
                    if res is None or res.status >= 400 or not res.content:
                        stats["errors"] += 1
                        queue.task_done()
                        continue

                    stats["fetched"] += 1
                    if progress:
                        progress(url, stats)

                    ct = (res.content_type or "").lower()
                    is_html = "html" in ct or "xml" in ct or ct == ""
                    is_doc = (
                        "pdf" in ct
                        or "officedocument" in ct
                        or "msword" in ct
                        or is_document_url(res.final_url)
                    )

                    if is_doc or (is_html and (is_seed_domain(res.final_url, seed_domains_t) or external)):
                        await on_doc(res, depth, is_seed_domain(res.final_url, seed_domains_t) and is_html)
                        stats["extracted"] += 1

                    if is_html and is_seed_domain(res.final_url, seed_domains_t):
                        for link in _extract_links(res.content, res.final_url):
                            if link in visited or looks_excluded(link):
                                continue
                            if is_document_url(link):
                                # Always fetch docs regardless of host
                                await queue.put((link, depth + 1, False))
                            elif is_seed_domain(link, seed_domains_t):
                                await queue.put((link, depth + 1, False))
                            else:
                                # External HTML: 1 hop only, don't follow further
                                if depth + 1 <= 1:
                                    await queue.put((link, depth + 1, True))
                except Exception as e:
                    print(f"[crawler] worker error on {url}: {e}")
                    stats["errors"] += 1
                finally:
                    queue.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(settings.crawl_concurrency)]
        try:
            await queue.join()
        finally:
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

    stats["visited"] = len(visited)
    return stats
