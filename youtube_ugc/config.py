"""設定値.

要件 6.5（収集範囲・quota）/ 6.1（API方式）に対応。
収集件数の上限やカテゴリ語などのチューニング対象を一箇所に集約する。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


# 検索時に観光地名へ付与するカテゴリ語（要件 6.3）。
# 同名異義・無関係動画を避け、観光関連に寄せるための語。多言語を併用。
CATEGORY_TERMS: list[str] = [
    "観光", "旅行", "グルメ", "温泉",
    "travel", "trip", "tourism",
    "旅遊", "美食",  # 中国語圏
    "여행",            # 韓国語
]

# 言語判定で扱う対象言語（要件 8）。これ以外は "other"。
SUPPORTED_LANGUAGES = ["ja", "en", "zh", "ko", "th"]

# 言語コード → 市場まとめ区分（要件 8「市場まとめ区分」）
LANGUAGE_TO_MARKET = {
    "ja": "日本語圏",
    "en": "英語圏",
    "zh": "中国語圏",
    "ko": "韓国語圏",
    "th": "タイ語圏",
    "other": "その他",
}

# セグメントのセルを「参考値」とみなす件数のしきい値（要件 8）
MIN_SAMPLES_FOR_RELIABLE = 3


@dataclass
class CollectConfig:
    """収集設定（要件 6.5）。"""

    place: str
    months_back: int = 12              # 収集期間：直近12ヶ月（決定事項）
    max_videos: int = 50               # 1観光地あたりの収集件数上限（quota対策）
    category_terms: list[str] = field(default_factory=lambda: list(CATEGORY_TERMS))
    api_key: str | None = field(default_factory=lambda: os.environ.get("YOUTUBE_API_KEY"))
    region_hint: str | None = None     # 検索の地域バイアス（任意）

    def has_api_key(self) -> bool:
        return bool(self.api_key)
