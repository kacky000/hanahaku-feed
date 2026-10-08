# 必要な場合だけ定期取得する

このファイルは設定例です。ツールのインストールではスケジュールを登録しません。

利用条件を確認し、利用者の端末や権限を持つサーバーのスケジューラーから次のコマンドを実行します。

```sh
/path/to/hanahaku-feed/.venv/bin/hanahaku-feed fetch \
  --output-dir /path/to/hanahaku-feed/data \
  --cache-dir /path/to/hanahaku-feed/.hanahaku-cache
```

`/path/to/hanahaku-feed` は自分の保存先に置き換えます。6時間ごとなど、必要最低限の頻度を指定してください。ログの保存先も自分で選びます。

同じキャッシュと比較用データを保持してください。毎回新しい環境で実行すると、取得頻度の抑制と差分検出が働きません。公開CIのログや成果物に取得データをアップロードしないでください。

ツールはメール・チャットへの送信を行いません。通知を別途作る場合は `changes.json` の `initial_run` が `false` で、新着または変更がある場合だけ処理すると、不要な通知を減らせます。
