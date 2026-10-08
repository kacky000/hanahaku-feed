"""出典付きの JSON / RSS と、過去の取得結果との差分。"""

from datetime import date, datetime
from email.utils import format_datetime
from html import escape
from xml.etree import ElementTree as ET

from . import __version__
from .client import FetchResult
from .models import FeedError, NewsItem, SOURCE_URL, TERMS_URL
from .parser import _article_url


def build_document(result: FetchResult) -> dict:
    return {
        "schema_version": 1,
        "generator": f"hanahaku-feed/{__version__}",
        "source": {
            "name": "GREEN×EXPO 2027 公式ウェブサイト 新着情報",
            "url": SOURCE_URL,
            "terms_url": TERMS_URL,
        },
        "checked_at": result.checked_at,
        "fetched_at": result.fetched_at,
        "from_cache": result.from_cache,
        "not_modified": result.not_modified,
        "items": [item.to_dict() for item in result.items],
    }


def compare_items(items: list[NewsItem], previous: dict | None) -> tuple[dict, dict]:
    """初回は基準を保存し、その後は新着と変更だけを返す。一覧落ちは保持。"""
    initial = previous is None
    try:
        if initial:
            seen = {}
        else:
            if (previous["schema_version"] != 1 or previous["source_url"] != SOURCE_URL
                    or not isinstance(previous["items"], dict)):
                raise ValueError
            seen = dict(previous["items"])
            for key, value in seen.items():
                if not isinstance(value["title"], str) or not isinstance(value["categories"], list):
                    raise ValueError
                if not all(isinstance(category, str) for category in value["categories"]):
                    raise ValueError
                if date.fromisoformat(value["published_date"]).isoformat() != value["published_date"]:
                    raise ValueError
                item = NewsItem(value["title"], _article_url(value["url"]), value["published_date"], tuple(value["categories"]))
                if item.id != key or item.to_dict() != value:
                    raise ValueError
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise FeedError("差分の保存データが壊れています。state.json を確認してください。") from exc
    changes = {"initial_run": initial, "new": [], "updated": []}
    for item in items:
        value = item.to_dict()
        old = seen.get(item.id)
        if not initial:
            if old is None:
                changes["new"].append(value)
            elif old != value:
                changes["updated"].append({"before": old, "after": value})
        seen[item.id] = value
    return changes, {"schema_version": 1, "source_url": SOURCE_URL, "items": seen}


def render_rss(result: FetchResult) -> str:
    root = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(root, "channel")
    ET.SubElement(channel, "title").text = "Hanahaku Feed — GREEN×EXPO 2027 新着情報（非公式）"
    ET.SubElement(channel, "link").text = SOURCE_URL
    ET.SubElement(channel, "description").text = "公式一覧の参照用フィード。掲載情報の権利は原権利者に帰属します。"
    ET.SubElement(channel, "language").text = "ja"
    ET.SubElement(channel, "generator").text = f"Hanahaku Feed {__version__}"
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(datetime.fromisoformat(result.checked_at))
    ET.SubElement(channel, "ttl").text = "60"
    for entry in result.items:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = entry.title
        ET.SubElement(item, "link").text = entry.url
        ET.SubElement(item, "guid", {"isPermaLink": "true"}).text = entry.url
        # 公表されていない掲載「時刻」は補わず、日付を本文に表示する。
        description = f"掲載日: {entry.published_date} / 分類: {'、'.join(entry.categories)} / 出典: GREEN×EXPO 2027 公式ウェブサイト"
        ET.SubElement(item, "description").text = escape(description)
        for category in entry.categories:
            ET.SubElement(item, "category").text = category
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True) + "\n"
