"""言語・地域の判定（要件 6.4 / 8）.

- 言語＝主：タイトル＋説明文から判定（APIの言語項目は空欄が多いため使わない）。
- 地域＝従：チャンネルの国情報（自己申告）を補助に用い、空欄は信頼度フラグで明示。

外部ライブラリに依存せず、Unicodeスクリプト＋簡易ストップワードで判定する
（オフライン・テスト容易性のため）。
"""
from __future__ import annotations

import re

# Latin系言語の簡易ストップワード（頻出語で英/西/仏/独/伊/インドネシア語を弁別）
_LATIN_STOPWORDS = {
    "en": {"the", "and", "to", "of", "in", "is", "this", "for", "with", "best", "guide", "day", "trip"},
    "es": {"el", "la", "los", "las", "de", "que", "viaje", "mejor", "comida", "y", "en", "por"},
    "fr": {"le", "la", "les", "de", "et", "voyage", "meilleur", "un", "une", "pour", "avec"},
    "de": {"der", "die", "das", "und", "reise", "mit", "ein", "eine", "für", "ist"},
    "it": {"il", "la", "di", "che", "viaggio", "per", "con", "un", "una", "migliore"},
    "id": {"dan", "yang", "di", "ke", "wisata", "jalan", "terbaik", "ini", "untuk"},
}


def _count_scripts(text: str) -> dict[str, int]:
    counts = {"hiragana_katakana": 0, "hangul": 0, "thai": 0, "han": 0, "latin": 0}
    for ch in text:
        o = ord(ch)
        if 0x3040 <= o <= 0x30FF:          # ひらがな・カタカナ
            counts["hiragana_katakana"] += 1
        elif 0xAC00 <= o <= 0xD7A3 or 0x1100 <= o <= 0x11FF:  # ハングル
            counts["hangul"] += 1
        elif 0x0E00 <= o <= 0x0E7F:        # タイ文字
            counts["thai"] += 1
        elif 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF:  # 漢字
            counts["han"] += 1
        elif ("a" <= ch.lower() <= "z"):
            counts["latin"] += 1
    return counts


def _detect_latin(text: str) -> str:
    words = re.findall(r"[a-zA-Z]+", text.lower())
    if not words:
        return "other"
    scores = {lang: sum(1 for w in words if w in sw) for lang, sw in _LATIN_STOPWORDS.items()}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "en"  # Latin だが弁別不可 → 英語に寄せる（インバウンドの最大公約数）
    # 対象言語(SUPPORTED)以外（es/fr/de/it/id）は "other" に丸める
    return best if best == "en" else "other"


def detect_language(title: str, description: str = "") -> str:
    """タイトル＋説明文から言語コードを返す。

    返り値: ja / en / zh / ko / th / other
    """
    text = f"{title} {description}".strip()
    if not text:
        return "other"
    c = _count_scripts(text)

    # かなが含まれれば日本語（漢字と混在しても日本語と判定）
    if c["hiragana_katakana"] > 0:
        return "ja"
    if c["hangul"] > 0:
        return "ko"
    if c["thai"] > 0:
        return "th"
    # 漢字とラテン文字の多い方で判定する。
    # 外国語動画が地名「高山」を含むだけで中国語誤判定されるのを防ぐ
    # （例: 英語タイトル "Takayama 高山 food tour" はラテンが優勢 → 英語）。
    han, latin = c["han"], c["latin"]
    if han == 0 and latin == 0:
        return "other"
    if han > latin:
        return "zh"
    return _detect_latin(text)


def detect_region(channel_country: str | None) -> tuple[str, str]:
    """チャンネル国情報から (地域, 信頼度) を返す（要件 6.4）.

    信頼度: "declared"（自己申告あり） / "unknown"（空欄）。
    発信者地域であり視聴者地域ではない点に留意（レポートで注記）。
    """
    if channel_country and channel_country.strip():
        return channel_country.strip().upper(), "declared"
    return "unknown", "unknown"
