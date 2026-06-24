"""データモデル.

要件定義書 第6章「取得できる指標」に対応するフィールドのみを保持する。
インプレッション・共有数は取得不可のため持たない（第6.2節）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Video:
    """YouTube動画1件分のUGCデータ.

    取得できる指標のみで構成する（要件 6.2）。
    """

    video_id: str
    title: str
    description: str
    channel_id: str
    channel_title: str
    published_at: str  # ISO8601 文字列
    duration_seconds: int
    view_count: int
    like_count: int
    comment_count: int
    tags: list[str] = field(default_factory=list)

    # チャンネル属性（セグメント・エンゲージメント率に使用）
    channel_country: Optional[str] = None  # ISO国コード。任意入力のため空が多い
    subscriber_count: Optional[int] = None
    subscriber_hidden: bool = False  # 登録者数を非公開にしている場合 True

    # コメント（視聴者側の分析に使用）。本文テキストのみを少数保持する。
    comments: list[str] = field(default_factory=list)

    # 分析で付与される派生値（pipelineで設定）
    language: Optional[str] = None      # 判定言語コード (ja/en/zh/ko/th/other)
    region: Optional[str] = None        # 推定地域（国コード or "unknown"）
    region_confidence: str = "unknown"  # "declared" | "unknown"
    topics: list[str] = field(default_factory=list)
    viewer_languages: dict = field(default_factory=dict)  # コメント言語の構成 {lang: 件数}
    sentiment: Optional[str] = None     # "positive" | "negative" | "neutral" | None

    # ---- 計算プロパティ -------------------------------------------------
    @property
    def engagement(self) -> int:
        """エンゲージメント数 = いいね数 + コメント数（要件 7）。"""
        return self.like_count + self.comment_count

    @property
    def engagement_rate(self) -> Optional[float]:
        """エンゲージメント率 = エンゲージメント数 / 登録者数（要件 7）.

        登録者数が非公開、または0/不明の場合は算出せず None を返す。
        """
        if self.subscriber_hidden:
            return None
        if not self.subscriber_count:  # None または 0
            return None
        return self.engagement / self.subscriber_count

    @property
    def published_date(self) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(self.published_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    @property
    def duration_bucket(self) -> str:
        """尺の区分（高反応パターン分析に使用）。"""
        s = self.duration_seconds
        if s <= 60:
            return "shorts(〜60秒)"
        if s <= 600:
            return "mid(1〜10分)"
        return "long(10分〜)"

    @classmethod
    def from_dict(cls, d: dict) -> "Video":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in d.items() if k in known})
