"""取得データの形式と固定の情報源。"""

from dataclasses import asdict, dataclass
from hashlib import sha256

ORIGIN = "https://expo2027yokohama.or.jp"
SOURCE_URL = ORIGIN + "/news/index.html"
ROBOTS_URL = ORIGIN + "/robots.txt"
TERMS_URL = ORIGIN + "/terms/"
MAX_BYTES = 2 * 1024 * 1024
USER_AGENT = "HanahakuFeed/0.1 (unofficial local news reader)"


class FeedError(Exception):
    """利用者に知らせる取得・形式エラー。"""


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    published_date: str
    categories: tuple[str, ...]

    @property
    def id(self) -> str:
        return sha256(self.url.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return {"id": self.id, **asdict(self), "categories": list(self.categories)}
