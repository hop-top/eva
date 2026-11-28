# core/importers/fetch.py
"""Network access for the dataset importers: stdlib only.

One row per request through the Hugging Face dataset viewer (rows API), the
dataset's repo head through the Hub API, a git repo head through smart HTTP
(no API quota), and one raw JSON file. Requests are spaced, and 429 / 5xx /
connection errors are retried with backoff (``Retry-After`` honoured). Any
failure left after the retries raises ``FetchError``; nothing is cached on
disk.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "eva-dataset-importer (+https://github.com/hop-top/eva)"
VIEWER = "https://datasets-server.huggingface.co/rows"
HUB = "https://huggingface.co/api/datasets/"
GIT = "https://github.com/{repo}.git/info/refs?service=git-upload-pack"
RAW = "https://raw.githubusercontent.com/{repo}/{rev}/{path}"
RETRY_STATUS = {429, 500, 502, 503, 504}


class FetchError(RuntimeError):
    """Upstream unreachable, rate limited past the retries, or malformed."""


class RowTruncated(FetchError):
    """The viewer cut a cell short; the row is not usable as is."""


class Fetcher:
    def __init__(self, delay: float = 0.5, tries: int = 5, timeout: float = 60,
                 sleep=time.sleep):
        self.delay, self.tries, self.timeout, self._sleep = delay, tries, timeout, sleep
        self._totals: dict[tuple, int] = {}
        self._last = 0.0

    def _get(self, url: str) -> bytes:
        err: Exception | None = None
        for attempt in range(self.tries):
            wait = self.delay - (time.monotonic() - self._last)
            if wait > 0:
                self._sleep(wait)
            self._last = time.monotonic()
            retry_after = 0.0
            backoff = 2.0 * (attempt + 1)
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return r.read()
            except urllib.error.HTTPError as e:
                if e.code not in RETRY_STATUS:
                    raise FetchError(f"{url}: HTTP {e.code}") from None
                err = e
                if e.code == 429:  # CDN throttle: back off hard, it sends no Retry-After
                    backoff = min(60.0, 5.0 * 2 ** attempt)
                try:
                    retry_after = float(e.headers.get("Retry-After", 0))
                except (TypeError, ValueError):
                    pass
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                err = e
            if attempt < self.tries - 1:
                self._sleep(max(retry_after, backoff))
        raise FetchError(f"{url}: {err}")

    def _json(self, url: str):
        try:
            return json.loads(self._get(url))
        except ValueError as e:
            raise FetchError(f"{url}: not JSON ({e})") from None

    # -- Hugging Face ------------------------------------------------------

    def row(self, dataset: str, config: str, split: str, idx: int) -> dict:
        q = urllib.parse.urlencode({"dataset": dataset, "config": config,
                                    "split": split, "offset": idx, "length": 1})
        d = self._json(f"{VIEWER}?{q}")
        try:
            self._totals[(dataset, config, split)] = int(d["num_rows_total"])
            item = d["rows"][0]
            row = item["row"]
        except (KeyError, IndexError, TypeError, ValueError):
            raise FetchError(f"{dataset} {config}/{split}#{idx}: unexpected viewer response") from None
        if item.get("truncated_cells"):
            raise RowTruncated(f"{dataset} {config}/{split}#{idx}: cell truncated by the viewer")
        return row

    def total(self, dataset: str, config: str, split: str) -> int:
        if (dataset, config, split) not in self._totals:
            try:
                self.row(dataset, config, split, 0)
            except RowTruncated:
                pass
        return self._totals[(dataset, config, split)]

    def hub_card(self, dataset: str) -> tuple[str, str | None]:
        """(repo head sha, licence tag from the dataset card or None)."""
        d = self._json(HUB + dataset)
        try:
            sha = d["sha"]
        except (KeyError, TypeError):
            raise FetchError(f"{dataset}: Hub response has no sha") from None
        lic = (d.get("cardData") or {}).get("license")
        if isinstance(lic, list):
            lic = lic[0] if lic else None
        return sha, lic

    # -- GitHub ------------------------------------------------------------

    def git_head(self, repo: str) -> str:
        text = self._get(GIT.format(repo=repo)).decode("latin-1")
        m = re.search(r"([0-9a-f]{40}) HEAD\x00", text)
        if not m:
            raise FetchError(f"{repo}: could not read repo head")
        return m.group(1)

    def raw_json(self, repo: str, rev: str, path: str):
        return self._json(RAW.format(repo=repo, rev=rev, path=path))
