"""UGC収集（要件 6）.

- SampleCollector: 同梱のサンプルJSONを読む（APIキー不要・動作確認/テスト用）。
- YouTubeCollector: YouTube Data API v3 から実データを収集（要件 6.1）。
  追加依存を避けるため標準ライブラリ(urllib)のみで実装。

収集後、観光地→動画の関連度フィルタ（要件 6.3）を適用する。
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from .config import CollectConfig
from .models import Video

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_API = "https://www.googleapis.com/youtube/v3"


# ---- 関連度フィルタ（要件 6.3） --------------------------------------------
def is_relevant(video: Video, place: str) -> bool:
    """地名がタイトル/説明文/タグに含まれるかで無関係動画を足切りする。"""
    place_low = place.lower()
    haystack = f"{video.title} {video.description} {' '.join(video.tags)}".lower()
    return place_low in haystack


def filter_relevant(videos: Iterable[Video], place: str) -> list[Video]:
    return [v for v in videos if is_relevant(v, place)]


# ---- ISO8601 duration パース ------------------------------------------------
_DUR = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def parse_duration(iso: str) -> int:
    m = _DUR.fullmatch(iso or "")
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


# ---- サンプル収集 -----------------------------------------------------------
class SampleCollector:
    """同梱サンプルから収集する（APIキー不要）。"""

    def __init__(self, data_dir: Path = DATA_DIR):
        self.data_dir = data_dir

    def collect(self, config: CollectConfig) -> list[Video]:
        path = self.data_dir / "sample_videos.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        videos = [Video.from_dict(d) for d in raw]
        videos = filter_relevant(videos, config.place)
        return videos[: config.max_videos]


# ---- YouTube Data API 収集 --------------------------------------------------
class YouTubeCollector:
    """YouTube Data API v3 から収集する。

    quota目安: search.list=100u/回, videos.list/channels.list=1u/回。
    max_videos と直近12ヶ月でquotaを抑える（要件 6.5）。
    """

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("YOUTUBE_API_KEY が必要です")
        self.api_key = api_key

    def _get(self, endpoint: str, params: dict) -> dict:
        params = {**params, "key": self.api_key}
        url = f"{_API}/{endpoint}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))

    def _build_query(self, config: CollectConfig) -> str:
        # 地名＋カテゴリ語（要件 6.3）。OR 検索でカテゴリ語の網羅を上げる。
        terms = " | ".join(config.category_terms)
        return f"{config.place} ({terms})"

    def _search_ids(self, config: CollectConfig) -> list[str]:
        after = (datetime.now(timezone.utc) - timedelta(days=30 * config.months_back)).isoformat()
        ids: list[str] = []
        token = None
        while len(ids) < config.max_videos:
            params = {
                "part": "snippet", "q": self._build_query(config), "type": "video",
                "order": "relevance", "maxResults": min(50, config.max_videos - len(ids)),
                "publishedAfter": after,
            }
            if config.region_hint:
                params["regionCode"] = config.region_hint
            if token:
                params["pageToken"] = token
            data = self._get("search", params)
            ids += [it["id"]["videoId"] for it in data.get("items", []) if it["id"].get("videoId")]
            token = data.get("nextPageToken")
            if not token:
                break
        return ids[: config.max_videos]

    def _fetch_videos(self, ids: list[str]) -> tuple[list[dict], dict[str, dict]]:
        items: list[dict] = []
        channel_ids: set[str] = set()
        for i in range(0, len(ids), 50):
            chunk = ids[i:i + 50]
            data = self._get("videos", {
                "part": "snippet,statistics,contentDetails", "id": ",".join(chunk),
            })
            for it in data.get("items", []):
                items.append(it)
                channel_ids.add(it["snippet"]["channelId"])
        channels = self._fetch_channels(list(channel_ids))
        return items, channels

    def _fetch_channels(self, ids: list[str]) -> dict[str, dict]:
        result: dict[str, dict] = {}
        for i in range(0, len(ids), 50):
            chunk = ids[i:i + 50]
            data = self._get("channels", {"part": "statistics,snippet", "id": ",".join(chunk)})
            for it in data.get("items", []):
                result[it["id"]] = it
        return result

    def collect(self, config: CollectConfig) -> list[Video]:
        ids = self._search_ids(config)
        items, channels = self._fetch_videos(ids)
        videos: list[Video] = []
        for it in items:
            sn, st = it["snippet"], it.get("statistics", {})
            ch = channels.get(sn["channelId"], {})
            ch_st = ch.get("statistics", {})
            ch_sn = ch.get("snippet", {})
            videos.append(Video(
                video_id=it["id"],
                title=sn.get("title", ""),
                description=sn.get("description", ""),
                channel_id=sn["channelId"],
                channel_title=sn.get("channelTitle", ""),
                published_at=sn.get("publishedAt", ""),
                duration_seconds=parse_duration(it.get("contentDetails", {}).get("duration", "")),
                view_count=int(st.get("viewCount", 0)),
                like_count=int(st.get("likeCount", 0)),
                comment_count=int(st.get("commentCount", 0)),
                tags=sn.get("tags", []),
                channel_country=ch_sn.get("country"),
                subscriber_count=(None if ch_st.get("hiddenSubscriberCount")
                                  else int(ch_st.get("subscriberCount", 0)) or None),
                subscriber_hidden=bool(ch_st.get("hiddenSubscriberCount")),
            ))
        return filter_relevant(videos, config.place)[: config.max_videos]


def get_collector(config: CollectConfig, force_sample: bool = False):
    """APIキーがあれば実収集、なければサンプル（要件 6.1）。"""
    if not force_sample and config.has_api_key():
        return YouTubeCollector(config.api_key)
    return SampleCollector()
