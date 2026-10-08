import unittest
from pathlib import Path

from hanahaku_feed.parser import ParseError, parse_news


HTML = Path(__file__).with_name("fixtures").joinpath("news.html").read_text(encoding="utf-8")


class ParserTests(unittest.TestCase):
    def test_記事の日付と分類と参照先を抽出する(self):
        items = parse_news(HTML)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, "テスト用の花と緑 & 学びのお知らせ")
        self.assertEqual(items[0].published_date, "2026-10-08")
        self.assertEqual(items[0].categories, ("お知らせ", "活動報告"))
        self.assertEqual(items[0].url, "https://expo2027yokohama.or.jp/news/detail/example-a.html")
        self.assertEqual(items[1].title, "架空の展示 イベントのご案内")
        self.assertTrue(items[1].url.endswith(".pdf"))

    def test_一覧外のリンクを含めない(self):
        items = parse_news(HTML.replace("<nav>", '<nav><a href="/news/detail/other.html">その他</a>'))
        self.assertEqual(len(items), 2)

    def test_構造変更を空の成功として扱わない(self):
        with self.assertRaises(ParseError):
            parse_news("<html><p>メンテナンス中です</p></html>")

    def test_存在しない日付を拒否する(self):
        with self.assertRaises(ParseError):
            parse_news(HTML.replace("2026.10.08", "2026.02.30"))

    def test_不正なURLを拒否する(self):
        for url in ("javascript:alert(1)", "http://127.0.0.1/", "https://attacker.example/", "//attacker.example/", "https://expo2027yokohama.or.jp@attacker.example/"):
            with self.subTest(url=url), self.assertRaises(ParseError):
                parse_news(HTML.replace("/news/detail/example-a.html", url))

    def test_同一URLの異なる内容を黙って捨てない(self):
        changed = HTML.replace("テスト用の花と緑 &amp; 学びのお知らせ", "異なるタイトル", 1)
        with self.assertRaises(ParseError):
            parse_news(changed)

    def test_極端に深いHTMLを拒否する(self):
        with self.assertRaises(ParseError):
            parse_news("<div>" * 1000 + HTML + "</div>" * 1000)

    def test_値のない属性も制御されたエラーにする(self):
        with self.assertRaises(ParseError):
            parse_news(HTML.replace('class="c-newsList"', 'class'))

    def test_XMLで使えない文字を除去する(self):
        items = parse_news(HTML.replace("テスト用", "テスト\uffff用"))
        self.assertNotIn("\uffff", items[0].title)


if __name__ == "__main__":
    unittest.main()
