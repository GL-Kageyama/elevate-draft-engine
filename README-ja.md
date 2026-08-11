**言語:** [English](README.md) | [日本語](README-ja.md) | [中文](README-zh.md)

# elevate-draft-engine

<p align="center">
  <img src="assets/repo-hero.png" width="100%" alt="elevate-draft-engine">
</p>

**複数のAIがそれぞれ別の視点から書いた答えをぶつけ合って、どの単一の視点にもない一段高い答えを生むエンジン。**

AIが一発で出す「平均的な良い答え」を超えるために、**DIVERGE（発散）→ SYNTHESIZE（昇華）** の2段構えを取る。

```
            タスク
              │
              ├─→ [Draft: strategist]     価値
              ├─→ [Draft: differentiator] 独自性
              ├─→ [Draft: humanist]       共感
              ├─→ [Draft: futurist]       将来性
              ├─→ [Draft: designer]       体験設計
              ├─→ [Draft: visionary]      世界観
              ├─→ [Draft: implementer]    実現性
              └─→ [Draft: storyteller]    物語
                      │
                      ↓
             [昇華推理 Aufheben]        ← 各草案の一面性を否定しつつ、真理の契機を保存し、
                      │                   矛盾を包括する一段高い枠組みを創出（思考の土台。読者向けではない）
                      ↓
             [最終化 Finalize]           ← 止揚推理だけを読み、超越的統合解を単発生成を上回る明瞭な成果物に仕上げる
                      │
                      ↓
                最終成果物
```

- **DIVERGE**: 8種のクリエイターエージェントが、それぞれ**極限まで逸脱した**独立草案を生成。役割多様性（system）＋温度多様性で独立を保証。**発想レベル**（`--idea-level`）で発散の行き先を選ぶ: standard（0.9・既定）/ very（1.2）/ extreme（1.5）。各レベルに段階的な発散ヒントが対になる。妥協や中間解は素材にならない——後の昇華で一段高い次元へ引き上げるための、あえて先鋭化した個別解を出す。
- **SYNTHESIZE**（核心）: 全草案を読み、**否定・保存・高次化**の三契機で止揚する昇華推理（発想レベルと同じ温度）→ 止揚推理だけを読む最終化（temp 0.0）。単一観点の草案にはない超越的な統合解を構成する。
  - 例えば strategist の「収益」と humanist の「共感」の衝突は、論理的な妥協（条件付き受容）ではなく、両者の真理を**同時に成立させる新たな枠組み**へ止揚される。
  - 「昇華が単発生成を上回る」は**設計目標**。`compare` による実測で検証する（[昇華優位性の計測](#昇華優位性の計測compare) を参照）。
  - `synthesize()` は**外部草案も受け付ける**。人間の専門家が書いた分析、別モデルの出力、過去の成果物など、出所を問わず「複数の異なる視点」を突っ込めば超越的な統合解を返す。

## 評価の5軸（ポリシー密着）

`--evaluate` の採点は、**このエンジンが「良い成果物」だと信じていること**（ポリシー: 複数の独立した視点を昇華して単一視点を超える成果物を生む）を5つの軸に分解し、それぞれ 0.0〜1.0 で測る。

最初の3軸は「発散 → 昇華 → 超越」というエンジンの動きの質を、残る2軸は成果物の仕上がりの質を測る。

| 軸 | 概要 | 高得点（0.7〜0.8） | 低得点（0.0〜0.4） |
|---|---|---|---|
| **多様性** | 物事を色々な立場・分野から眺めているか | 複数の視点・価値観を横断し、分野を広く賄っている | ひとつの見方に閉じている |
| **統合性** | 違いを「並べた」のではなく「噛み合わせた」か | 視点間の矛盾を解決し、相互に連結した構造になっている | 断片の寄せ集め・併記（平均化も不合格） |
| **超越性** | どの単一視点にもなかった新しい見方が生まれたか | 統合を経て初めて得られる新たな視点が明確にある | どれかの草案の焼き直し |
| **誠実性** | 確かなことと不確かなことを区別しているか | 不確実な点は条件付き・前提として明示している | 根拠のないことを断定している |
| **実用性** | 実際にどう進めて誰がどう使うか、筋道が見えるか | 実行の筋道と利用者が具体的に描ける | 抽象的で実行可能性が確認できない |

採点のルール:

- **重みは均等（各 0.20）**: `5軸overall = 多様性×0.20 + 統合性×0.20 + 超越性×0.20 + 誠実性×0.20 + 実用性×0.20`
- **全軸「高いほど良い」**: 全5軸ともスコアが高いほど良い成果物を示す（反転ロジックはない）。
- **採点アンカー**: 0.5 = 無難（凡庸） / 0.7〜0.8 = 確かに良い / 0.9 以上 = 凡庸な生成では出ない「固有の枠組み・見方の転換」。凡庸な出力に 0.7 以上をつけない。
- **盲検**: 評価は生成とは独立した評価専用モデルが、成果物の出所・生成方法を知らされずに行う。

## 品質評価（overall に統合）

`--evaluate` の overall は、5軸評価に**品質評価（定番さ・独自性）**を掛け算で統合する。
5軸評価は「定番さ・独自性」を測らないため、素の生成（指示のみ）が定番タスクで無難な回答を
出しても 5軸 overall が高止まりし、独自性の差が反映されない。品質評価がこの死角を埋める。

| 観点 | 概要 | 高いほど |
|---|---|---|
| **新奇度** | そのタスクの「典型的な回答」からどの程度逸脱しているか | 目新しく、定番レパートリーに収まっていない |
| **独自性** | 定番レパートリーにない固有の視点・概念枠組み・造語・哲学があるか | 固有の枠組みがある |
| **意外性** | 読み手の予想を裏切る要素があるか | 予想を裏切る |

overall の式（α = 0.25。`0.75` は `1−α`）:

    overall = 5軸overall × (α + (1−α) × 品質スコア)
    品質スコア = (新奇度 + 独自性 + 意外性) / 3

- **定番回答は大幅に減点される**: 品質スコア 0.2（定番）なら係数 0.40、0.8（独自）なら係数 0.85。
- **Pass しきい値は 0.60**: 品質評価の掛け算で overall の絶対値が下がるため、5軸単独時代の 0.70 から再調整。
- **`--no-quality`** で品質評価なし（5軸のみの overall）に戻せる。

## エージェント（agents/）

**1エージェント=1ファイル**方式で `agents/{name}.md` に配置する。正本はファイル。
エンジンは起動時に `agents/*.md` を読み込み、
frontmatter の `name` をエージェント名、本文（ペルソナ）をシステムプロンプトとして使う。

```markdown
---
name: strategist
description: 価値の観点。最大の市場価値・成功条件・競合優位。…
---

You are the **Strategist**, a voice of value and markets.
…
```

**エージェントを追加する**: `agents/{name}.md` を追加する（再起動で読込まれる）か、
実行中は `add_agent(name, system_prompt)` で追加する。削除は `remove_agent(name)`。

**草案のテーゼ集中形式**: 各エージェントの草案は完全な分析レポートではなく、後の昇華に渡す
**先鋭化した1つのテーゼ**である（エージェントファイルの「草案の作り方」に組込み済み）。
**核心的主張**（3文以内）・**根拠**（箇条書き3点以内・各1文）・**前提**（1文・省略可）の
3要素のみで500〜800字に収める。草案が分析レポート化すると昇華が全てを拾おうとして過剰包摂し、
検証不能な数字を捏造して utility が落ちる。テーゼに絞ることで対立構造が鮮明になり、速度と昇華品質を同時に改善する。
`DRAFT_MAX_LENGTH`（1000字）を超える草案は不完全扱いで再生成される。「反論されそうな点」は
**付けない**——草案に弱点を先読みさせると自由な逸脱が萎縮するため、反論の検出は昇華段階の
Aufheber が引き受ける。

デフォルト8エージェントは全クリエイター目線で統一されており、エージェント同士の
**生産的衝突**が昇華解の源泉になる。懐疑・批判は昇華段階の Aufheber が
引き受ける（草案同士の矛盾を検出して止揚する）。

エージェントは `./install.sh` で Claude Code のサブエージェント（Agent tool / @-mention）
としても呼べるようになる。ただし**エンジンはサブエージェントを使わない**——
`agents/*.md` をリポジトリ内から直接読む。オーケストレーションは常に Python エンジン側。

| # | ファイル | 観点 |
|---|---------|------|
| 1 | `designer` | 体験設計 |
| 2 | `differentiator` | 独自性 |
| 3 | `futurist` | 将来性 |
| 4 | `humanist` | 共感 |
| 5 | `implementer` | 実現性 |
| 6 | `storyteller` | 物語 |
| 7 | `strategist` | 価値 |
| 8 | `visionary` | 世界観 |

## 多言語対応（--lang）

エンジンは en / ja / zh の3言語に対応する（既定は **en**）。
言語は `--lang {en,ja,zh}` フラグで指定し、環境変数 `ELEVATE_DRAFT_ENGINE_LANG`、
さらに未指定なら既定 `en` の順で解決される。

| 領域 | 言語の扱い |
|---|---|
| エージェント | `agents/{name}.md`（en）・`agents/{name}-ja.md`（ja）・`agents/{name}-zh.md`（zh）。`--agents strategist` のように**ベース名で指定すれば言語に依存しない** |
| LLMプロンプト | `prompts/{lang}.json`（engine 定数・品質ルーブリック・mock テキスト） |
| CLI / 保存テンプレート | `locales/{lang}.json` |
| 品質評価JSON | キーは常に英語（`novelty`/`originality`/`surprise`/`rationale`）。ラベル表示のみ言語別 |

`agents/` 直下に無接尾辞のファイルを置くと **en 扱い**になる
（独自エージェントを日本語で書きたい場合は `agents/{name}-ja.md`、中国語なら `-zh.md` を置く）。

## クイックスタート

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests/ -q     # 259件

# API 不要のモックでパイプライン確認
.venv/bin/python main.py compare "健康AIの企画" --mock --evaluate

# 実API（claude -p 独立起動）でサンプル取得・保存
.venv/bin/python main.py elevate "健康AIの企画" \
  --engine claude-code --agents strategist humanist differentiator --out examples/health-ai
```

認証は環境変数で供給する（APIキーをコードに含めない）。

| 環境変数 | 用途 |
|---|---|
| `ANTHROPIC_API_KEY` | 通常の Anthropic API |
| `ANTHROPIC_AUTH_TOKEN` + `ANTHROPIC_BASE_URL` | Claude Code 互換ゲートウェイ |
| `CLAUDE_MIN_INTERVAL_SECONDS` | リクエスト最小間隔（既定 2.0 秒。空応答対策） |
| `CLAUDE_MAX_RETRIES` | 空応答/エラー時の再試行上限（既定 6 回。間欠的空応答対策） |

## CLI

```bash
python main.py generate "タスク"                 # 素のAI（単発生成）, 1 call
python main.py diverge "タスク"                  # 8エージェントで草案生成・一覧出力
python main.py synthesize draft1.md draft2.md  # 外部草案を昇華（核心）
python main.py elevate "タスク"                  # diverge → synthesize 一気
python main.py compare "タスク"                  # generate vs elevate 両方出力
python main.py compare "タスク" --evaluate       # + 品質評価（5軸+新奇度・独自性・意外性）でスコア比較
python main.py compare "タスク" --evaluate --runs 10        # N回反復で統計集計
python main.py compare "タスク" --evaluate --baseline best-of-n  # 帰無仮説比較
python main.py compare "タスク" --evaluate --no-strong-claim      # 断言枠アブレーション
python main.py compare "タスク" --evaluate --logic-check          # 最終化後に論理一貫性の復元工程
python main.py calibrate "タスク" --mock --runs 3                 # 温度近似の誤差定量
python main.py improve "タスク" --rounds 3                        # 昇華版→改修の草案→昇華 のループで反復改善
python main.py improve "タスク" --rounds 3 --evaluate             # + 各ラウンド採点・頭打ちで早期停止
```

共通オプション: `--lang {en,ja,zh}`（言語指定。既定 en）/
`--mock`（API不要）/ `--engine sdk|claude-code`（既定 sdk）/
`--method two-stage|single-pass`（既定 two-stage）/
`--idea-level {standard,very,extreme}`（発散・昇華の極端さ。既定 standard）/
`--agents strategist humanist`（エージェントを限定）/ `--out DIR`（成果物の保存先。省略時は
`outputs/{タスク名}/` に自動保存。diverge / elevate / compare / improve すべて全成果物を対象）/
`--runs N`（compare を N 回反復）/ `--baseline single|best-of-n`（比較対象）/
`--no-strong-claim`（断言枠除去）/ `--logic-check`（論理一貫性の復元工程。既定は無効）/
`--rounds N` / `--min-improve` / `--quality-ceiling`（improve の反復回数・頭打ちしきい値・高品位停止しきい値。高品位は既定 0.75 で有効）/
`--output-format '<JSON>'`（出力形式の明示指定。省略時は実APIでタスクから LLM が動的に抽出）/
`--knowledge 'TEXT'` / `--knowledge-file PATH` / `--ask-knowledge`（前提知識。素材・制約・背景情報を生成の土台として全段階に注入。相互排他。保存先 `--out/knowledge.md`。実行時パラメータは `--out/parameters.md` に保存）

### 出力フォーマット認識（分野ごとの形式）

パイプライン開始前に、タスクから期待される出力形式を LLM が動的に抽出し、全段階に注入する
（キャッチコピーなら候補形式、分析系ならテーゼ形式、直接成果物は長さ範囲で完全性判定）。
抽出失敗時のフォールバック・安全弁・`OutputFormat` テーブルは [docs/output-format.md](docs/ja/output-format.md)。

### 前提知識の注入（--knowledge）

素材・制約・背景情報を生成の土台として全段階に注入する（fmt=形の制約と対になる内容の制約）。
指定方法・注入範囲・保存先の詳細は [docs/knowledge.md](docs/ja/knowledge.md)。

### 発想レベル（--idea-level）

`--idea-level {standard,very,extreme}` で、発散（diverge）と昇華推理（Aufheben）がどこまで極端に踏み込むかを選ぶ。2つのレバーで適用する: 段階的な**発散ヒント**（主レバー。reasoning モデルは温度 1 越えを確実には反映しないため）＋**温度**（補助）。最終化はレベルに関わらず常に温度 0.0。

| レベル | 温度 | 意味 |
|---|---|---|
| `standard`（既定） | 0.9 | 一般的に極端 — 従来の挙動（後方互換） |
| `very` | 1.2 | 非常に極端 |
| `extreme` | 1.5 | 極度に極端 |

`sdk` エンジンは温度とヒントの両方を API に渡す。`claude-code` エンジン（温度つまみなし）はヒントのみでレベルを近似する。2レバー設計の根拠と温度 1 越えのゲートウェイ所見は [docs/idea-levels.md](docs/ja/idea-levels.md)。

### 昇華優位性の計測（compare）

「昇華」と「単発生成（または昇華しない最良草案選択）」を同一入力・同一評価器で走らせ、
スコアと勝率を実測する。`--runs N` で統計集計（勝率・95%CI・効果量）を出力し、各 run の
raw / elevated は `render_comparison.py` で比較ドキュメント化できる。
詳細は [docs/measurement.md](docs/ja/measurement.md)。

### 反復改善（improve）

昇華版を土台に「改修草案 → 昇華」を繰り返し磨くループ。各 round は `round_NN/` に保存され、
`--evaluate` で高品位停止・頭打ち停止の安全弁が働く。詳細は [docs/measurement.md](docs/ja/measurement.md)。

### 生成エンジン（--engine）

| エンジン | 起動方式 | 用途 |
|---|---|---|
| `sdk`（既定） | `anthropic` SDK で1プロセス内から直呼び | 通常の Anthropic API |
| `claude-code` | 呼び出しごとに `claude -p` を独立起動 | Claude Code 互換ゲートウェイ・不安定な SDK 経路の回避 |

`claude-code` エンジンは草案・昇華推理・最終化を**それぞれ独立プロセス**で生成する
（中間コンテキストの混線なし・打ち切り時の再試行もプロセス単位）。温度はシステムプロンプト
内の指示文で近似する（`温度≥0.5` → 発散重視 / `温度<0.5` → 一貫性重視）。
SDK 経由の空応答は `CLAUDE_MAX_RETRIES`（既定6）で再試行する。

## インストールとファサード skill

`./install.sh` で Claude Code から呼べるようにする（agents + skill を symlink 設置）。

```bash
./install.sh            # グローバル: ~/.claude/agents/ + ~/.claude/skills/
./install.sh --local    # プロジェクト: .claude/agents/ + .claude/skills/
./install.sh --uninstall
```

インストールされるもの:
- **8クリエイターエージェント**（`strategist` 等）— Agent tool / @-mention で起動可能
- **`elevate-draft-engine` skill（ファサード）** — `main.py` への薄い呼び出しインターフェース

**ファサード skill の設計**: elevate の skill は**オーケストレーターではなくファサード**である。
オーケストレーション（DIVERGE → 昇華推理 → 最終化、完全性ガード、温度制御、`claude -p` 安定経路）
はすべて Python エンジン側にあり、skill は `main.py` を起動して結果を報告するだけ。エンジンを
バイパスしてサブエージェントを直接昇華するのはダウングレードなので行わない。

```bash
# 呼び出し例（Claude Code 内で Skill: elevate-draft-engine を使用）
# Args: {"task": "健康AIの企画", "agents": ["strategist", "humanist", "differentiator"]}
```

## Python API

`elevate.DraftEngine` で generate / diverge / synthesize / elevate を直接呼べる
（外部草案もそのまま昇華できる）。使用例は [docs/api.md](docs/ja/api.md)。

## リポジトリ構成

```
elevate-draft-engine/
├── agents/                     # エージェント正本（1エージェント=1ファイル、frontmatter + ペルソナ）
│   ├── designer.md
│   ├── differentiator.md
│   ├── futurist.md
│   ├── humanist.md
│   ├── implementer.md
│   ├── storyteller.md
│   ├── strategist.md
│   └── visionary.md
├── elevate/
│   ├── __init__.py             # from elevate import DraftEngine, Draft
│   └── engine.py               # DraftEngine（agents/ 読込 + synthesize）
├── adapters/
│   ├── claude_client.py        # Claude API クライアント（スロットル・空応答再試行込み）
│   └── claude_code_client.py   # claude -p 独立起動（--engine claude-code）
├── evaluation/
│   ├── evaluator.py            # 品質評価（5軸 + 掛け算統合。--evaluate 用）
│   └── quality.py              # 品質評価の3観点（新奇度・独自性・意外性）
├── skills/
│   └── elevate-draft-engine/SKILL.md   # ファサード skill（main.py を起動。オーケストレーションは委譲）
├── tests/                      # 259件
├── examples/                   # 実行サンプル集（分野横断テストケース等）
│   └── multi-domain/           # 分野横断フォーマット認識+知識注入の検証ケース
├── docs/                       # 深掘り詳細（output-format / knowledge / measurement / api）
├── CLAUDE.md                   # プロジェクト指示（AI向け）
├── HISTORY.md                  # 開発履歴（ルーブリック再調整・旧実測等）
├── install.sh                  # agents + skill を Claude Code 検出先へ symlink 設置
├── main.py                     # 薄い CLI（generate / diverge / synthesize / elevate / compare / improve / calibrate）
├── render_comparison.py        # compare 出力から「素AI生成 vs 昇華版」比較ドキュメントを生成
├── requirements.txt
└── README.md
```

設計の要点（詳細はコードのコメント参照）:
- **完全性ガード（broken output → regenerate）**: 打ち切り/不完全は再生成（最大3回）、直らなければ明示的失敗
- **成果物のファイル逐次保存（既定）**: `--out` を省略すると `outputs/{タスク名}/` に全成果物（input / draft_{agent} / reconciliation / raw / elevated / evaluation_* / measurement）を自動保存する。draft は生成前に空の `draft_{agent}.md` として作られ、生成中に逐次追記される。全8草案の完了を待たずにファイルが育つため、途中で失敗しても生成済み分は消えない。打ち切りで再生成するときはファイルを空に戻してから再開する。claude-code エンジンは `claude -p --output-format stream-json` の累積テキスト差分を `on_chunk` で流す（SDK エンジンは全文が揃った時点で一括書き込み）
- **昇華推理の完全性は長さ基準**（最小30字）: 昇華推理は「思考の土台」で文終端記号で終わらないため
- **最終化は止揚推理だけを読み**、中間思考（草案同士の比較・弁証法の手続き説明）が成果物に漏れない

## 制約と失敗モード

- **昇華優位性は実測で検証する**: 「昇華が単発生成を上回る」は設計目標。実測記録は [HISTORY.md](./HISTORY.md) の実測記録セクションに一元管理している。`compare --runs N` で n を積んで検証し、勝率 50% を下回る結果も正常な知見として開示する。
- **コスト**: DIVERGE（8草案）+ aufheben + finalize は単発生成の約10回分の API 呼び出しになる。
  優位性の検証はそのコストに見合うタスクに限るのが実用的である。
- **温度近似**: `claude-code` エンジンでは温度をシステムプロンプトの指示文で近似する
  （SDK 直呼びの空応答回避のため）。数値としての温度再現性はない。
- **評価の系統**: `--evaluate` の評価は生成と独立した評価エンジン（evaluation/）で行うが、
  評価モデルが生成モデルと同系である限り、完全な独立評価ではない。結果は傾向として読む。
- **アブレーションの範囲**: `--no-strong-claim` は枠の有無だけを変える。枠の貢献度が正にも負にも
  出る可能性があり、どちらの結果もそのまま報告する。
