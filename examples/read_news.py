"""導入先の Python コードから新着情報を読み取る例。"""

from hanahaku_feed.client import Client
from hanahaku_feed.models import FeedError

try:
    result = Client(".hanahaku-cache").fetch()
except FeedError as exc:
    raise SystemExit(f"取得できませんでした: {exc}")

for item in result.items:
    print(f"{item.published_date} [{', '.join(item.categories)}] {item.title}\n{item.url}")
