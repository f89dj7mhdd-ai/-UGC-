"""エンゲージメント指標の集計（要件 7）.

エンゲージメント数 = いいね + コメント。
エンゲージメント率 = エンゲージメント数 / 登録者数（非公開は除外）。
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Sequence

from .models import Video


@dataclass
class EngagementSummary:
    count: int
    total_views: int
    total_engagement: int
    avg_engagement: float
    median_engagement: float
    avg_engagement_rate: float | None  # 率を出せた動画のみで平均
    rate_coverage: int                 # 率を算出できた動画数（登録者数公開分）

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def summarize(videos: Sequence[Video]) -> EngagementSummary:
    if not videos:
        return EngagementSummary(0, 0, 0, 0.0, 0.0, None, 0)
    engagements = [v.engagement for v in videos]
    rates = [v.engagement_rate for v in videos if v.engagement_rate is not None]
    return EngagementSummary(
        count=len(videos),
        total_views=sum(v.view_count for v in videos),
        total_engagement=sum(engagements),
        avg_engagement=mean(engagements),
        median_engagement=_median(engagements),
        avg_engagement_rate=(mean(rates) if rates else None),
        rate_coverage=len(rates),
    )


def top_videos(videos: Sequence[Video], n: int = 10, by: str = "engagement") -> list[Video]:
    """上位動画を返す。by="engagement"（絶対数）または "rate"（率）。

    率は登録者数非公開だと出ないため、by="rate" では率がある動画のみを対象とする。
    """
    if by == "rate":
        pool = [v for v in videos if v.engagement_rate is not None]
        return sorted(pool, key=lambda v: v.engagement_rate, reverse=True)[:n]
    return sorted(videos, key=lambda v: v.engagement, reverse=True)[:n]
