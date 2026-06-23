"""高反応パターンの抽出（要件 7「高反応パターン」）.

エンゲージメント上位の動画群に共通する特徴（話題・言語・尺・投稿時期）を
全体分布と比較し、上位で偏って多い特徴を「再現すべき要素」として返す。
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Sequence

from .models import Video


@dataclass
class PatternFinding:
    dimension: str          # 例: "話題", "言語", "尺", "投稿時期"
    value: str
    top_share: float        # 上位群での出現割合
    overall_share: float    # 全体での出現割合
    lift: float             # top_share / overall_share（1超で上位に偏在）

    @property
    def lift_label(self) -> str:
        if self.lift >= 1.5:
            return "強い偏り"
        if self.lift >= 1.15:
            return "やや偏り"
        return "全体並み"


def _season(v: Video) -> str | None:
    d = v.published_date
    if not d:
        return None
    m = d.month
    if m in (3, 4, 5):
        return "春(3-5月)"
    if m in (6, 7, 8):
        return "夏(6-8月)"
    if m in (9, 10, 11):
        return "秋(9-11月)"
    return "冬(12-2月)"


def _dimension_values(v: Video) -> dict[str, list[str]]:
    return {
        "話題": list(v.topics),
        "言語": [v.language or "other"],
        "尺": [v.duration_bucket],
        "投稿時期": [s for s in [_season(v)] if s],
    }


def _share(videos: Sequence[Video], dim: str) -> Counter:
    counter: Counter = Counter()
    for v in videos:
        for val in _dimension_values(v).get(dim, []):
            counter[val] += 1
    return counter


def extract(videos: Sequence[Video], top_ratio: float = 0.3, min_lift: float = 1.15) -> list[PatternFinding]:
    """上位群に偏在する特徴を返す。

    top_ratio: 上位とみなす割合（既定: 上位30%）。
    min_lift:  この値以上のliftだけ採用。
    """
    if len(videos) < 4:
        return []
    ranked = sorted(videos, key=lambda v: v.engagement, reverse=True)
    k = max(2, round(len(ranked) * top_ratio))
    top = ranked[:k]

    findings: list[PatternFinding] = []
    for dim in ("話題", "言語", "尺", "投稿時期"):
        overall = _share(videos, dim)
        top_c = _share(top, dim)
        overall_total = sum(overall.values()) or 1
        top_total = sum(top_c.values()) or 1
        for val, tc in top_c.items():
            top_share = tc / top_total
            overall_share = overall.get(val, 0) / overall_total
            if overall_share == 0:
                continue
            lift = top_share / overall_share
            if lift >= min_lift and top_share >= 0.2:
                findings.append(PatternFinding(dim, val, top_share, overall_share, lift))
    return sorted(findings, key=lambda f: f.lift, reverse=True)
