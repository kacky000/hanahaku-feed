"""端末やジョブランナーから使う CLI。定期実行の登録は行わない。"""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .client import Client
from .models import FeedError
from .output import build_document, compare_items, render_rss
from .storage import atomic_write, directory_lock, json_text


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="横浜花博 GREEN×EXPO 2027 の公式新着情報をローカルに取得します。")
    parser.add_argument("--version", action="version", version=f"hanahaku-feed {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch", help="新着情報を取得し、JSON・RSS・差分を保存")
    fetch.add_argument("--output-dir", type=Path, default=Path("data"), help="出力先ディレクトリ（既定: data）")
    fetch.add_argument("--cache-dir", type=Path, default=Path(".hanahaku-cache"), help="キャッシュと比較用データの保存先")
    fetch.add_argument("--format", choices=("json", "rss", "both"), default="both", help="出力形式（既定: both）")
    args = parser.parse_args(argv)
    try:
        with directory_lock(args.cache_dir, ".run.lock"):
            state_path = args.cache_dir / "state.json"
            previous = None
            if state_path.exists():
                if state_path.stat().st_size > 10 * 1024 * 1024:
                    raise FeedError("差分の保存データが上限の 10 MiB を超えました。")
                previous = json.loads(state_path.read_text(encoding="utf-8"))
                if not isinstance(previous, dict):
                    raise FeedError("差分の保存データが壊れています。state.json を確認してください。")
                # 不正な比較用データを検出してから通信する。
                compare_items([], previous)
            result = Client(args.cache_dir).fetch()
            changes, state = compare_items(result.items, previous)
            changes["checked_at"] = result.checked_at
            changes["source_url"] = build_document(result)["source"]["url"]
            outputs = {"changes.json": json_text(changes)}
            if args.format in ("json", "both"):
                outputs["news.json"] = json_text(build_document(result))
            if args.format in ("rss", "both"):
                outputs["news.xml"] = render_rss(result)
            state_text = json_text(state)
            if len(state_text.encode("utf-8")) > 10 * 1024 * 1024:
                raise FeedError("差分の保存データが上限を超えます。過去の state.json を退避してください。")
            for name, contents in outputs.items():
                atomic_write(args.output_dir / name, contents)
            # 出力できた場合だけ比較基準を進める。
            atomic_write(state_path, state_text)
        mode = "キャッシュ利用" if result.from_cache else "更新確認・変更なし" if result.not_modified else "取得完了"
        count = len(result.items)
        print(f"{mode}: {count} 件。新着 {len(changes['new'])} 件、変更 {len(changes['updated'])} 件。保存先: {args.output_dir}")
        if changes["initial_run"]:
            print("初回の比較基準を保存しました。次回から新着・変更を判定します。")
        return 0
    except (FeedError, OSError, ValueError) as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
