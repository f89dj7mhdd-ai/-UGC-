"""コメント分析（視聴者層・感情）.

YouTube APIでは第三者動画の視聴者属性（年齢・地域）は取得できないため、
コメントを代理シグナルに使う：
  - 視聴者の言語構成：コメントの言語を判定して集計（発信者言語との比較に使用）
  - 感情：ポジ/ネガ/中立（LLMがあればLLM、無ければ多言語辞書）
これにより当初課題の「視聴者層分析」「国内外の関心度」に近づける。
"""
from __future__ import annotations

from collections import Counter
from typing import Sequence

from . import detect
from .models import Video

# 多言語の簡易感情辞書（LLMが無い場合のフォールバック）
_POS = [
    "最高", "良い", "よかった", "綺麗", "きれい", "美味", "おいしい", "行きたい", "素晴",
    "amazing", "beautiful", "great", "love", "best", "delicious", "wonderful", "want to go",
    "太棒", "好吃", "漂亮", "喜歡", "喜欢", "想去",
    "좋아", "맛있", "예쁘", "멋지", "가고싶",
    "อร่อย", "สวย", "ดีมาก", "อยากไป",
]
_NEG = [
    "残念", "ひどい", "高い", "混雑", "まずい", "最悪", "がっかり", "高すぎ",
    "disappointing", "bad", "expensive", "crowded", "terrible", "worst", "overrated",
    "失望", "太貴", "太贵", "難吃", "难吃", "人多",
    "별로", "실망", "비싸", "최악",
    "แพง", "แย่", "ผิดหวัง", "คนเยอะ",
]


# ---- 視聴者の言語構成 -------------------------------------------------------
def annotate_viewer_languages(videos: Sequence[Video]) -> None:
    """各動画のコメント言語構成を viewer_languages に設定する。"""
    for v in videos:
        counter: Counter = Counter()
        for c in v.comments:
            counter[detect.detect_language(c)] += 1
        v.viewer_languages = dict(counter)


def viewer_language_totals(videos: Sequence[Video]) -> dict[str, int]:
    """全動画のコメント言語を合算した構成。"""
    total: Counter = Counter()
    for v in videos:
        total.update(v.viewer_languages)
    return dict(total)


def creator_vs_viewer(videos: Sequence[Video]) -> dict[str, dict]:
    """発信者言語の構成と、視聴者（コメント）言語の構成を並べて返す。"""
    creator: Counter = Counter(v.language or "other" for v in videos)
    viewer = viewer_language_totals(videos)
    return {"creator": dict(creator), "viewer": viewer}


# ---- 感情分析 --------------------------------------------------------------
def _lexicon_sentiment(comments: Sequence[str]) -> str | None:
    if not comments:
        return None
    pos = neg = 0
    for c in comments:
        low = c.lower()
        pos += sum(1 for w in _POS if w.lower() in low)
        neg += sum(1 for w in _NEG if w.lower() in low)
    if pos == 0 and neg == 0:
        return "neutral"
    return "positive" if pos >= neg else "negative"


def _llm_sentiment(videos: Sequence[Video]) -> dict[str, str] | None:
    from . import llm
    if not llm.is_available():
        return None
    items = [(v.video_id, v.comments) for v in videos if v.comments]
    if not items:
        return {}
    blocks = []
    for vid, cs in items:
        joined = " / ".join(c[:120] for c in cs[:12])
        blocks.append(f"{vid}\t{joined}")
    system = ("あなたは観光動画のコメント感情分析器です。各動画のコメント群全体の"
              "総合的な感情を positive / negative / neutral のいずれかで判定します。多言語対応。")
    prompt = ('次の各行「ID<TAB>コメント群」について総合感情を判定し、'
              'JSON {"ID":"positive|negative|neutral"} だけを出力。\n\n' + "\n".join(blocks))
    data = llm.complete_json(prompt, system=system, max_tokens=800)
    if not isinstance(data, dict):
        return None
    valid = {"positive", "negative", "neutral"}
    return {vid: data.get(vid) for vid, _ in items if data.get(vid) in valid}


def annotate_sentiment(videos: Sequence[Video], use_llm: bool = True) -> None:
    """各動画の総合感情を sentiment に設定する（LLM優先、辞書フォールバック）。"""
    llm_map = _llm_sentiment(videos) if use_llm else None
    for v in videos:
        label = (llm_map or {}).get(v.video_id)
        if label is None:
            label = _lexicon_sentiment(v.comments)
        v.sentiment = label


def sentiment_summary(videos: Sequence[Video]) -> dict:
    """感情の集計（件数とポジ率）。"""
    counter: Counter = Counter(v.sentiment for v in videos if v.sentiment)
    rated = sum(counter.values())
    pos = counter.get("positive", 0)
    return {
        "positive": pos,
        "negative": counter.get("negative", 0),
        "neutral": counter.get("neutral", 0),
        "rated": rated,
        "positive_ratio": (pos / rated if rated else None),
    }
