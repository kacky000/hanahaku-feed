# Hanahaku Feed 🌱

横浜花博 **GREEN×EXPO 2027** の公式新着一覧を取得し、JSON・RSS・新着差分をローカルに保存する非公式ツールです。Python ライブラリとしても、コマンドとしても使えます。

公式サイトを何度も開いて確認する作業を減らし、個人の情報収集や、掲載許可を得たシステムへの組み込みに利用できます。

## できること

- タイトル、掲載日、複数の分類、公式記事・PDFの参照URLを取得
- 出典・取得日時を含む JSON と RSS 2.0 を生成
- 初回を基準に、新着とタイトル・日付・分類の変更を検出
- 一覧から外れた記事も比較履歴に残し、再登場を新着と誤認しない
- 1時間キャッシュ、ETag / Last-Modified、robots.txt 確認で取得負荷を抑制
- 形式変更や通信障害を検出し、前回の正常な出力を保持

Python 3.11 以上。実行時の外部ライブラリ、APIキー、ブラウザ、ログインは不要です。

## インストールと実行

このリポジトリをダウンロードし、プロジェクトのディレクトリで実行します。

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
hanahaku-feed fetch
```

Windows の仮想環境の有効化は `.venv\Scripts\Activate.ps1` を使用します。
インストールせず、プロジェクトのディレクトリから `python3 -m hanahaku_feed fetch` でも実行できます。
PyPI への公開は行っていないため、パッケージ名だけを指定したインストールは案内していません。

初回実行時の表示例（件数は情報源によって変わります）:

```text
取得完了: 20 件。新着 0 件、変更 0 件。保存先: data
初回の比較基準を保存しました。次回から新着・変更を判定します。
```

```sh
# 保存先を指定
hanahaku-feed fetch --output-dir ./data --cache-dir ./.hanahaku-cache

# JSON または RSS のみ。差分 JSON は常に保存
hanahaku-feed fetch --format json
hanahaku-feed fetch --format rss

# コマンド一覧
hanahaku-feed --help
hanahaku-feed fetch --help
```

| ファイル | 内容 |
| --- | --- |
| `data/news.json` | 最新一覧、出典、掲載日、取得日時 |
| `data/news.xml` | 個人のフィードリーダーなどで利用する RSS |
| `data/changes.json` | 初回かどうか、新着、変更前後の情報 |
| `.hanahaku-cache/cache.json` | 条件付き取得用のキャッシュ |
| `.hanahaku-cache/state.json` | これまでに確認した記事の比較用データ |

取得データ・キャッシュは Git 管理と配布物から除外しています。API の認証情報や個人情報を取得する機能はありません。

## Python から利用

```python
from hanahaku_feed.client import Client
from hanahaku_feed.output import build_document

result = Client(cache_dir=".hanahaku-cache").fetch()
document = build_document(result)

for item in document["items"]:
    print(item["published_date"], item["title"], item["url"])
```

ライブラリの失敗は `hanahaku_feed.models.FeedError` で捕捉できます。
CLI は取得・保存に失敗した場合に終了コード `1`、引数が不正な場合に `2` を返します。

## JSON の形式

以下は説明用の架空データです。実際の記事を転載したものではありません。

```json
{
  "schema_version": 1,
  "generator": "hanahaku-feed/0.1.0",
  "source": {
    "name": "GREEN×EXPO 2027 公式ウェブサイト 新着情報",
    "url": "https://expo2027yokohama.or.jp/news/index.html",
    "terms_url": "https://expo2027yokohama.or.jp/terms/"
  },
  "checked_at": "2026-10-08T03:00:00+00:00",
  "fetched_at": "2026-10-08T03:00:00+00:00",
  "from_cache": false,
  "not_modified": false,
  "items": []
}
```

`items` の各要素は `id`、`title`、`url`、`published_date`、`categories` を持ちます。`id` は参照URLの SHA-256 で、タイトルが変わっても同じ記事として比較できます。

- `checked_at`: 情報源を最後に確認した時刻。キャッシュを読むだけでは更新しません。
- `fetched_at`: HTML 本体を取得した時刻。HTTP 304 では前回の値を保持します。
- `published_date`: 公式一覧に掲載された日付。イベントの開催日ではありません。
- RSS は公表されていない掲載時刻を補わず、日付を説明欄に載せます。
- `changes.json` の初回は `initial_run: true`、新着・変更は空です。2回目以降に前回までの保存データと比較します。

## 定期取得

ツール自身は常駐せず、1回の実行で終了します。[定期実行の設定例](examples/scheduling.md)を参考に、利用者の環境で必要な場合だけ設定してください。このリポジトリを取得しただけで定期実行は始まりません。

取得頻度は6時間に1回程度を推奨します。同じキャッシュを再利用してください。1時間以内はネットワークに接続せず、期限後もサーバーが対応していれば条件付き取得を行います。

## 情報源と利用条件

取得元は [協会公式の新着一覧](https://expo2027yokohama.or.jp/news/index.html) です。協会公認のAPI・公式RSSではありません。

**MITライセンスは本ツールのコードに適用されます。取得した公式情報はMITライセンスになりません。**

協会の[利用規約](https://expo2027yokohama.or.jp/terms/)には掲載情報の私的利用を超える利用や第三者への提供について制限が記載されています。本ツールは取得結果を利用者のローカル環境に保存します。生成JSON・RSSをサイトに掲載したり第三者に配信したりする場合は、権利者の許可など必要な利用条件を別途確認してください。出典を書くだけで再公開が許可されるわけではありません。

本文・画像・PDFファイルの内容は取得しません。ロゴやマスコット画像も同梱していません。CI・テストは架空データだけを使用します。

## 制限と障害時の動作

- 対象は最新一覧の**1ページ**です。全記事・全イベント・開催概要・チケット料金を網羅するAPIではありません。
- 確認の間に記事が一覧から外れた場合、その記事を取得できないことがあります。履歴の完全性は保証しません。
- 詳細本文だけの変更は検出しません。タイトルなど一覧の情報を比較します。
- 公式サイトの構造・URL・利用条件変更によって取得できなくなることがあります。0件や壊れた記事を成功として保存しません。
- robots.txt が取得を禁止する場合は停止します。404/410 の場合を除き、確認不能時も停止します。robots.txt は転載許可を示すものではありません。
- 接続先は2つのHTTPS URLに固定し、リダイレクトは拒否します。任意のURLやAPIキーを受け付けません。
- 読み取りのソケットタイムアウトは20秒、各応答の上限は2 MiBです。ネットワーク障害の自動再試行はありません。
- 出力はファイル単位で一時ファイルから置換します。複数ファイル全体のトランザクションではありません。保存失敗時は比較基準を進めず、次回再実行で差分を再出力できます。
- 同じキャッシュを使った同時実行はロックで停止します。強制終了でロックが残った場合は、実行中のプロセスがないことを確認してから `.hanahaku-cache/.run.lock` と `.hanahaku-cache/.fetch.lock` を取り除いてください。
- 取得元の文字列をWebページに組み込む際は、`innerHTML` ではなくテキストとして扱ってください。

## 開発

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q hanahaku_feed
```

テストにインターネット接続は不要です。実サイトの確認は `hanahaku-feed fetch` で明示的に行います。

変更提案は [CONTRIBUTING.md](CONTRIBUTING.md)、脆弱性報告は [SECURITY.md](SECURITY.md) を参照してください。コードは [MIT License](LICENSE) で公開します。
