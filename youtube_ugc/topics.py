"""話題（トピック）分類の多言語キーワード辞書.

要件 9「市場×話題」。MVPはキーワードマッチによる軽量分類とする。
拡張フェーズでLLM分類への差し替えを想定。
"""
from __future__ import annotations

# カテゴリ → キーワード（小文字で比較。日本語/英語/中国語/韓国語/タイ語を混在）
TOPIC_KEYWORDS: dict[str, list[str]] = {
    "食・グルメ": [
        "グルメ", "食べ", "ごはん", "ラーメン", "寿司", "海鮮", "スイーツ", "カフェ",
        "food", "eat", "cuisine", "ramen", "sushi", "restaurant", "cafe",
        "美食", "拉麵", "壽司", "맛집", "음식", "อาหาร",
    ],
    "自然・景観": [
        "自然", "絶景", "紅葉", "桜", "山", "海", "滝", "星空", "景色",
        "nature", "scenery", "view", "mountain", "autumn", "cherry",
        "風景", "자연", "경치", "ธรรมชาติ",
    ],
    "温泉・宿": [
        "温泉", "旅館", "露天", "ホテル", "宿",
        "onsen", "hot spring", "ryokan", "hotel", "spa",
        "溫泉", "온천", "ออนเซน",
    ],
    "文化・寺社": [
        "寺", "神社", "祭", "城", "伝統", "歴史", "古い町",
        "temple", "shrine", "festival", "castle", "history", "tradition", "old town",
        "寺廟", "神社", "축제", "วัด",
    ],
    "体験・アクティビティ": [
        "体験", "アクティビティ", "ハイキング", "スキー", "サイクリング",
        "experience", "activity", "hiking", "ski", "cycling", "tour",
        "體驗", "체험", "กิจกรรม",
    ],
    "聖地・サブカル": [
        "聖地", "アニメ", "ロケ地",
        "anime", "pilgrimage", "filming location",
        "動漫", "성지", "อนิเมะ",
    ],
}


def classify_topics(text: str) -> list[str]:
    """テキストから該当する話題カテゴリ一覧を返す（複数可）。"""
    low = text.lower()
    hits = []
    for category, kws in TOPIC_KEYWORDS.items():
        if any(kw.lower() in low for kw in kws):
            hits.append(category)
    return hits
