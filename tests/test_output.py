import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from hanahaku_feed.client import FetchResult
from hanahaku_feed.cli import main
from hanahaku_feed.models import FeedError, NewsItem
from hanahaku_feed.output import build_document, compare_items, render_rss

ITEM = NewsItem("架空の案内 & 展示", "https://expo2027yokohama.or.jp/news/detail/example-a.html", "2026-10-08", ("お知らせ",))
RESULT = FetchResult([ITEM], "2026-10-08T03:00:00+00:00", "2026-10-08T03:00:00+00:00")


class OutputTests(unittest.TestCase):
    def test_初回を全件新着と誤認しない(self):
        changes, state = compare_items([ITEM], None)
        self.assertTrue(changes["initial_run"])
        self.assertEqual(changes["new"], [])
        self.assertIn(ITEM.id, state["items"])

    def test_新着と変更を区別する(self):
        _, state = compare_items([ITEM], None)
        updated = NewsItem("変更済み", ITEM.url, ITEM.published_date, ITEM.categories)
        new = NewsItem("新着", "https://expo2027yokohama.or.jp/news/detail/example-b.html", "2026-10-09", ())
        changes, _ = compare_items([updated, new], state)
        self.assertEqual(changes["new"][0]["title"], "新着")
        self.assertEqual(changes["updated"][0]["before"]["title"], ITEM.title)
        self.assertEqual(changes["updated"][0]["after"]["title"], "変更済み")

    def test_一覧から一度消えても再登場を新着と誤認しない(self):
        _, state = compare_items([ITEM], None)
        _, absent_state = compare_items([], state)
        changes, _ = compare_items([ITEM], absent_state)
        self.assertEqual(changes["new"], [])
        self.assertEqual(changes["updated"], [])

    def test_壊れた状態を初回扱いにしない(self):
        with self.assertRaises(FeedError):
            compare_items([ITEM], {"schema_version": 1, "items": []})

    def test_JSONには出典と取得時刻を含める(self):
        doc = build_document(RESULT)
        self.assertEqual(doc["source"]["url"], "https://expo2027yokohama.or.jp/news/index.html")
        self.assertEqual(doc["items"][0]["published_date"], "2026-10-08")
        self.assertEqual(doc["checked_at"], "2026-10-08T03:00:00+00:00")

    def test_RSSをXMLとして解釈でき本文にHTMLを注入できない(self):
        title = '<script>alert("x")</script> & 案内'
        unsafe = NewsItem(title, ITEM.url, ITEM.published_date, ("<img src=x onerror=x>",))
        result = FetchResult([unsafe], RESULT.checked_at, RESULT.fetched_at)
        root = ET.fromstring(render_rss(result))
        self.assertIsNone(root.find(".//script"))
        self.assertEqual(root.findtext("channel/item/title"), title)
        self.assertNotIn("<img", root.findtext("channel/item/description"))
        self.assertEqual(root.findtext("channel/item/link"), ITEM.url)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.args = ["fetch", "--output-dir", str(self.base / "data"), "--cache-dir", str(self.base / "cache")]
        for context in (redirect_stdout(StringIO()), redirect_stderr(StringIO())):
            context.__enter__()
            self.addCleanup(context.__exit__, None, None, None)

    def test_CLIでJSONとRSSと差分を出力する(self):
        with patch("hanahaku_feed.cli.Client.fetch", return_value=RESULT):
            self.assertEqual(main(self.args), 0)
            first = json.loads((self.base / "data/changes.json").read_text(encoding="utf-8"))
            self.assertTrue(first["initial_run"])
            self.assertEqual(main(self.args), 0)
        doc = json.loads((self.base / "data/news.json").read_text(encoding="utf-8"))
        changes = json.loads((self.base / "data/changes.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["items"][0]["title"], ITEM.title)
        self.assertFalse(changes["initial_run"])
        self.assertEqual(changes["new"], [])
        self.assertEqual(ET.parse(self.base / "data/news.xml").findtext("channel/item/link"), ITEM.url)

    def test_通信失敗では前回の出力も状態も変更しない(self):
        with patch("hanahaku_feed.cli.Client.fetch", return_value=RESULT):
            main(self.args)
        paths = [self.base / "data/news.json", self.base / "data/news.xml", self.base / "data/changes.json", self.base / "cache/state.json"]
        before = [path.read_bytes() for path in paths]
        with patch("hanahaku_feed.cli.Client.fetch", side_effect=FeedError("通信失敗")):
            self.assertEqual(main(self.args), 1)
        self.assertEqual([path.read_bytes() for path in paths], before)

    def test_出力失敗では差分の基準を進めない(self):
        with patch("hanahaku_feed.cli.Client.fetch", return_value=RESULT), patch("hanahaku_feed.cli.atomic_write", side_effect=OSError("書き込めません")):
            self.assertEqual(main(self.args), 1)
        self.assertFalse((self.base / "cache/state.json").exists())

    def test_RSSだけを選べる(self):
        with patch("hanahaku_feed.cli.Client.fetch", return_value=RESULT):
            self.assertEqual(main(self.args + ["--format", "rss"]), 0)
        self.assertTrue((self.base / "data/news.xml").exists())
        self.assertFalse((self.base / "data/news.json").exists())

    def test_nullの状態ファイルを初回と誤認しない(self):
        path = self.base / "cache/state.json"
        path.parent.mkdir()
        path.write_text("null", encoding="utf-8")
        with patch("hanahaku_feed.cli.Client.fetch", side_effect=AssertionError("不正な比較基準で取得")):
            self.assertEqual(main(self.args), 1)
        self.assertEqual(path.read_text(encoding="utf-8"), "null")


if __name__ == "__main__":
    unittest.main()
