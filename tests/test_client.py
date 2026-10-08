import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request

from hanahaku_feed.client import Client, HttpResponse, _NoRedirect, _read_body, _request
from hanahaku_feed.models import FeedError, MAX_BYTES, ROBOTS_URL, SOURCE_URL

HTML = Path(__file__).with_name("fixtures").joinpath("news.html").read_bytes()
ALLOW = HttpResponse(200, {"content-type": "text/plain"}, b"User-agent: *\nDisallow: /mt/\n")


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.client = Client(self.path)
        self.sleep = patch("hanahaku_feed.client.time.sleep").start()
        self.addCleanup(patch.stopall)

    def ok(self, html=HTML):
        return HttpResponse(200, {"content-type": "text/html; charset=UTF-8", "etag": '"version1"'}, html)

    def test_取得後の再実行でネットワークに接続しない(self):
        with patch("hanahaku_feed.client._request", side_effect=[ALLOW, self.ok()]) as request:
            result = self.client.fetch()
        self.assertEqual(len(result.items), 2)
        self.assertFalse(result.from_cache)
        self.assertEqual([call.args[0] for call in request.call_args_list], [ROBOTS_URL, SOURCE_URL])
        with patch("hanahaku_feed.client._request", side_effect=AssertionError("不要な通信")):
            cached = self.client.fetch()
        self.assertTrue(cached.from_cache)
        self.assertEqual(cached.items, result.items)

    def test_robotsが禁止すると一覧を取得しない(self):
        deny = HttpResponse(200, {"content-type": "text/plain"}, b"User-agent: *\nDisallow: /news/\n")
        with patch("hanahaku_feed.client._request", side_effect=[deny]), self.assertRaises(FeedError):
            self.client.fetch()
        self.assertFalse((self.path / "cache.json").exists())

    def test_robotsの障害では取得を停止する(self):
        for code in (403, 429, 500):
            with self.subTest(code=code), patch("hanahaku_feed.client._request", return_value=HttpResponse(code, {}, b"")), self.assertRaises(FeedError):
                self.client.fetch()

    def test_robotsが存在しないときは一覧を取得できる(self):
        with patch("hanahaku_feed.client._request", side_effect=[HttpResponse(404, {}, b""), self.ok()]):
            self.assertEqual(len(self.client.fetch().items), 2)

    def test_期限切れのキャッシュを条件付き取得し304で保持する(self):
        with patch("hanahaku_feed.client.time.time", return_value=1700000000), patch("hanahaku_feed.client._request", side_effect=[ALLOW, self.ok()]):
            first = self.client.fetch()
        with patch("hanahaku_feed.client.time.time", return_value=1700007200), patch("hanahaku_feed.client._request", side_effect=[ALLOW, HttpResponse(304, {}, b"")]) as request:
            second = self.client.fetch()
        self.assertEqual(second.items, first.items)
        self.assertTrue(second.not_modified)
        self.assertEqual(second.fetched_at, first.fetched_at)
        self.assertNotEqual(second.checked_at, first.checked_at)
        self.assertEqual(request.call_args.args[1]["If-None-Match"], '"version1"')

    def test_壊れた新しいHTMLで前回のキャッシュを壊さない(self):
        with patch("hanahaku_feed.client.time.time", return_value=1700000000), patch("hanahaku_feed.client._request", side_effect=[ALLOW, self.ok()]):
            self.client.fetch()
        previous = (self.path / "cache.json").read_bytes()
        with patch("hanahaku_feed.client.time.time", return_value=1700007200), patch("hanahaku_feed.client._request", side_effect=[ALLOW, self.ok(b"maintenance")]), self.assertRaises(FeedError):
            self.client.fetch()
        self.assertEqual((self.path / "cache.json").read_bytes(), previous)

    def test_キャッシュなしの304は成功にしない(self):
        with patch("hanahaku_feed.client._request", side_effect=[ALLOW, HttpResponse(304, {}, b"")]), self.assertRaises(FeedError):
            self.client.fetch()

    def test_取得上限を超えたレスポンスを拒否する(self):
        import io
        with self.assertRaises(FeedError):
            _read_body(io.BytesIO(b"x" * (MAX_BYTES + 1)))

    def test_リダイレクトで別サーバーへ接続しない(self):
        handler = _NoRedirect()
        with self.assertRaises(FeedError):
            handler.redirect_request(Request(SOURCE_URL), None, 302, "", {}, "http://127.0.0.1/")

    def test_破損したキャッシュを黙って使わない(self):
        (self.path / "cache.json").write_text('{"checked_at": "bad"}', encoding="utf-8")
        with self.assertRaises(FeedError):
            self.client.fetch()

    def test_競合実行で既存のロックを消さない(self):
        lock = self.path / ".fetch.lock"
        lock.write_text("既存のロック", encoding="utf-8")
        with self.assertRaises(FeedError):
            self.client.fetch()
        self.assertEqual(lock.read_text(encoding="utf-8"), "既存のロック")

    def test_失敗後にロックを解放する(self):
        with patch("hanahaku_feed.client._request", side_effect=FeedError("通信失敗")), self.assertRaises(FeedError):
            self.client.fetch()
        self.assertFalse((self.path / ".fetch.lock").exists())

    def test_ニュース以外のコンテンツ形式を拒否する(self):
        response = HttpResponse(200, {"content-type": "application/octet-stream"}, HTML)
        with patch("hanahaku_feed.client._request", side_effect=[ALLOW, response]), self.assertRaises(FeedError):
            self.client.fetch()

    def test_許可以外の通信先を拒否する(self):
        with self.assertRaises(FeedError):
            _request("http://127.0.0.1/", {})

    def test_HTTP応答が途中で切れた場合も取得エラーにする(self):
        from http.client import IncompleteRead
        with patch("hanahaku_feed.client.build_opener") as opener:
            opener.return_value.open.side_effect = IncompleteRead(b"partial")
            with self.assertRaises(FeedError):
                _request(SOURCE_URL, {})

    def test_キャッシュからHTTPヘッダーに改行を渡さない(self):
        with patch("hanahaku_feed.client._request", side_effect=[ALLOW, self.ok()]):
            self.client.fetch()
        path = self.path / "cache.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["etag"] = "x\r\nInjected: true"
        path.write_text(json.dumps(data), encoding="utf-8")
        with patch("hanahaku_feed.client._request", side_effect=AssertionError("不正ヘッダーで通信")), self.assertRaises(FeedError):
            self.client.fetch()


if __name__ == "__main__":
    unittest.main()
