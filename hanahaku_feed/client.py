"""公開一覧の低頻度取得。HTTP の認証・Cookie・任意URL入力を持たない。"""

import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

from .models import FeedError, MAX_BYTES, NewsItem, ROBOTS_URL, SOURCE_URL, USER_AGENT
from .parser import parse_news
from .storage import atomic_write, directory_lock, json_text

CACHE_SECONDS = 3600


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class FetchResult:
    items: list[NewsItem]
    checked_at: str
    fetched_at: str
    from_cache: bool = False
    not_modified: bool = False


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise FeedError("取得先からリダイレクトされました。公式 URL の変更を確認してください。")


def _read_body(response) -> bytes:
    body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise FeedError("取得データが 2 MiB の上限を超えました。")
    return body


def _request(url: str, headers: dict[str, str]) -> HttpResponse:
    if url not in {SOURCE_URL, ROBOTS_URL}:
        raise FeedError("許可された情報源以外には接続できません。")
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity", **headers})
    try:
        with build_opener(_NoRedirect()).open(request, timeout=20) as response:
            return HttpResponse(response.status, {k.lower(): v for k, v in response.headers.items()}, _read_body(response))
    except HTTPError as exc:
        with exc:
            return HttpResponse(exc.code, {k.lower(): v for k, v in exc.headers.items()}, b"")
    except (URLError, TimeoutError, OSError, ValueError, HTTPException) as exc:
        raise FeedError(f"公式サイトから取得できませんでした（{type(exc).__name__}）。") from exc


def _header(value) -> str:
    if not isinstance(value, str) or len(value) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise FeedError("HTTP キャッシュ情報が不正です。")
    return value


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")


class Client:
    """同じ cache_dir を再利用すると、1時間以内は外部通信を省略する。"""

    def __init__(self, cache_dir: Path | str = ".hanahaku-cache"):
        self.cache_dir = Path(cache_dir)

    def _load_cache(self):
        path = self.cache_dir / "cache.json"
        if not path.exists():
            return None
        try:
            if path.stat().st_size > MAX_BYTES * 2 + 8192:
                raise ValueError
            data = json.loads(path.read_text(encoding="utf-8"))
            if data["schema_version"] != 1 or not isinstance(data["html"], str):
                raise ValueError
            if type(data["checked_epoch"]) not in (int, float) or not math.isfinite(data["checked_epoch"]):
                raise ValueError
            for key in ("fetched_at", "checked_at"):
                if datetime.fromisoformat(data[key]).tzinfo is None:
                    raise ValueError
            for key in ("etag", "last_modified"):
                _header(data[key])
            return data
        except (ValueError, KeyError, TypeError, OSError, OverflowError) as exc:
            raise FeedError("キャッシュが壊れています。cache.json を退避してから再実行してください。") from exc

    def fetch(self) -> FetchResult:
        with directory_lock(self.cache_dir, ".fetch.lock"):
            return self._fetch()

    def _fetch(self) -> FetchResult:
        now = time.time()
        cached = self._load_cache()
        if cached and 0 <= now - cached["checked_epoch"] < CACHE_SECONDS:
            return FetchResult(parse_news(cached["html"]), cached["checked_at"], cached["fetched_at"], from_cache=True)

        robots = _request(ROBOTS_URL, {"Accept": "text/plain"})
        delay = 1
        if robots.status == 200:
            if robots.headers.get("content-type", "").split(";")[0].strip().lower() != "text/plain":
                raise FeedError("robots.txt の形式を確認できないため取得を停止しました。")
            rules = RobotFileParser(ROBOTS_URL)
            try:
                rules.parse(robots.body.decode("utf-8-sig").splitlines())
            except UnicodeDecodeError as exc:
                raise FeedError("robots.txt の文字コードを読み取れません。") from exc
            if not rules.can_fetch(USER_AGENT, SOURCE_URL):
                raise FeedError("robots.txt により新着一覧の取得が禁止されています。")
            delay = max(delay, rules.crawl_delay(USER_AGENT) or 0)
            rate = rules.request_rate(USER_AGENT)
            if rate and rate.requests > 0:
                delay = max(delay, rate.seconds / rate.requests)
        elif robots.status not in (404, 410):
            raise FeedError(f"robots.txt を確認できません（HTTP {robots.status}）。取得を停止しました。")
        if delay > 60:
            raise FeedError("情報源が長い取得間隔を指定しているため、今回の取得を停止しました。")
        time.sleep(delay)

        headers = {"Accept": "text/html"}
        if cached:
            if cached["etag"]:
                headers["If-None-Match"] = cached["etag"]
            if cached["last_modified"]:
                headers["If-Modified-Since"] = cached["last_modified"]
        response = _request(SOURCE_URL, headers)
        checked_at = _iso(now)
        not_modified = response.status == 304
        if not_modified:
            if cached is None:
                raise FeedError("キャッシュがない状態で HTTP 304 が返りました。")
            html = cached["html"]
            fetched_at = cached["fetched_at"]
        elif response.status == 200:
            if response.headers.get("content-type", "").split(";")[0].strip().lower() != "text/html":
                raise FeedError("新着一覧が HTML として返されませんでした。")
            try:
                html = response.body.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise FeedError("新着一覧の文字コードを読み取れません。") from exc
            fetched_at = checked_at
        else:
            raise FeedError(f"新着一覧を取得できません（HTTP {response.status}）。自動再試行は行いません。")
        items = parse_news(html)
        fallback = cached if not_modified else {}
        data = {
            "schema_version": 1, "checked_epoch": now, "checked_at": checked_at,
            "fetched_at": fetched_at, "html": html,
            "etag": _header(response.headers.get("etag", fallback.get("etag", ""))),
            "last_modified": _header(response.headers.get("last-modified", fallback.get("last_modified", ""))),
        }
        atomic_write(self.cache_dir / "cache.json", json_text(data))
        return FetchResult(items, checked_at, fetched_at, not_modified=not_modified)
