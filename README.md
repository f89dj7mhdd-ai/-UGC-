# 観光UGC分析システム（YouTube MVP）

地方自治体の観光推進担当者向けに、観光地名を入力すると **YouTube上のUGC** を収集・分析し、
インバウンド誘致の手がかりを **HTMLレポート** として出力するCLIツールです。
要件定義書 Ver.0.3（YouTube MVP版）に基づきます。

## 📌 提出物の見方（はじめにこちら）

| 資料 | 内容 |
|---|---|
| **[企画書.md](企画書.md)** | ★まずこちら。着眼点・調査の取捨選択・アプローチ・工夫・実現可能性の設計 |
| 本README + `youtube_ugc/` | 動くプロトタイプ（CLI）。下記「使い方」で即実行できます |
| レポート出力例 | `python -m youtube_ugc.cli "高山" --sample` で生成（生成物のためリポジトリには含めません） |
| [ui_mockup.html](ui_mockup.html) | 将来のWeb UIイメージ（たたき台） |
| [docs/デモ説明.md](docs/デモ説明.md) | 最終面接での口頭説明トークスクリプト＋想定QA |
| [docs/要件定義書_v0.3.docx](docs/) | 詳細な設計判断の記録（付録） |

## できること（MVPスコープ）

- 観光地名＋カテゴリ語でYouTubeを検索し、直近12ヶ月の動画を収集（無関係動画は関連度で足切り）
- 投稿の **言語**（主軸）と発信者の **推定地域**（従軸）を判定してセグメント分割
- **エンゲージメント**（いいね＋コメント）で反応を評価。率は登録者数を分母（非公開は絶対数のみ）
- エンゲージメント上位群に偏在する **高反応パターン**（話題・言語・尺・時期）を抽出
- **コメント分析**：コメントの言語構成から「視聴者側」の市場を推定し、発信者言語と比較（発信者≠視聴者の補正）。**感情分析**でポジ率・ネガ要因を把握
- **話題分類のLLM化**：表現揺れ・多言語をLLMで吸収（キーがなければキーワード辞書にフォールバック）
- 非専門の担当者向けに **示唆** を文章化したHTMLレポートを生成

※ トレンド/季節性・競合比較・他SNS・外部指標突合は拡張フェーズ（本MVP対象外）。

### LLM（任意・あれば精度向上）

話題分類とコメント感情分析にLLMを使えます。**無くてもキーワード/多言語辞書で動作**します。

- **Ollama（ローカル・キー不要・推奨）**: `ollama serve` を起動し `OLLAMA_MODEL`（既定 `llama3.1`）を指定
- **Anthropic**: `ANTHROPIC_API_KEY` を設定
- **OpenAI**: `OPENAI_API_KEY` を設定

優先順位は `LLM_PROVIDER` 明示 → Anthropic → OpenAI → ローカルOllama。いずれも無ければ辞書動作。

## セットアップ

追加依存はありません（Python 3.10+）。テストを使う場合のみ:

```bash
pip install -r requirements.txt   # pytest のみ
```

## 使い方

### サンプルデータで試す（APIキー不要）

```bash
python -m youtube_ugc.cli "高山" --sample --out report_takayama.html
```

`data/sample_videos.json`（高山＝Takayamaの模擬データ）で動作確認できます。

### 本番（YouTube Data API v3）

1. Google CloudでYouTube Data API v3を有効化し、APIキーを取得
2. 環境変数に設定（キーをコードに書かない）

```bash
export YOUTUBE_API_KEY="あなたのキー"
python -m youtube_ugc.cli "高山" --max 50 --out report.html --open
```

APIキーがあれば自動で実収集、なければサンプルにフォールバックします。

### 主なオプション

| オプション | 説明 | 既定 |
|---|---|---|
| `--sample` | サンプルデータで実行 | - |
| `--months N` | 収集期間（月） | 12 |
| `--max N` | 収集件数上限（quota対策） | 50 |
| `--aliases "a,b"` | 地名の別表記を手動追加 | - |
| `--auto-aliases` | Wikidataから多言語の地名を自動取得（任意の観光地に対応・要ネット） | - |
| `--no-aliases` | 日本語名のみで収集（偏りを再現する比較用） | - |
| `--no-comments` | コメントを収集しない（視聴者層・感情分析を省く） | - |
| `--no-llm` | LLMを使わずキーワード/辞書のみ | - |
| `--out PATH` | 出力HTMLパス | `report_<place>.html` |
| `--open` | 生成後にブラウザで開く | - |

### 地名の多言語化（インバウンド対応の要）

日本語名だけで検索すると日本語コンテンツに偏り、訪日客のUGCを取りこぼす。そこで地名を各市場の言語表記でも検索・照合する。

- 主要観光地は**内蔵辞書**でカバー（`config.py` の `PLACE_ALIASES`）。日本語名・ローマ字名どちらで入力しても同じ表記群に解決される。
- 辞書に無い**任意の観光地**は `--auto-aliases` で**Wikidataから多言語名を自動取得**（一度取得した結果は `data/alias_cache.json` にキャッシュ）。
- 取得失敗・オフライン時は内蔵辞書／地名そのものに**自動フォールバック**する。

```bash
# 偏りの比較（日本語名のみ → 多言語）
python -m youtube_ugc.cli "高山" --sample --no-aliases   # 限定的
python -m youtube_ugc.cli "高山" --sample                # 多言語（既定）

# 辞書に無い地名をWikidataで自動対応（要ネット）
python -m youtube_ugc.cli "別府" --auto-aliases
```

> 注: Wikidataの取得結果は、行政区分の接尾辞（県/Prefecture 等）を含む場合があり、簡易的な正規化で核となる表記も併せて生成しています。同名地名の曖昧性は先頭ヒットを採用する簡易方式です（拡張余地）。

## 構成

``` 
youtube_ugc/
  models.py     … Videoデータモデル（取得可能な指標のみ）
  config.py     … 収集設定・カテゴリ語・市場区分
  collector.py  … YouTube収集 / サンプル収集 / 関連度フィルタ
  detect.py     … 言語・地域の判定（要件6.4）
  place_names.py… 地名の多言語化（Wikipedia言語間リンク / Wikidata）
  topics.py     … 話題分類（LLM＋キーワード辞書フォールバック）
  comments.py   … コメント分析（視聴者言語構成・感情）
  llm.py        … LLMクライアント（Ollama / Anthropic / OpenAI 自動検出）
  metrics.py    … エンゲージメント集計（要件7）
  segment.py    … 言語/地域セグメント・市場区分・クロス集計（要件8）
  patterns.py   … 高反応パターン抽出
  pipeline.py   … 収集→付与→集計→示唆の統合
  report.py     … HTMLレポート生成（要件11）
  cli.py        … CLIエントリ
data/sample_videos.json … 動作確認用サンプル（コメント付き）
tests/test_analysis.py  … ユニットテスト（36件）
```

## テスト

```bash
python -m pytest -q          # pytestがあれば
python tests/test_analysis.py  # 簡易実行（下記参照）
```

## データ取り扱いの注意（要件6）

- インプレッション・共有数は第三者UGCではYouTube APIで取得できないため扱いません。
- エンゲージメント率の分母は登録者数。非公開チャンネルは率を出さず絶対数で扱います。
- 地域は発信者の自己申告（推定値）であり、視聴者の地域ではありません。
- 実運用前にAPI利用規約・個人情報・データ保持方針の確認が必要です（要件6.6）。
```
