"""HTMLレポート生成（要件 11）.

外部ライブラリに依存しない自己完結HTML。バーはdiv幅で表現する。
非専門の担当者が上長・議会説明に使える説明可能なレポートを目指す。
"""
from __future__ import annotations

import html
from datetime import datetime

from .config import LANGUAGE_TO_MARKET
from .pipeline import AnalysisResult


def _esc(s) -> str:
    return html.escape(str(s))


def _bar(value: float, max_value: float, color: str = "#2E6E8E") -> str:
    pct = 0 if max_value <= 0 else min(100, value / max_value * 100)
    return (
        f'<div class="bar-wrap"><div class="bar" style="width:{pct:.1f}%;background:{color}"></div>'
        f'<span class="bar-val">{value:,.0f}</span></div>'
    )


def _segment_table(title: str, stats, note: str = "") -> str:
    if not stats:
        return ""
    max_eng = max((s.avg_engagement for s in stats), default=0)
    rows = []
    for s in stats:
        rate = "—" if s.avg_engagement_rate is None else f"{s.avg_engagement_rate*100:.2f}%"
        topics = "、".join(s.top_topics) if s.top_topics else "—"
        flag = f'<span class="flag">{s.note}</span>' if s.note else ""
        rows.append(
            f"<tr><td>{_esc(s.label)} {flag}</td><td class='num'>{s.count}</td>"
            f"<td>{_bar(s.avg_engagement, max_eng)}</td>"
            f"<td class='num'>{rate}</td><td>{_esc(topics)}</td></tr>"
        )
    note_html = f'<p class="note">{_esc(note)}</p>' if note else ""
    return (
        f"<h3>{_esc(title)}</h3>{note_html}"
        "<table><thead><tr><th>セグメント</th><th>件数</th>"
        "<th>平均エンゲージメント</th><th>平均エンゲージ率</th><th>主な話題</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _video_rows(videos, show_rate: bool) -> str:
    rows = []
    for v in videos:
        rate = "—" if v.engagement_rate is None else f"{v.engagement_rate*100:.2f}%"
        topics = "、".join(v.topics) if v.topics else "—"
        region = "不明" if v.region == "unknown" else v.region
        extra = f"<td class='num'>{rate}</td>" if show_rate else ""
        rows.append(
            f"<tr><td class='title'>{_esc(v.title)}</td>"
            f"<td>{_esc(v.language)}/{_esc(region)}</td>"
            f"<td class='num'>{v.view_count:,}</td>"
            f"<td class='num'>{v.engagement:,}</td>{extra}"
            f"<td>{_esc(topics)}</td></tr>"
        )
    return "".join(rows)


def _findings_html(findings) -> str:
    if not findings:
        return "<p class='note'>明確な偏りは検出されませんでした（データ量が少ない可能性）。</p>"
    rows = [
        f"<tr><td>{_esc(f.dimension)}</td><td><b>{_esc(f.value)}</b></td>"
        f"<td class='num'>{f.top_share:.0%}</td><td class='num'>{f.overall_share:.0%}</td>"
        f"<td class='num'>{f.lift:.1f}倍</td><td>{_esc(f.lift_label)}</td></tr>"
        for f in findings
    ]
    return (
        "<table><thead><tr><th>観点</th><th>特徴</th><th>上位群での割合</th>"
        "<th>全体割合</th><th>偏り(lift)</th><th>判定</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _viewer_sentiment_html(result: AnalysisResult) -> str:
    cv = result.creator_vs_viewer or {}
    creator = cv.get("creator", {})
    viewer = cv.get("viewer", {})
    if not viewer:
        return ('<p class="note">コメントが取得できなかったため、視聴者層・感情分析はスキップしました'
                '（サンプル/コメント無効動画など）。</p>')
    keys = sorted(set(creator) | set(viewer),
                  key=lambda k: viewer.get(k, 0) + creator.get(k, 0), reverse=True)
    c_total = sum(creator.values()) or 1
    v_total = sum(viewer.values()) or 1
    rows = []
    for k in keys:
        label = LANGUAGE_TO_MARKET.get(k, k)
        c, v = creator.get(k, 0), viewer.get(k, 0)
        rows.append(
            f"<tr><td>{_esc(label)}</td>"
            f"<td class='num'>{c}（{c/c_total:.0%}）</td>"
            f"<td class='num'>{v}（{v/v_total:.0%}）</td></tr>"
        )
    table = (
        "<h3>発信者言語 × 視聴者言語（コメント）</h3>"
        "<table><thead><tr><th>市場</th><th>発信者（動画数）</th>"
        "<th>視聴者（コメント数）</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        '<p class="note">視聴者属性はAPI非開示のため、コメントの言語を視聴者側の代理指標としています。</p>'
    )

    ss = result.sentiment or {}
    sent = ""
    if ss.get("rated"):
        pr = ss.get("positive_ratio")
        pr_s = "—" if pr is None else f"{pr*100:.0f}%"
        sent = (
            '<div class="cards">'
            f'<div class="card"><div class="k">ポジティブ率</div><div class="v">{pr_s}</div></div>'
            f'<div class="card"><div class="k">ポジ</div><div class="v">{ss.get("positive",0)}</div></div>'
            f'<div class="card"><div class="k">ネガ</div><div class="v">{ss.get("negative",0)}</div></div>'
            f'<div class="card"><div class="k">中立</div><div class="v">{ss.get("neutral",0)}</div></div>'
            "</div>"
            f'<p class="note">感情判定: {_esc(result.llm_provider)}（LLMが無い場合は多言語辞書）。'
            "ネガティブは混雑・価格などの懸念を含む可能性があり、要因確認の起点になります。</p>"
        )
    return table + sent


def render(result: AnalysisResult) -> str:
    s = result.summary
    src_label = "サンプルデータ" if result.source == "sample" else "YouTube Data API"
    rate_cov = f"（率算出 {s.rate_coverage}/{s.count}件・登録者数非公開は除外）" if s.count else ""
    avg_rate = "—" if s.avg_engagement_rate is None else f"{s.avg_engagement_rate*100:.2f}%"

    insights = "".join(f"<li>{_esc(t)}</li>" for t in result.insights)
    lang_comp = "、".join(
        f"{LANGUAGE_TO_MARKET.get(k, k)} {v}件" for k, v in
        sorted(result.language_composition.items(), key=lambda kv: kv[1], reverse=True)
    )

    matrix_rows = "".join(
        f"<tr><td>{_esc(c.language)}</td><td>{'不明' if c.region=='unknown' else _esc(c.region)}</td>"
        f"<td class='num'>{c.count}</td><td class='num'>{c.avg_engagement:,.0f}</td>"
        f"<td>{'' if c.reliable else '参考値'}</td></tr>"
        for c in result.matrix
    )

    show_rate = any(v.engagement_rate is not None for v in result.top_by_engagement)

    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<title>観光UGC分析レポート — {_esc(result.place)}</title>
<style>
  body {{ font-family: "Yu Gothic","Hiragino Sans",sans-serif; color:#222; max-width:980px;
          margin:0 auto; padding:32px 24px; line-height:1.7; }}
  h1 {{ color:#1F4E66; border-bottom:3px solid #1F4E66; padding-bottom:8px; }}
  h2 {{ color:#1F4E66; margin-top:36px; border-left:6px solid #2E6E8E; padding-left:10px; }}
  h3 {{ color:#2E6E8E; margin-top:22px; }}
  .meta {{ color:#666; font-size:13px; }}
  .cards {{ display:flex; flex-wrap:wrap; gap:14px; margin:16px 0; }}
  .card {{ flex:1; min-width:150px; background:#F2F6F8; border-radius:8px; padding:14px 16px; }}
  .card .k {{ font-size:12px; color:#567; }}
  .card .v {{ font-size:24px; font-weight:bold; color:#1F4E66; }}
  table {{ border-collapse:collapse; width:100%; margin:10px 0 4px; font-size:14px; }}
  th,td {{ border:1px solid #D6E0E6; padding:7px 9px; text-align:left; vertical-align:top; }}
  th {{ background:#1F4E66; color:#fff; font-weight:600; }}
  tr:nth-child(even) td {{ background:#F7FAFC; }}
  td.num {{ text-align:right; white-space:nowrap; }}
  td.title {{ max-width:360px; }}
  .bar-wrap {{ position:relative; background:#E8EEF2; border-radius:4px; height:18px; min-width:120px; }}
  .bar {{ height:18px; border-radius:4px; }}
  .bar-val {{ position:absolute; right:6px; top:0; font-size:11px; color:#333; line-height:18px; }}
  .flag {{ background:#FFE0B2; color:#8A5A00; font-size:11px; padding:1px 6px; border-radius:8px; }}
  .note {{ color:#777; font-size:12.5px; margin:4px 0; }}
  .insights {{ background:#E8F2E8; border-left:6px solid #2E7D32; padding:12px 16px 12px 28px; border-radius:6px; }}
  .insights li {{ margin:6px 0; }}
  .disclaimer {{ background:#FFF6E5; border-left:6px solid #E69500; padding:10px 16px; border-radius:6px;
                 font-size:12.5px; color:#6b5300; margin-top:30px; }}
</style></head><body>

<h1>観光UGC分析レポート</h1>
<p class="meta">対象観光地：<b>{_esc(result.place)}</b>　/　データ源：{src_label}　/
収集期間：直近{result.config.months_back}ヶ月　/　生成日時：{datetime.now():%Y-%m-%d %H:%M}</p>
<p class="meta">検索表記（多言語）：{_esc(' / '.join(result.config.resolved_aliases()))}</p>

<h2>1. 現状サマリ</h2>
<div class="cards">
  <div class="card"><div class="k">収集動画数</div><div class="v">{s.count}</div></div>
  <div class="card"><div class="k">総再生数</div><div class="v">{s.total_views:,}</div></div>
  <div class="card"><div class="k">平均エンゲージメント</div><div class="v">{s.avg_engagement:,.0f}</div></div>
  <div class="card"><div class="k">平均エンゲージ率</div><div class="v">{avg_rate}</div></div>
</div>
<p class="note">エンゲージメント＝いいね＋コメント。率＝エンゲージメント÷登録者数 {rate_cov}。</p>
<p>言語構成：{_esc(lang_comp)}</p>

<h2>2. 反応の良い市場・地域（セグメント）</h2>
{_segment_table("言語別（主軸）", result.lang_segments)}
{_segment_table("市場まとめ区分", result.market_segments)}
{_segment_table("推定地域別（従・自己申告ベース）", result.region_segments,
                note="地域は発信者の自己申告であり、視聴者の地域ではありません。空欄は『不明』として参考値扱いです。")}

<h3>言語 × 推定地域 クロス集計</h3>
<table><thead><tr><th>言語</th><th>推定地域</th><th>件数</th><th>平均エンゲージメント</th><th>信頼度</th></tr></thead>
<tbody>{matrix_rows}</tbody></table>

<h2>3. 視聴者層と感情（コメント分析）</h2>
{_viewer_sentiment_html(result)}

<h2>4. 人気コンテンツ（エンゲージメント上位）</h2>
<table><thead><tr><th>タイトル</th><th>言語/地域</th><th>再生数</th><th>エンゲージ</th>
{'<th>エンゲージ率</th>' if show_rate else ''}<th>話題</th></tr></thead>
<tbody>{_video_rows(result.top_by_engagement, show_rate)}</tbody></table>

<h2>5. 高反応パターン</h2>
<p class="note">エンゲージメント上位群に偏って多い特徴（再現すべき訴求要素の候補）。話題分類: {_esc(result.llm_provider)}。</p>
{_findings_html(result.findings)}

<h2>6. 示唆と次の手がかり</h2>
<ul class="insights">{insights}</ul>

<div class="disclaimer">
  <b>データ取り扱い上の注意（要件 6）：</b>
  本レポートは公開エンゲージメント（いいね＋コメント）に基づきます。インプレッション・共有数は
  YouTube APIで第三者投稿について取得できないため扱っていません。エンゲージメント率は登録者数を
  分母とし、登録者数非公開のチャンネルは率を算出していません。地域は発信者の自己申告に基づく推定値です。
</div>

</body></html>"""
