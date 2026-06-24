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
    p.add_argument("--aliases", default=None,
                   help="地名の別表記をカンマ区切りで追加（例: 'Takayama,다카야마'）")
    p.add_argument("--no-aliases", action="store_true",
                   help="多言語表記を使わず日本語名のみで収集（偏りを再現する比較用）")
    p.add_argument("--auto-aliases", action="store_true",
                   help="Wikidataから多言語の地名を自動取得（辞書に無い任意の観光地に対応・要ネット）")
    p.add_argument("--no-comments", action="store_true",
                   help="コメントを収集しない（視聴者層・感情分析を省く）")
    p.add_argument("--no-llm", action="store_true",
                   help="LLMを使わずキーワード/辞書のみで分類・感情判定")
    p.add_argument("--out", default=None, help="出力HTMLパス。既定: report_<place>.html")
    p.add_argument("--open", action="store_true", help="生成後にブラウザで開く")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    extra = [a.strip() for a in args.aliases.split(",")] if args.aliases else []

    if args.auto_aliases and not args.no_aliases:
        from .place_names import fetch_aliases
        fetched = fetch_aliases(args.place)
        if fetched:
            extra += fetched
            print(f"[多言語名] 取得: {' / '.join(fetched)}", file=sys.stderr)
        else:
            print("[多言語名] 取得できませんでした（内蔵辞書／地名のみで続行）", file=sys.stderr)

    config = CollectConfig(
        place=args.place, months_back=args.months, max_videos=args.max_videos,
        extra_aliases=extra, use_aliases=not args.no_aliases,
        fetch_comments=not args.no_comments, use_llm=not args.no_llm,
    )
    print(f"[検索表記] {' / '.join(config.resolved_aliases())}", file=sys.stderr)
    if config.use_llm:
        from .llm import provider_name
        print(f"[LLM] プロバイダ: {provider_name()}（noneなら辞書/キーワードで動作）", file=sys.stderr)

    collector = get_collector(config, force_sample=args.sample)
    is_sample = collector.__class__.__name__ == "SampleCollector"
    src = "サンプルデータ" if is_sample else "YouTube Data API"
    if is_sample and not args.sample:
        print("[注意] YOUTUBE_API_KEY が未設定のためサンプルデータで動作します。", file=sys.stderr)
    if is_sample and args.place != "高山":
        print(f"[注意] サンプルは『高山』のみ収録。『{args.place}』は0件になります。"
              "実データは export YOUTUBE_API_KEY=... を設定してください。", file=sys.stderr)
    print(f"[収集] {args.place} を {src} から取得中 …", file=sys.stderr)

    result = run(config, collector)
    print(f"[完了] {result.summary.count} 件を分析しました。", file=sys.stderr)
    if result.summary.count == 0 and is_sample:
        print("[ヒント] 0件です。実APIで収集するには YOUTUBE_API_KEY を設定して再実行してください。",
              file=sys.stderr)

    out = Path(args.out) if args.out else Path(f"report_{args.place}.html")
    out.write_text(render(result), encoding="utf-8")
    print(f"[出力] {out.resolve()}", file=sys.stderr)

    if args.open:
        webbrowser.open(out.resolve().as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
