"""分析ロジックのユニットテスト（要件 7/8 の検証ステップ）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from youtube_ugc import detect, metrics, patterns, segment  # noqa: E402
from youtube_ugc.collector import is_relevant, parse_duration  # noqa: E402
from youtube_ugc.models import Video  # noqa: E402
from youtube_ugc.topics import classify_topics  # noqa: E402


def mk(vid="v", title="高山 グルメ", desc="", likes=10, comments=5, subs=1000,
       hidden=False, country="JP", dur=300, views=1000, published="2025-10-01T00:00:00Z", tags=None):
    return Video(video_id=vid, title=title, description=desc, channel_id="c", channel_title="ch",
                 published_at=published, duration_seconds=dur, view_count=views,
                 like_count=likes, comment_count=comments, tags=tags or [],
                 channel_country=country, subscriber_count=subs, subscriber_hidden=hidden)


# ---- 言語判定 -----------------------------------------------------------
def test_detect_japanese():
    assert detect.detect_language("高山のグルメ食べ歩き") == "ja"

def test_detect_chinese_no_kana():
    assert detect.detect_language("高山美食之旅 飛驒牛") == "zh"

def test_detect_korean():
    assert detect.detect_language("다카야마 맛집 투어") == "ko"

def test_detect_thai():
    assert detect.detect_language("เที่ยวทาคายามะ อาหาร") == "th"

def test_detect_english():
    assert detect.detect_language("Takayama food travel guide and the best trip") == "en"

def test_detect_english_with_place_kanji():
    # 地名「高山」を含む英語タイトルは英語と判定されるべき（漢字優先の誤判定防止）
    assert detect.detect_language("TAKAYAMA Japan Street Food Tour | Hida Beef in 高山",
                                  "Amazing food tour in Takayama 高山, the best trip guide") == "en"

def test_detect_empty():
    assert detect.detect_language("", "") == "other"

def test_detect_region_declared_and_unknown():
    assert detect.detect_region("jp") == ("JP", "declared")
    assert detect.detect_region(None) == ("unknown", "unknown")
    assert detect.detect_region("  ") == ("unknown", "unknown")


# ---- 指標 ---------------------------------------------------------------
def test_engagement_is_like_plus_comment():
    assert mk(likes=10, comments=5).engagement == 15

def test_engagement_rate():
    v = mk(likes=10, comments=10, subs=1000)
    assert abs(v.engagement_rate - 0.02) < 1e-9

def test_rate_none_when_hidden():
    assert mk(hidden=True, subs=None).engagement_rate is None

def test_rate_none_when_zero_subs():
    assert mk(subs=0).engagement_rate is None

def test_summary_excludes_hidden_from_rate():
    vids = [mk(subs=1000, likes=10, comments=10), mk(hidden=True, subs=None, likes=50, comments=50)]
    s = metrics.summarize(vids)
    assert s.count == 2
    assert s.rate_coverage == 1  # 非公開は率対象外
    assert s.total_engagement == 120

def test_top_by_rate_only_includes_rateable():
    vids = [mk(vid="a", subs=100, likes=10, comments=0), mk(vid="b", hidden=True, subs=None, likes=999, comments=0)]
    top = metrics.top_videos(vids, by="rate")
    assert [v.video_id for v in top] == ["a"]


# ---- 話題分類 -----------------------------------------------------------
def test_classify_topics_multilingual():
    assert "食・グルメ" in classify_topics("高山 ラーメン グルメ")
    assert "温泉・宿" in classify_topics("Takayama onsen ryokan")
    assert "自然・景観" in classify_topics("高山 紅葉 自然")


# ---- セグメント ---------------------------------------------------------
def test_language_segments_grouping():
    vids = [mk(vid="a", title="高山グルメ"), mk(vid="b", title="高山ラーメン"),
            mk(vid="c", title="Takayama food best trip guide")]
    for v in vids:
        v.language = detect.detect_language(v.title, v.description)
    segs = {s.key: s.count for s in segment.by_language(vids)}
    assert segs.get("ja") == 2
    assert segs.get("en") == 1

def test_reliable_flag():
    vids = [mk(vid=str(i), title="高山グルメ") for i in range(4)]
    for v in vids:
        v.language = "ja"
    seg = segment.by_language(vids)[0]
    assert seg.reliable is True  # 4件 >= しきい値3


# ---- パターン抽出 -------------------------------------------------------
def test_patterns_detects_topic_bias():
    # 上位群（高エンゲージ）は食、下位は文化。食が偏在するはず。
    vids = []
    for i in range(6):
        v = mk(vid=f"hi{i}", title="高山グルメ ラーメン", likes=1000, comments=100)
        v.topics = ["食・グルメ"]
        v.language = "ja"
        vids.append(v)
    for i in range(6):
        v = mk(vid=f"lo{i}", title="高山 神社 歴史", likes=5, comments=1)
        v.topics = ["文化・寺社"]
        v.language = "ja"
        vids.append(v)
    findings = patterns.extract(vids)
    topic_findings = [f for f in findings if f.dimension == "話題"]
    assert any(f.value == "食・グルメ" and f.lift > 1 for f in topic_findings)


# ---- 収集ユーティリティ -------------------------------------------------
def test_parse_duration():
    assert parse_duration("PT1H2M3S") == 3723
    assert parse_duration("PT58S") == 58
    assert parse_duration("PT10M") == 600
    assert parse_duration("") == 0

def test_relevance_filter():
    assert is_relevant(mk(title="高山のグルメ"), ["高山"]) is True
    assert is_relevant(mk(title="京都の寺", tags=[]), ["高山"]) is False


# ---- コメント分析（視聴者層・感情） -------------------------------------
def test_viewer_language_aggregation():
    from youtube_ugc import comments as cm
    v = mk()
    v.language = "ja"
    v.comments = ["美味しそう", "Looks amazing", "好想去", "行きたい"]
    cm.annotate_viewer_languages([v])
    assert v.viewer_languages.get("ja", 0) >= 1
    assert v.viewer_languages.get("en", 0) == 1
    assert v.viewer_languages.get("zh", 0) == 1

def test_creator_vs_viewer_shows_foreign_interest():
    from youtube_ugc import comments as cm
    v = mk()
    v.language = "ja"  # 発信者は日本語
    v.comments = ["Amazing!", "好想去", "가고 싶다"]  # 視聴者は外国語
    cm.annotate_viewer_languages([v])
    cv = cm.creator_vs_viewer([v])
    assert cv["creator"].get("ja") == 1
    assert sum(n for lg, n in cv["viewer"].items() if lg != "ja") >= 3

def test_lexicon_sentiment_positive_negative_neutral():
    from youtube_ugc.comments import _lexicon_sentiment
    assert _lexicon_sentiment(["最高でした", "beautiful"]) == "positive"
    assert _lexicon_sentiment(["高すぎる", "crowded"]) == "negative"
    assert _lexicon_sentiment(["普通の動画"]) == "neutral"
    assert _lexicon_sentiment([]) is None

def test_sentiment_summary_counts():
    from youtube_ugc import comments as cm
    vids = [mk(vid="a"), mk(vid="b"), mk(vid="c")]
    vids[0].comments = ["最高！"]
    vids[1].comments = ["高すぎる"]
    vids[2].comments = ["普通"]
    cm.annotate_sentiment(vids, use_llm=False)
    ss = cm.sentiment_summary(vids)
    assert ss["positive"] == 1 and ss["negative"] == 1 and ss["neutral"] == 1
    assert abs(ss["positive_ratio"] - 1/3) < 1e-9


# ---- LLM クライアント（ネット非依存の単体検証） -------------------------
def test_llm_extract_json_from_fenced_text():
    from youtube_ugc.llm import _extract_json
    assert _extract_json('ここ: ```json\n{"a": ["x"]}\n```') == {"a": ["x"]}
    assert _extract_json('[1, 2, 3] 以上') == [1, 2, 3]
    assert _extract_json("JSONなし") is None

def test_classify_batch_keyword_fallback():
    from youtube_ugc.topics import classify_batch
    out = classify_batch([("v1", "高山 ラーメン グルメ"), ("v2", "高山 温泉 旅館")], use_llm=False)
    assert "食・グルメ" in out["v1"]
    assert "温泉・宿" in out["v2"]


# ---- 多言語の地名（インバウンド対応） -----------------------------------
def test_resolve_aliases_known_place():
    from youtube_ugc.config import resolve_aliases
    al = resolve_aliases("高山")
    assert "高山" in al and "Takayama" in al and "다카야마" in al

def test_resolve_aliases_unknown_place_with_extra():
    from youtube_ugc.config import resolve_aliases
    al = resolve_aliases("無名温泉", ["Mumei Onsen"])
    assert al == ["無名温泉", "Mumei Onsen"]

def test_resolve_aliases_reverse_lookup_romaji():
    # ローマ字や英語名で入力しても、内蔵辞書の多言語表記群に解決される
    from youtube_ugc.config import resolve_aliases
    for q in ("富山", "toyama", "Toyama"):
        al = resolve_aliases(q)
        assert "富山" in al and "Toyama" in al and "도야마" in al


# ---- Wikidata 自動取得（任意の観光地対応・ネット非依存の単体検証） --------
def test_wikidata_normalize_strips_admin_suffixes():
    from youtube_ugc.place_names import _normalize
    out = _normalize(["Toyama Prefecture", "富山県", "Beppu (Oita)"])
    # 接尾辞・括弧を除いた「核」も併せて生成される
    assert "Toyama" in out and "富山" in out and "Beppu" in out
    # 元の表記も保持
    assert "Toyama Prefecture" in out

def test_wikidata_normalize_keeps_place_when_suffix_is_part_of_name():
    # 「別府」「甲府」などは「府」を削って1文字にしてはいけない
    from youtube_ugc.place_names import _normalize
    out = _normalize(["別府", "甲府"])
    assert out == ["別府", "甲府"]
    assert "別" not in out and "甲" not in out

def test_wikidata_normalize_strips_ko_th_admin_terms():
    # 韓国語「부」(府)・タイ語「จังหวัด」(県)を落として市レベルの核も得る
    from youtube_ugc.place_names import _normalize
    out = _normalize(["교토부", "จังหวัดเกียวโต"])
    assert "교토" in out and "เกียวโต" in out

def test_wikidata_selects_entity_richest_in_target_languages():
    # 候補2件のうち、中韓タイのラベルが揃っている方を選ぶ
    from youtube_ugc.place_names import _select_best_labels, _label_values
    entities = {
        "Q1": {"labels": {"ja": {"value": "別府"}, "en": {"value": "Beppu"}}},  # 日英のみ
        "Q2": {"labels": {                                                        # 多言語あり
            "ja": {"value": "別府市"}, "en": {"value": "Beppu"},
            "zh": {"value": "別府市"}, "ko": {"value": "벳푸시"}, "th": {"value": "เบ็ปปุ"},
        }},
    }
    best = _select_best_labels(entities, order=["Q1", "Q2"])
    vals = _label_values(best)
    assert "벳푸시" in vals and "เบ็ปปุ" in vals  # 多言語項目(Q2)が選ばれる

def test_wikidata_fetch_is_graceful_offline():
    # ネット不通でも例外を投げず list を返す（フォールバック）
    from youtube_ugc.place_names import fetch_aliases
    result = fetch_aliases("存在しない観光地XYZ", use_cache=False)
    assert isinstance(result, list)

def test_alias_filter_lets_foreign_video_through():
    # 日本語名「高山」を含まない英語動画は、別表記 Takayama で初めて通る
    en = mk(title="TAKAYAMA Food Tour", desc="best trip", tags=["Takayama"])
    assert is_relevant(en, ["高山"]) is False              # 日本語名のみ→取りこぼす
    assert is_relevant(en, ["高山", "Takayama"]) is True   # 多言語表記→拾える

def test_config_no_aliases_uses_place_only():
    from youtube_ugc.config import CollectConfig
    assert CollectConfig(place="高山", use_aliases=False).resolved_aliases() == ["高山"]
    assert "Takayama" in CollectConfig(place="高山").resolved_aliases()
