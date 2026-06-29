"""UGC収集（要件 6）.

- SampleCollector: 同梱のサンプルJSONを読む（APIキー不要・動作確認/テスト用）。
- YouTubeCollector: YouTube Data API v3 から実データを収集（要件 6.1）。
  追加依存を避けるため標準ライブラリ(urllib)のみで実装。

収集後、観光地→動画の関連度フィルタ（要件 6.3）を適用する。
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from .config import CollectConfig
from .models import Video

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_API = "https://www.googleapis.com/youtube/v3"


# ---- 関連度フィルタ（要件 6.3 / インバウンド対応） -------------------------
def is_relevant(video: Video, aliases: list[str]) -> bool:
    """地名のいずれかの表記がタイトル/説明文/タグに含まれれば通す。

    日本語名だけでなく多言語表記（Takayama, 다카야마 等）で照合することで、
    訪日客の外国語UGCを取りこぼさない。
    """
    haystack = f"{video.title} {video.description} {' '.join(video.tags)}".lower()
    return any(a.lower() in haystack for a in aliases)


def filter_relevant(videos: Iterable[Video], aliases: list[str]) -> list[Video]:
    return [v for v in videos if is_relevant(v, aliases)]


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
        videos = filter_relevant(videos, config.resolved_aliases())
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
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")
            raise RuntimeError(f"YouTube API {e.code} エラー（{endpoint}）: {body[:600]}") from None

    def _search_one(self, name: str, after: str, limit: int, seen: set[str]) -> list[str]:
        """1つの地名表記で検索して動画IDを集める（市場別収集の1単位）。"""
        ids: list[str] = []
        token = None
        while len(ids) < limit:
            params = {
                "part": "snippet", "q": name, "type": "video",
                "order": "relevance", "maxResults": min(50, limit - len(ids)),
                "publishedAfter": after,
            }
            if config_region := getattr(self, "_region_hint", None):
                params["regionCode"] = config_region
            if token:
                params["pageToken"] = token
            data = self._get("search", params)
            for it in data.get("items", []):
                vid = it["id"].get("videoId")
                if vid and vid not in seen:
                    seen.add(vid)
                    ids.append(vid)
            token = data.get("nextPageToken")
            if not token:
                break
        return ids

    def _search_ids(self, config: CollectConfig) -> list[str]:
        # YouTube は RFC3339（末尾Z・マイクロ秒なし）を要求。isoformat()の "+00:00" だと400になる。
        after = (datetime.now(timezone.utc) - timedelta(days=30 * config.months_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self._region_hint = config.region_hint
        # 地名の表記ごとに個別に検索してマージする（市場別収集）。
        # 全表記を1回でOR検索すると日本語動画ばかり返り、海外市場を取りこぼすため。
        names = config.resolved_aliases()[:8]
        per_name = max(15, -(-config.max_videos // max(1, len(names))))  # 各表記への配分（切り上げ）
        seen: set[str] = set()
        ids: list[str] = []
        for name in names:
            if len(ids) >= config.max_videos:
                break
            ids += self._search_one(name, after, per_name, seen)
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
        videos = filter_relevant(videos, config.resolved_aliases())[: config.max_videos]
        if config.fetch_comments:
            for v in videos:
                v.comments = self._fetch_comments(v.video_id, config.max_comments)
        return videos

    def _fetch_comments(self, video_id: str, max_comments: int) -> list[str]:
        """上位コメントを取得（コメント無効動画などは静かにスキップ）。"""
        try:
            data = self._get("commentThreads", {
                "part": "snippet", "videoId": video_id,
                "maxResults": min(100, max_comments), "order": "relevance",
                "textFormat": "plainText",
            })
        except Exception:
            return []
        out = []
        for it in data.get("items", []):
            sn = it.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
            text = sn.get("textDisplay")
            if text:
                out.append(text)
        return out[:max_comments]


def get_collector(config: CollectConfig, force_sample: bool = False):
    """APIキーがあれば実収集、なければサンプル（要件 6.1）。"""
    if not force_sample and config.has_api_key():
        return YouTubeCollector(config.api_key)
    return SampleCollector()
