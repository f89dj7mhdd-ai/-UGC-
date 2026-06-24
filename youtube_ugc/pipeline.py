"""分析パイプライン（収集→付与→集計）.

要件 5 の機能フローを束ねる：
収集 → 言語/地域判定・話題分類 → 指標集計・セグメント・パターン抽出 → 示唆生成。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from . import comments as comments_mod
from . import detect, metrics, patterns, segment
from .config import CollectConfig, LANGUAGE_TO_MARKET
from .models import Video
from .topics import classify_batch


def annotate(videos: Sequence[Video], use_llm: bool = True) -> list[Video]:
    """各動画に言語・地域・話題・視聴者言語・感情を付与する（要件 6.4 / 9）。"""
    for v in videos:
        v.language = detect.detect_language(v.title, v.description)
        v.region, v.region_confidence = detect.detect_region(v.channel_country)

    # 話題分類は一括（LLMがあれば表現揺れを吸収、無ければキーワード）
    items = [(v.video_id, f"{v.title} {v.description} {' '.join(v.tags)}") for v in videos]
    topic_map = classify_batch(items, use_llm=use_llm)
    for v in videos:
        v.topics = topic_map.get(v.video_id, [])

    # コメントから視聴者言語・感情を付与
    comments_mod.annotate_viewer_languages(videos)
    comments_mod.annotate_sentiment(videos, use_llm=use_llm)
    return list(videos)


def build_insights(videos, lang_segments, findings) -> list[str]:
    """非専門の担当者向けの示唆を文章で生成する（要件 11）。"""
    insights: list[str] = []
    if not videos:
        return ["対象期間内に該当UGCが見つかりませんでした。検索条件（地名・カテゴリ語）の調整を検討してください。"]

    # 反応の良い市場
    reliable = [s for s in lang_segments if s.reliable]
    ranked = sorted(reliable or lang_segments, key=lambda s: s.avg_engagement, reverse=True)
    if ranked:
        top = ranked[0]
        topics = "・".join(top.top_topics) if top.top_topics else "（話題の偏りは弱め）"
        insights.append(
            f"反応が最も高い市場は「{top.label}」で、平均エンゲージメント{top.avg_engagement:,.0f}。"
            f"この市場では特に {topics} の動画が伸びており、優先ターゲットの候補になります。"
        )

    # 話題パターン
    topic_hits = [f for f in findings if f.dimension == "話題"]
    if topic_hits:
        f = topic_hits[0]
        insights.append(
            f"高反応動画では「{f.value}」が上位群の{f.top_share:.0%}（全体比{f.lift:.1f}倍）を占めます。"
            f"プロモーション素材はこの切り口を軸にすると反応が見込めます。"
        )

    # 尺・時期
    for dim, lead in (("尺", "動画の長さ"), ("投稿時期", "発信の時期")):
        hit = [f for f in findings if f.dimension == dim]
        if hit:
            f = hit[0]
            insights.append(f"{lead}は「{f.value}」が高反応群に偏在（全体比{f.lift:.1f}倍）。発信設計の参考にできます。")

    # 発信者 vs 視聴者の言語ギャップ（コメント由来）
    cv = comments_mod.creator_vs_viewer(videos)
    viewer = cv["viewer"]
    if viewer:
        foreign_viewer = sum(n for lg, n in viewer.items() if lg not in ("ja", "other"))
        total_viewer = sum(viewer.values())
        if total_viewer and foreign_viewer / total_viewer >= 0.3:
            insights.append(
                f"コメントの{foreign_viewer/total_viewer:.0%}が外国語で、発信者構成以上に海外の視聴者の関心が高い可能性があります。"
                "発信が日本語中心でも、海外視聴者向けの多言語化（字幕・概要）が効きそうです。"
            )

    # 感情
    ss = comments_mod.sentiment_summary(videos)
    if ss["rated"]:
        if ss["positive_ratio"] is not None:
            insights.append(
                f"コメントの感情はポジティブが{ss['positive_ratio']:.0%}（{ss['rated']}件中）。"
                + (f"ネガティブ{ss['negative']}件は混雑・価格などの懸念を含む可能性があり、要因の確認に値します。"
                   if ss["negative"] else "全体に好意的です。")
            )

    # データ留意
    unknown = sum(1 for v in videos if v.region == "unknown")
    if unknown:
        insights.append(
            f"地域が不明な動画が{unknown}件あります（発信者の自己申告が空欄）。地域別の数値は参考値として扱ってください。"
        )
    return insights


@dataclass
class AnalysisResult:
    place: str
    source: str               # "sample" or "youtube"
    videos: list[Video]
    summary: object
    top_by_engagement: list[Video]
    top_by_rate: list[Video]
    lang_segments: list
    market_segments: list
    region_segments: list
    matrix: list
    findings: list
    insights: list[str]
    config: CollectConfig
    language_composition: dict = field(default_factory=dict)
    viewer_languages: dict = field(default_factory=dict)
    creator_vs_viewer: dict = field(default_factory=dict)
    sentiment: dict = field(default_factory=dict)
    llm_provider: str = "none"


def run(config: CollectConfig, collector) -> AnalysisResult:
    from . import llm
    raw = collector.collect(config)
    videos = annotate(raw, use_llm=config.use_llm)

    lang_segments = segment.by_language(videos)
    composition = {s.key: s.count for s in lang_segments}
    findings = patterns.extract(videos)

    return AnalysisResult(
        place=config.place,
        source=("youtube" if config.has_api_key() and collector.__class__.__name__ == "YouTubeCollector" else "sample"),
        videos=videos,
        summary=metrics.summarize(videos),
        top_by_engagement=metrics.top_videos(videos, 10, by="engagement"),
        top_by_rate=metrics.top_videos(videos, 10, by="rate"),
        lang_segments=lang_segments,
        market_segments=segment.by_market(videos),
        region_segments=segment.by_region(videos),
        matrix=segment.language_region_matrix(videos),
        findings=findings,
        insights=build_insights(videos, lang_segments, findings),
        config=config,
        language_composition=composition,
        viewer_languages=comments_mod.viewer_language_totals(videos),
        creator_vs_viewer=comments_mod.creator_vs_viewer(videos),
        sentiment=comments_mod.sentiment_summary(videos),
        llm_provider=(llm.provider_name() if config.use_llm else "off"),
    )
