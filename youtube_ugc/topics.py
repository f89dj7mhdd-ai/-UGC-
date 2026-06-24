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


CATEGORIES = list(TOPIC_KEYWORDS.keys())


def classify_topics(text: str) -> list[str]:
    """テキストから該当する話題カテゴリ一覧を返す（キーワード一致・フォールバック）。"""
    low = text.lower()
    hits = []
    for category, kws in TOPIC_KEYWORDS.items():
        if any(kw.lower() in low for kw in kws):
            hits.append(category)
    return hits


def _llm_classify(items: list[tuple[str, str]]) -> dict[str, list[str]] | None:
    """LLMで一括分類。表現揺れ・多言語に強い。失敗時は None。"""
    from . import llm
    if not llm.is_available():
        return None
    cats = "、".join(CATEGORIES)
    lines = "\n".join(f"{k}\t{text[:200]}" for k, text in items)
    system = (
        "あなたは観光コンテンツの分類器です。各動画を、与えられたカテゴリのみから"
        "0〜複数個に分類します。多言語（日英中韓タイ）の表現揺れを吸収してください。"
    )
    prompt = (
        f"カテゴリ: {cats}\n"
        "次の各行は「ID<TAB>テキスト」です。各IDについて該当カテゴリを選び、"
        'JSONオブジェクト {"ID": ["カテゴリ", ...]} だけを出力してください。'
        "カテゴリ名は上記の表記を厳守。該当なしは空配列。\n\n" + lines
    )
    data = llm.complete_json(prompt, system=system, max_tokens=1500)
    if not isinstance(data, dict):
        return None
    # カテゴリ集合外の値を除去して正規化
    valid = set(CATEGORIES)
    out: dict[str, list[str]] = {}
    for k, _ in items:
        vals = data.get(k) or data.get(str(k)) or []
        if isinstance(vals, str):
            vals = [vals]
        out[k] = [v for v in vals if v in valid]
    return out


def classify_batch(items: list[tuple[str, str]], use_llm: bool = True) -> dict[str, list[str]]:
    """(id, text) のリストを一括分類。LLM優先、失敗時はキーワード。

    返り値: {id: [カテゴリ, ...]}
    """
    if use_llm:
        llm_result = _llm_classify(items)
        if llm_result is not None:
            return llm_result
    return {k: classify_topics(text) for k, text in items}
