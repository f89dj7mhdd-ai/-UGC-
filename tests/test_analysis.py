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
    assert is_relevant(mk(title="高山のグルメ"), "高山") is True
    assert is_relevant(mk(title="京都の寺", tags=[]), "高山") is False
