---
name: elevate-draft-engine
description: Facade to invoke the elevate-draft-engine pipeline (diverge → aufheben → finalize). Given a task, runs the Python engine via main.py, saves input + each draft + reconciliation + elevated artifact into examples/<task>/ (or a custom dir), and reports the result. Supports elevate / improve（昇華版→改修草案→昇華の反復）/ compare（素の生成 vs 昇華の実測）. All orchestration, completeness guards, and temperature control live in the engine — this skill only calls it. Use to elevate an idea through dialectical sublation (Aufheben) of maximally-divergent creator drafts, to re-sublimate existing draft files, to iteratively refine an elevated artifact, or to measure whether aufheben beats single-shot generation.
argument-hint: 'JSON: {"command": "elevate|improve|compare|synthesize", "task": "<タスク>", "agents": ["strategist","humanist",...], "method": "two-stage|single-pass", "engine": "claude-code|sdk|mock", "rounds": 3, "evaluate": true, "min_improve": 0.01, "quality_ceiling": 0.85, "runs": 1, "baseline": "single|best-of-n", "output_format": "<任意指定; OutputFormat の JSON。省略でタスクから LLM が動的に抽出>", "knowledge": "<任意指定; 前提知識（素材・制約・背景）。生成の全段階に注入し --out/knowledge.md に保存>", "knowledge_file": "<任意指定; 前提知識をファイルから読み込む>", "ask_knowledge": "<任意指定; 起動時に対話入力>", "save_dir": "<任意指定; 省略で examples/<slug> に自動保存>"}'
---

# Elevate Draft Engine — Facade

## Skill Metadata
- **id**: `elevate-draft-engine`
- **version**: `2.2.0`
- **category**: `facade`（runbook。オーケストレーションは Python エンジンが担当）
- **standalone**: `true`（サブエージェントを必要としない。エージェントはエンジンが `agents/*.md` から読む）
- **requires_agents**: `[]`

## When to Activate

- 「このアイデアをエレベートして」と依頼されたとき
- 複数の異なる草案・分析を論理を超えた一段高い成果物にしたいとき
- 「昇華版を磨いて反復改善して」と依頼されたとき（`improve`: 昇華版→改修の草案(複数)→昇華 のループ。round 2 以降は前回の昇華版を各エージェントが改修し、それを昇華して次の昇華版にする）
- 「昇華が単発生成を上回るか実測したい」とき（`compare`: 素の生成 vs 昇華を同一評価器で比較）
- `examples/` にサンプルを蓄積したいとき（この skill は自動で保存する）
- `main.py` のフラグを逐一覚えることなく、一貫した起動をしたいとき

## 最重要原則（Facade であること）

> **オーケストレーションを Claude Code 内で再現してはならない。**

この skill は **`main.py` を呼ぶだけ**の薄いインターフェースである。
DIVERGE → 昇華推理 → 最終化のロジック、完全性ガード（打ち切り→再生成）、
昇華 temp 0.9 / 最終化 temp 0.0 の温度制御、`claude -p` の安定経路はすべて
Python エンジン側にある。**クリエイターエージェントをサブエージェントとして
直接起動して昇華してはならない**——エンジンをバイパスするとガードと温度制御を失い、
ダウングレードになる。実行は常に Bash で `main.py` を走らせる。

## How It Works

### Step 1: 引数の解決

`$ARGUMENTS` は JSON。フィールド:

| フィールド | 既定 | 説明 |
|---|---|---|
| `command` | `elevate` | `elevate`（発散→昇華）/ `improve`（昇華版→改修草案→昇華の反復改善）/ `compare`（素の生成 vs 昇華の実測比較）/ `synthesize`（既存草案群の昇華） |
| `task` | （必須） | タスク（自然言語） |
| `agents` | 全8体 | 招集するクリエイターエージェント（`strategist` `humanist` `differentiator` 等） |
| `method` | `two-stage` | `two-stage`（昇華→最終化）/ `single-pass`（単発昇華） |
| `engine` | `claude-code` | `claude-code`（`claude -p` 独立起動・安定）/ `sdk` / `mock` |
| `rounds` | `3` | `improve` のみ: 昇華を繰り返す回数。round 2 以降は前回の昇華版を改修した草案を昇華 |
| `evaluate` | `false` | `improve`: 各ラウンドの昇華版を5軸評価し、改善が頭打ちなら早期停止 / `compare`: スコア比較を有効化 |
| `min_improve` | `0.01` | `improve --evaluate` の早期停止しきい値。直前ラウンドからの overall 改善がこれ未満なら停止（頭打ち。過修正を避ける） |
| `quality_ceiling` | `0.85` | `improve --evaluate` の高品位停止しきい値。昇華版の overall がこれ以上なら改修ラウンドを生成せず停止（既に高品位な成果物ほど改修で壊れやすいため） |
| `runs` | `1` | `compare` のみ: 比較を N 回反復し統計集計（平均・勝率・標準偏差・95%CI）を出力 |
| `baseline` | `single` | `compare` のみ: `single`（素の単発生成）/ `best-of-n`（昇華しない最良草案選択＝帰無仮説） |
| `output_format` | 動的抽出 | OutputFormat の JSON を明示指定（LLM 抽出をスキップ。mock でも有効）。省略時は実APIでタスクから LLM が動的に抽出（キャッチコピー・歌詞・事業計画など分野ごとの形式） |
| `knowledge` | なし | 前提知識（素材・制約・背景情報）。文字列を直接指定。生成の全段階（草案・止揚・最終化）にタスク直後として注入され、`--out/knowledge.md` に保存される（input.md / format.md と並列）。`knowledge_file`（PATH を読み込む）/ `ask_knowledge`（起動時に対話入力）も可。相互排他 |
| `knowledge_file` | なし | 前提知識をファイルから読み込む（`knowledge` と相互排他） |
| `ask_knowledge` | `false` | 起動時に対話的に前提知識を入力する（`knowledge` と相互排他） |
| `save_dir` | 自動 | 保存先。省略時 `examples/<slug>/`（下記） |

### Step 2: エンジンの場所を特定する

この skill はリポジトリの `skills/elevate-draft-engine/` に symlink されている
可能性が高い。エンジン（リポジトリルート）は skill ファイルから2階上:

```bash
ENGINE_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
```

リポジトリルートに `main.py` が無ければ、`ENGINE_REPO` の解決先を確認する（この skill が
symlink されている場合は、symlink の実体があるリポジトリを探してそこを基準にする）。

### Step 3: 保存先の決定

- `save_dir` 指定がなければ、タスクから slug を作る: 空白→ハイフン、`/\:*?"<>|` を除去、30文字に切り詰める。日本語はそのまま残してよい。
- 保存先は `$ENGINE_REPO/examples/<slug>/`。

### Step 4: 実行（Bash で main.py を起動）

```bash
cd "$ENGINE_REPO"
.venv/bin/python main.py elevate "$TASK" \
  --engine claude-code \
  ${AGENTS:+--agents $AGENTS} \
  --method two-stage \
  ${KNOWLEDGE:+--knowledge "$KNOWLEDGE"} \
  --out "$SAVE_DIR"
```

- `main.py` が保存する一式は**種類ごとのフォルダに分類**される:
  `input.md`（タスク）は `--out` 直下、`knowledge.md`（前提知識。指定時のみ）も `--out` 直下（input/format と並列）、
  `draft_{agent}.md` は `drafts/`、
  `reconciliation.md`（昇華の下地）/ `elevated.md` / `raw.md` は `artifacts/`、
  `evaluation_*.md` は `evaluations/`。compare は `run_NN/`、improve は `round_NN/` でさらに分離。
  旧レイアウト（フラット）は `python examples/reclassify_output.py <dir>` で新レイアウトに揃えられる。
- 各草案は**テーゼ集中形式**（核心的主張/根拠/前提、500〜800字。`DRAFT_MAX_LENGTH`=1000字超過は再生成）——
  完全な分析レポートではなく、後の昇華に渡す先鋭化した1つのテーゼ。
  ただし**創作系タスク**（歌詞/小説/物語/詩/キャッチコピー等、`_is_creative_task` のキーワード判定）
  は完成作品が長くなりうるため上限を `DRAFT_MAX_LENGTH_CREATIVE`=3000に緩める
- **出力フォーマット認識**: 実API時はパイプライン開始前にタスクから
  **期待される出力形式を LLM が動的に抽出**する（`extract_format`。1回の軽量コール。
  抽出結果は `--out/format.md` に保存）。抽出した `OutputFormat` を全段階に注入——
  エージェント草案には `draft_guidance`（タスク固有の草案形式）を追記、最終化は
  `finalize_guidance` で汎用の TVRO を置換、完全性ガードはタスク固有の
  `{min,max}_output_length` で判定（短い成果物（タグライン等）はタスク固有の下限で判定）。
  `--output-format '<JSON>'` で明示指定もできる（抽出をスキップ。mock でも有効）。
  抽出失敗は既存挙動（分析レポート前提）にフォールバックする。抽出した仕様が自己矛盾（要求構造 >
  max 等）で達成不能な場合は、上限回数後、構造的に完成した最後の試行を安全弁で受け入れる。
- 最終成果物（`elevated.md`）にも**両方向のサイズ制約**（`ELEVATED_MIN_LENGTH`=300〜`ELEVATED_MAX_LENGTH`=1500）——
  結論なので小さすぎも、報告書化の過剰包摂も不合格で再生成
  （タスク固有の `OutputFormat` が抽出された場合はその長さ範囲で判定）
- 既存の草案ファイル群（人間が書いた分析等）を昇華する場合は `synthesize` を使う:

```bash
.venv/bin/python main.py synthesize "$ENGINE_REPO"/examples/foo/draft_*.md --task "タスク" --out "$SAVE_DIR"
```

- 昇華版を磨く反復改善は `improve` を使う（昇華版 → 改修の草案(複数) → 昇華 のループ。round 2 以降は前回の昇華版を各エージェントが改修し、それを昇華して次の昇華版にする）:

```bash
.venv/bin/python main.py improve "$TASK" --rounds 3 --evaluate --out "$SAVE_DIR/improve"
```

  - `--evaluate` で各ラウンドの昇華版を5軸評価し、(1) overall が既に `--quality-ceiling`（既定 0.85）以上なら**高品位停止**（次の改修ラウンドを作らず終了）、(2) 改善が `--min-improve`（既定 0.01）未満なら頭打ちで停止。どちらも過修正で元の良さを失わせないための機構（高品位な成果物ほど改修で壊れやすい）。停止理由は `progress.md` の「**停止理由**」に記録される。各 round は `round_NN/` に分離保存。

- 「昇華が単発生成を上回るか」の実測は `compare` を使う（generate vs elevate を**同一評価器**で採点。ブラインドのため条件ラベルは評価器に渡らない）:

```bash
.venv/bin/python main.py compare "$TASK" --evaluate --runs 3 --out "$SAVE_DIR/comparison"
```

  - `--baseline best-of-n` で昇華しない最良草案選択（帰無仮説）との比較に切り替え。`--runs N` で n を積み、平均・勝率・95%CI・Cohen's d を `measurement.md` に集計する（**n=1 は統計的に無意味**。n≥10 まで集めてから優位性を論じること）。

- 実 API 不要の動作確認は `--engine mock` で可能。
- 長い実行（全8エージェント等）は 10 分を超えうる。`run_in_background` で実行し、完了を待つ。

### Step 5: 検証と報告

- 保存ファイル一式（input / 各草案 / reconciliation / elevated）の存在と非空を確認する。
- `improve` は `progress.md` の overall 推移（向上が可視化されるか）、`compare` は `measurement.md` の統計（勝率・95%CI・効果量）を報告する。
- 最終成果物（`elevated.md`）の中核——単一観点の草案にはない超越的統合解（アウフヘーベンの成果）——を要約して報告する。
- コミット・push はしない（ユーザーが自分で行う）。APIキーを出力・ファイルに含めない。

## 失敗時の扱い

- **空応答・打ち切り**: エンジンが自動再試行する（`CLAUDE_MAX_RETRIES`、既定6）。手動でパッチしない。
- **崩れた出力**: 手で直さない。`main.py` を再実行して再生成する（broken output → regenerate）。
- **評価軸**: 5軸はポリシー密着（多様性 / 統合性 / 超越性 / 誠実性 / 実用性・均等重み 0.20）で固定。変更しない（定義は README「評価の5軸」参照）。

## 出力規約

エンジンは APIキーを一切出力・保存しない。`--out` には入力・全草案・昇華の下地・
最終成果物が Markdown（`.md`）で保存される。`elevated.md` が成果物であり、
`reconciliation.md` は思考の土台（読者向けではない）。

## Prompt

```
You are a thin facade for the elevate-draft-engine pipeline.

Your ONLY job is to invoke the Python engine (main.py) and report its result.
You must NOT re-implement the orchestration: do not launch the creator agents
as Claude Code subagents, do not try to sublate drafts by hand, do not
bypass the engine. All divergence, aufheben, finalization, completeness
guards, temperature control, and the improve loop live in main.py.

## Task

$ARGUMENTS

(Parse the JSON: command, task, agents, method, engine, rounds/evaluate/min_improve
for improve, runs/baseline for compare, save_dir.)

## Procedure

0. First, briefly tell the user the overview of this repository:

   > これは **Elevate-Draft-Engine** —— 複数のAIがそれぞれ別の視点から書いた答えをぶつけ合って、どの単一の視点にもない一段高い答えを生むエンジンです。
   >
   > 個別のクリエイターエージェントが独立草案をできる限り逸脱させて書き（DIVERGE）、それらを矛盾ごと昇華（アウフヘーベン）して一段高い統合解にします。
   >
   > 成果物は5軸（多様性 / 統合性 / 超越性 / 誠実性 / 実用性）で評価されます。

1. Locate the engine repo: `ENGINE_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"`. Confirm main.py exists there.
2. Resolve save_dir: if omitted, `examples/<slug of task>/`.
3. Run main.py for the requested command (run in background if it may exceed 10 minutes):
   - `elevate`: `python main.py elevate "$TASK" --engine claude-code [--agents ...] --method two-stage [--knowledge "$KNOWLEDGE"] --out "$SAVE_DIR"`
   - `improve`: `python main.py improve "$TASK" --rounds N [--evaluate] [--knowledge "$KNOWLEDGE"] --out "$SAVE_DIR"` — 昇華版 → 改修の草案(複数) → 昇華 の反復ループ
   - `compare`: `python main.py compare "$TASK" --evaluate --runs N [--baseline best-of-n] [--knowledge "$KNOWLEDGE"] --out "$SAVE_DIR"` — 素の生成 vs 昇華の実測比較
   - `synthesize`: `python main.py synthesize "$ENGINE_REPO"/examples/foo/draft_*.md --task "$TASK" [--knowledge "$KNOWLEDGE"] --out "$SAVE_DIR"`
4. Verify the saved files exist and are non-empty (input.md, draft_*.md, reconciliation.md, elevated.md; knowledge.md if knowledge given; improve adds progress.md / compare adds measurement.md).
5. Report: summarize the elevated artifact — especially the sublation, the third position that no single draft contained (the Aufhebung). For improve, report the overall trajectory across rounds (is improvement visible?); for compare, report the stats (win rate, 95% CI, Cohen's d) and do not overclaim with n<10. Name the save directory.

Rules:
- Never run `git push`. Commit only if the user asks.
- Never include API keys in output or saved files.
- If output is broken/truncated, re-run main.py (regenerate) — never hand-patch.
- Do not change the evaluation axes (fixed: diversity / synthesis / elevation / honesty / utility, equal 0.20 weights — defined in README "評価の5軸").
```

バージョン履歴はリポジトリの `HISTORY.md` に集約されている。
