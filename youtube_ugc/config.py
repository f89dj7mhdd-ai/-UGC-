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

# 観光地名の多言語表記辞書（インバウンド対応の要）。
# 日本語名だけで検索すると日本語コンテンツに偏り、訪日客のUGCを取りこぼす。
# 狙う各市場の言語表記で検索・フィルタするための内蔵辞書。
# 辞書に無い地名は CLI の --aliases で渡す（resolve_aliases 参照）。
PLACE_ALIASES: dict[str, list[str]] = {
    "高山": ["高山", "Takayama", "たかやま", "다카야마", "ทาคายามะ"],
    "金沢": ["金沢", "Kanazawa", "かなざわ", "가나자와", "คานาซาวะ"],
    "白川郷": ["白川郷", "Shirakawago", "Shirakawa-go", "시라카와고", "ชิรากาวาโกะ"],
    "富山": ["富山", "Toyama", "とやま", "도야마", "โทยามะ"],
}


def _lookup_aliases(place: str) -> list[str]:
    """内蔵辞書から別表記一覧を引く（キー一致＋別表記からの逆引き）。

    「富山」でも「toyama」「Toyama」でも同じ表記群に解決できるようにする。
    見つからなければ [place] を返す。
    """
    if place in PLACE_ALIASES:
        return PLACE_ALIASES[place]
    low = place.lower()
    for aliases in PLACE_ALIASES.values():
        if any(low == a.lower() for a in aliases):
            return aliases
    return [place]


def resolve_aliases(place: str, extra: list[str] | None = None) -> list[str]:
    """地名の検索・照合に使う表記一覧を返す（内蔵辞書＋CLI指定）。

    重複は除き、入力順を保つ。辞書に無ければ地名そのもの（＋extra）のみ。
    日本語名・ローマ字名どちらで入力しても同じ表記群に解決される。
    """
    base = _lookup_aliases(place)
    merged = [place, *base, *(extra or [])]
    return list(dict.fromkeys(a for a in merged if a and a.strip()))


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
    extra_aliases: list[str] = field(default_factory=list)  # CLI --aliases で追加する別表記
    use_aliases: bool = True           # False で日本語名のみ（偏りを再現する比較用）
    fetch_comments: bool = True        # コメントを収集して視聴者層・感情を分析
    max_comments: int = 20             # 1動画あたりの取得コメント数上限
    use_llm: bool = True               # 話題分類・感情分析にLLMを使う（無ければ辞書）

    def has_api_key(self) -> bool:
        return bool(self.api_key)

    def resolved_aliases(self) -> list[str]:
        """検索・照合に使う地名表記一覧（インバウンド対応）。"""
        if not self.use_aliases:
            return [self.place]
        return resolve_aliases(self.place, self.extra_aliases)
