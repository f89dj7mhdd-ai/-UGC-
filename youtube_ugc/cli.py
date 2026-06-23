"""CLIエントリ.

使い方:
  python -m youtube_ugc.cli "高山"                 # APIキーがあれば実収集、なければサンプル
  python -m youtube_ugc.cli "高山" --sample        # 強制的にサンプル
  python -m youtube_ugc.cli "高山" --max 80 --out report.html
"""
from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

from .collector import get_collector
from .config import CollectConfig
from .pipeline import run
from .report import render


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="youtube_ugc",
        description="観光地のYouTube UGCを分析しHTMLレポートを生成（MVP）。",
    )
    p.add_argument("place", help="観光地名（例: 高山）")
    p.add_argument("--sample", action="store_true", help="サンプルデータで実行（APIキー不要）")
    p.add_argument("--months", type=int, default=12, help="収集期間（月）。既定12")
    p.add_argument("--max", type=int, default=50, dest="max_videos", help="収集件数上限。既定50")
    p.add_argument("--out", default=None, help="出力HTMLパス。既定: report_<place>.html")
    p.add_argument("--open", action="store_true", help="生成後にブラウザで開く")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = CollectConfig(place=args.place, months_back=args.months, max_videos=args.max_videos)

    collector = get_collector(config, force_sample=args.sample)
    src = "サンプルデータ" if collector.__class__.__name__ == "SampleCollector" else "YouTube Data API"
    print(f"[収集] {args.place} を {src} から取得中 …", file=sys.stderr)

    result = run(config, collector)
    print(f"[完了] {result.summary.count} 件を分析しました。", file=sys.stderr)

    out = Path(args.out) if args.out else Path(f"report_{args.place}.html")
    out.write_text(render(result), encoding="utf-8")
    print(f"[出力] {out.resolve()}", file=sys.stderr)

    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
