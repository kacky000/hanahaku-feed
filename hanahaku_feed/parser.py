"""公式一覧の静的 HTML を読み取る。JavaScript やリンク先は実行しない。"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

from .models import FeedError, MAX_BYTES, NewsItem, ORIGIN, SOURCE_URL


class ParseError(FeedError):
    """一覧を信頼できる形で読み取れない。"""


@dataclass
class _Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)

    def text(self) -> str:
        if self.tag in {"script", "style"}:
            return ""
        return "".join(child if isinstance(child, str) else child.text() for child in self.children)

    def find(self, *, tag=None, cls=None):
        if (tag is None or self.tag == tag) and (cls is None or cls in self.attrs.get("class", "").split()):
            yield self
        for child in self.children:
            if isinstance(child, _Node):
                yield from child.find(tag=tag, cls=cls)


class _Document(HTMLParser):
    _VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("root")
        self.stack = [self.root]
        self.nodes = 0

    def handle_starttag(self, tag, attrs):
        self.nodes += 1
        if self.nodes > 30000 or len(self.stack) > 80:
            raise ParseError("HTML の構造が上限を超えています。")
        node = _Node(tag, {key: value or "" for key, value in attrs})
        self.stack[-1].children.append(node)
        if tag in {"br", "hr"}:
            node.children.append(" ")
        if tag not in self._VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self._VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _clean(text: str) -> str:
    # JSON / XML / 端末に制御文字を渡さない。
    text = "".join(c for c in text if c in "\n\r\t" or (
        (32 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF)
        and ord(c) not in range(127, 160)
    ))
    return re.sub(r"\s+", " ", text).strip()


def _article_url(href: str) -> str:
    if not href or any(c.isspace() or ord(c) < 32 for c in href):
        raise ParseError("記事の URL が不正です。")
    try:
        parsed = urlsplit(urljoin(SOURCE_URL, href))
        origin = urlsplit(ORIGIN)
        if (parsed.scheme != "https" or parsed.hostname != origin.hostname
                or parsed.port not in (None, 443) or parsed.username or parsed.password):
            raise ValueError
    except ValueError as exc:
        raise ParseError("公式サイト外または不正な記事 URL を検出しました。") from exc
    return urlunsplit(("https", origin.netloc, parsed.path, parsed.query, ""))


def parse_news(html: str) -> list[NewsItem]:
    """最新一覧1ページを解析。0件・不完全な記事・矛盾する重複はエラー。"""
    if len(html.encode("utf-8")) > MAX_BYTES:
        raise ParseError("HTML のサイズが上限を超えています。")
    document = _Document()
    document.feed(html)
    document.close()
    items = {}
    for listing in document.root.find(tag="ul", cls="c-newsList"):
        for row in listing.children:
            if not isinstance(row, _Node) or row.tag != "li":
                continue
            anchors = list(row.find(tag="a"))
            dates = list(row.find(cls="date"))
            titles = list(row.find(cls="title"))
            if len(anchors) != 1 or len(dates) != 1 or len(titles) != 1:
                raise ParseError("記事の構造が変更された可能性があります。")
            date_text = _clean(dates[0].text())
            try:
                if not re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", date_text):
                    raise ValueError
                date = datetime.strptime(date_text, "%Y.%m.%d").date().isoformat()
            except ValueError as exc:
                raise ParseError("記事の日付を読み取れません。") from exc
            title = _clean(titles[0].text())
            if not title or len(title) > 2000:
                raise ParseError("記事のタイトルが空、または長すぎます。")
            categories = tuple(dict.fromkeys(_clean(n.text()) for n in row.find(cls="cat") if _clean(n.text())))
            item = NewsItem(title, _article_url(anchors[0].attrs.get("href", "")), date, categories)
            if item.url in items and items[item.url] != item:
                raise ParseError("同じ URL に異なる記事情報があります。")
            items[item.url] = item
    if not items:
        raise ParseError("新着一覧が見つかりません。公式サイトの構造や応答を確認してください。")
    return sorted(items.values(), key=lambda item: item.published_date, reverse=True)
