"""セグメント分割（要件 8）.

言語＝主／推定地域＝従の2軸でグループ分けし、グループ内で比較する。
各セルに件数と信頼度フラグを付け、少数セルは参考値とする。
言語は市場まとめ区分（中国語圏など）へ集約も行う。
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Sequence

from . import metrics
from .config import LANGUAGE_TO_MARKET, MIN_SAMPLES_FOR_RELIABLE
from .models import Video


@dataclass
class SegmentStat:
    key: str
    label: str
    count: int
    avg_engagement: float
    avg_engagement_rate: float | None
    reliable: bool                       # 件数がしきい値以上か
    top_topics: list[str] = field(default_factory=list)

    @property
    def note(self) -> str:
        return "" if self.reliable else "参考値（少数）"


def _topic_ranking(videos: Sequence[Video], n: int = 3) -> list[str]:
    counter: dict[str, int] = defaultdict(int)
    for v in videos:
        for t in v.topics:
            counter[t] += 1
    return [t for t, _ in sorted(counter.items(), key=lambda kv: kv[1], reverse=True)[:n]]


def _build(groups: dict[str, list[Video]], labeler) -> list[SegmentStat]:
    stats: list[SegmentStat] = []
    for key, vids in groups.items():
        s = metrics.summarize(vids)
        stats.append(SegmentStat(
            key=key,
            label=labeler(key),
            count=len(vids),
            avg_engagement=s.avg_engagement,
            avg_engagement_rate=s.avg_engagement_rate,
            reliable=len(vids) >= MIN_SAMPLES_FOR_RELIABLE,
            top_topics=_topic_ranking(vids),
        ))
    return sorted(stats, key=lambda x: x.count, reverse=True)


def by_language(videos: Sequence[Video]) -> list[SegmentStat]:
    groups: dict[str, list[Video]] = defaultdict(list)
    for v in videos:
        groups[v.language or "other"].append(v)
    return _build(groups, lambda k: f"{k}（{LANGUAGE_TO_MARKET.get(k, k)}）")


def by_market(videos: Sequence[Video]) -> list[SegmentStat]:
    """市場まとめ区分（要件 8）。セルが疎になる問題の緩和。"""
    groups: dict[str, list[Video]] = defaultdict(list)
    for v in videos:
        market = LANGUAGE_TO_MARKET.get(v.language or "other", "その他")
        groups[market].append(v)
    return _build(groups, lambda k: k)


def by_region(videos: Sequence[Video]) -> list[SegmentStat]:
    groups: dict[str, list[Video]] = defaultdict(list)
    for v in videos:
        groups[v.region or "unknown"].append(v)
    return _build(groups, lambda k: ("地域不明" if k == "unknown" else k))


@dataclass
class MatrixCell:
    language: str
    region: str
    count: int
    avg_engagement: float
    reliable: bool


def language_region_matrix(videos: Sequence[Video]) -> list[MatrixCell]:
    """言語×推定地域のクロス集計（要件 8）。"""
    groups: dict[tuple[str, str], list[Video]] = defaultdict(list)
    for v in videos:
        groups[(v.language or "other", v.region or "unknown")].append(v)
    cells = []
    for (lang, region), vids in groups.items():
        s = metrics.summarize(vids)
        cells.append(MatrixCell(
            language=lang, region=region, count=len(vids),
            avg_engagement=s.avg_engagement,
            reliable=len(vids) >= MIN_SAMPLES_FOR_RELIABLE,
        ))
    return sorted(cells, key=lambda c: c.count, reverse=True)
