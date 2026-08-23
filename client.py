"""Thin async HTTP wrapper around the Kalshi trade API.

Owns exactly four concerns and no business logic:

  * request signing (delegated to auth.KalshiSigner)
  * a concurrency cap, so async ingest cannot fire hundreds of requests at once
  * retry with exponential backoff and jitter, on 429 and 5xx only
  * cursor pagination, hidden behind an async generator

Everything else -- what to fetch, how to parse it -- lives in ingest.py.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any, AsyncIterator

import httpx

from auth import API_PREFIX, BASE_URL, KalshiSigner

# Retry policy. Only 429 (rate limited) and 5xx (their server broke) are worth
# retrying; any other 4xx means the request itself is wrong and repeating it just
# sends the same mistake again.
RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 5
BACKOFF_BASE_SEC = 0.5
MAX_BACKOFF_SEC = 30.0


class KalshiAPIError(RuntimeError):
    """A non-retryable API failure, or a retryable one that ran out of attempts."""

    def __init__(self, status: int, path: str, body: str):
        self.status = status
        self.path = path
        self.body = body
        super().__init__(f"HTTP {status} on {path}: {body[:300]}")


class KalshiClient:
    """Signed, rate-limited, retrying async GET client.

    Use as an async context manager so the underlying connection pool is closed:

        async with KalshiClient(signer) as client:
            data = await client.get("/markets", {"status": "settled"})
    """

    def __init__(
        self,
        signer: KalshiSigner,
        base_url: str = BASE_URL,
        api_prefix: str = API_PREFIX,
        max_concurrency: int = 8,
        timeout: float = 30.0,
    ):
        self.signer = signer
        self.base_url = base_url.rstrip("/")
        self.api_prefix = api_prefix
        self._sem = asyncio.Semaphore(max_concurrency)
        # Accept-Encoding is pinned to gzip on purpose. Kalshi will serve large
        # responses (/series is ~630 KB) with brotli, and the installed
        # brotlicffi decoder throws "called with data when can_accept_more_data()
        # is False" partway through the stream. gzip decodes cleanly and the
        # bandwidth difference is irrelevant here.
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"Accept": "application/json", "Accept-Encoding": "gzip, deflate"},
        )
        # Populated as requests are made; surfaced in the ingest summary so the
        # README can say honestly how much retrying the run actually needed.
        self.stats = {"requests": 0, "retries": 0, "rate_limited": 0}

    async def __aenter__(self) -> "KalshiClient":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.close()

    async def close(self) -> None:
        await self._http.aclose()

    def _full_path(self, path: str) -> str:
        """Prepend the /trade-api/v2 prefix unless the caller already did."""
        if path.startswith(self.api_prefix):
            return path
        return self.api_prefix + ("" if path.startswith("/") else "/") + path

    @staticmethod
    def _sleep_for(attempt: int, retry_after: str | None) -> float:
        """Exponential backoff with jitter, honouring Retry-After when sent.

        attempt is 0-based, so waits go 0.5s, 1s, 2s, 4s -- each with a random
        nudge so concurrent failures do not all retry on the same instant.
        """
        if retry_after:
            try:
                return min(float(retry_after), MAX_BACKOFF_SEC)
            except ValueError:
                pass  # Retry-After can be an HTTP date; fall through to backoff
        base = min(BACKOFF_BASE_SEC * (2**attempt), MAX_BACKOFF_SEC)
        return base * (1.0 + random.random() * 0.25)

    async def get(self, path: str, params: dict | None = None) -> dict:
        """Signed GET returning parsed JSON.

        Retries 429/5xx with backoff; raises KalshiAPIError on anything else, or
        once attempts are exhausted.
        """
        full_path = self._full_path(path)
        url = self.base_url + full_path
        last_status: int | None = None
        last_body = ""

        async with self._sem:
            for attempt in range(MAX_ATTEMPTS):
                # Re-sign every attempt: the signature covers a timestamp, so a
                # stale one from a previous attempt could be rejected outright.
                headers = self.signer.headers("GET", full_path)
                try:
                    resp = await self._http.get(url, headers=headers, params=params)
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    # Network-level failure: no status code, but worth retrying.
                    last_status, last_body = 0, f"{type(exc).__name__}: {exc}"
                    if attempt == MAX_ATTEMPTS - 1:
                        break
                    self.stats["retries"] += 1
                    await asyncio.sleep(self._sleep_for(attempt, None))
                    continue

                self.stats["requests"] += 1
                if resp.status_code == 200:
                    return resp.json()

                last_status, last_body = resp.status_code, resp.text
                if resp.status_code not in RETRY_STATUSES:
                    raise KalshiAPIError(resp.status_code, full_path, resp.text)
                if resp.status_code == 429:
                    self.stats["rate_limited"] += 1
                if attempt == MAX_ATTEMPTS - 1:
                    break
                self.stats["retries"] += 1
                await asyncio.sleep(
                    self._sleep_for(attempt, resp.headers.get("Retry-After"))
                )

        raise KalshiAPIError(
            last_status or 0,
            full_path,
            f"gave up after {MAX_ATTEMPTS} attempts: {last_body}",
        )

    async def paginate(
        self,
        path: str,
        params: dict | None = None,
        key: str = "markets",
        max_items: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield items from a cursor-paginated endpoint, one page at a time.

        The cursor is an opaque bookmark: echo it back untouched, and stop when
        the response omits it or returns it empty. Some endpoints also repeat the
        final cursor forever, so a repeat is treated as the end too.
        """
        params = dict(params or {})
        seen_cursors: set[str] = set()
        yielded = 0

        while True:
            page = await self.get(path, params)
            items = page.get(key) or []
            for item in items:
                yield item
                yielded += 1
                if max_items is not None and yielded >= max_items:
                    return

            cursor = page.get("cursor")
            if not cursor or cursor in seen_cursors or not items:
                return
            seen_cursors.add(cursor)
            params["cursor"] = cursor
