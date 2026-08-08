---
name: elevate-draft-engine
description: Facade to invoke the elevate-draft-engine pipeline (diverge → aufheben → finalize). Given a task, runs the Python engine via main.py, saves input + each draft + reconciliation + elevated artifact into examples/<task>/ (or a custom dir), and reports the result. Supports elevate / improve（昇華版→改修草案→昇華の反復）/ compare（素の生成 vs 昇華の実測）. All orchestration, completeness guards, and temperature control live in the engine — this skill only calls it. Use to elevate an idea through dialectical sublation (Aufheben) of maximally-divergent creator drafts, to re-sublimate existing draft files, to iteratively refine an elevated artifact, or to measure whether aufheben beats single-shot generation.
argument-hint: 'JSON: {"command": "elevate|improve|compare|synthesize", "task": "<タスク>", "agents": ["strategist","humanist",...], "method": "two-stage|single-pass", "engine": "claude-code|sdk|mock", "rounds": 3, "evaluate": true, "min_improve": 0.01, "runs": 1, "baseline": "single|best-of-n", "save_dir": "<任意指定; 省略で examples/<slug> に自動保存>"}'
---

# Elevate Draft Engine — Facade

## Skill Metadata
- **id**: `elevate-draft-engine`
- **version**: `2.0.0`
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
| `min_improve` | `0.01` | `improve --evaluate` の早期停止しきい値。直前ラウンドからの overall 改善がこれ未満なら停止（過修正を避ける） |
| `runs` | `1` | `compare` のみ: 比較を N 回反復し統計集計（平均・勝率・標準偏差・95%CI）を出力 |
| `baseline` | `single` | `compare` のみ: `single`（素の単発生成）/ `best-of-n`（昇華しない最良草案選択＝帰無仮説） |
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
  --out "$SAVE_DIR"
```

- `main.py` が保存する一式: `input.md` / `draft_{agent}.md` / `reconciliation.md`（昇華の下地）/ `elevated.md`（最終成果物）
- 各草案は**テーゼ集中形式**（核心的主張/根拠/前提、500〜800字。`DRAFT_MAX_LENGTH`=1000字超過は再生成）——
  完全な分析レポートではなく、後の昇華に渡す先鋭化した1つのテーゼ。
  ただし**創作系タスク**（歌詞/小説/物語/詩/キャッチコピー等、`_is_creative_task` のキーワード判定）
  は完成作品が長くなりうるため上限を `DRAFT_MAX_LENGTH_CREATIVE`=3000に緩める
  （実測 2026-08-09: 歌詞1116字が1000字上限で3回失敗し行列が落ちた）
- 最終成果物（`elevated.md`）にも**両方向のサイズ制約**（`ELEVATED_MIN_LENGTH`=300〜`ELEVATED_MAX_LENGTH`=1500）——
  結論なので小さすぎも、報告書化の過剰包摂も不合格で再生成
- 既存の草案ファイル群（人間が書いた分析等）を昇華する場合は `synthesize` を使う:

```bash
.venv/bin/python main.py synthesize "$ENGINE_REPO"/examples/foo/draft_*.md --task "タスク" --out "$SAVE_DIR"
```

- 昇華版を磨く反復改善は `improve` を使う（昇華版 → 改修の草案(複数) → 昇華 のループ。round 2 以降は前回の昇華版を各エージェントが改修し、それを昇華して次の昇華版にする）:

```bash
.venv/bin/python main.py improve "$TASK" --rounds 3 --evaluate --out "$SAVE_DIR/improve"
```

  - `--evaluate` で各ラウンドの昇華版を5軸評価し、改善が `--min-improve`（既定 0.01）未満なら頭打ちで早期停止（過修正で元の良さを失わない）。各 round は `round_NN/` に分離保存、進捗は `progress.md` に記録。

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
- **評価軸**: 5軸はポリシー密着（多様性 / 統合性 / 超越性 / 誠実性 / 実用性・均等重み 0.20）で決定済み。ゴールポストは固定（2026-08-08 再調整(3)。安易に変更しない。定義は README「評価の5軸」参照）。

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

   > これは **Elevate-Draft-Engine** —— 複数の極端に逸脱した草案を、論理を超えた世界で昇華（アウフヘーベン）し、超越的な統合解を生むエンジンです。
   >
   > 個別のクリエイターエージェントが独立草案を、可能な限り逸脱・発散（DIVERGE）し、それらを論理を超えた世界で昇華（アウフヘーベン）し、超越的な統合解に到達します。
   >
   > 成果物は5軸（多様性 / 統合性 / 超越性 / 誠実性 / 実用性）で評価されます。

1. Locate the engine repo: `ENGINE_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"`. Confirm main.py exists there.
2. Resolve save_dir: if omitted, `examples/<slug of task>/`.
3. Run main.py for the requested command (run in background if it may exceed 10 minutes):
   - `elevate`: `python main.py elevate "$TASK" --engine claude-code [--agents ...] --method two-stage --out "$SAVE_DIR"`
   - `improve`: `python main.py improve "$TASK" --rounds N [--evaluate] --out "$SAVE_DIR"` — 昇華版 → 改修の草案(複数) → 昇華 の反復ループ
   - `compare`: `python main.py compare "$TASK" --evaluate --runs N [--baseline best-of-n] --out "$SAVE_DIR"` — 素の生成 vs 昇華の実測比較
   - `synthesize`: `python main.py synthesize "$ENGINE_REPO"/examples/foo/draft_*.md --task "$TASK" --out "$SAVE_DIR"`
4. Verify the saved files exist and are non-empty (input.md, draft_*.md, reconciliation.md, elevated.md; improve adds progress.md / compare adds measurement.md).
5. Report: summarize the elevated artifact — especially the sublation, the third position that no single draft contained (the Aufhebung). For improve, report the overall trajectory across rounds (is improvement visible?); for compare, report the stats (win rate, 95% CI, Cohen's d) and do not overclaim with n<10. Name the save directory.

Rules:
- Never run `git push`. Commit only if the user asks.
- Never include API keys in output or saved files.
- If output is broken/truncated, re-run main.py (regenerate) — never hand-patch.
- Do not change the evaluation axes (fixed: diversity / synthesis / elevation / honesty / utility, equal 0.20 weights — defined in README "評価の5軸").
```

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 2.0.0 | 2026-08-08 | 中核機構を「論理的な統合（synthesis）」から「弁証法的昇華（Aufheben）」へ衣替え。DIVERGE は温度0.9で極限まで逸脱し、昇華推理が否定・保存・高次化の三契機で矛盾を包括する枠組みを創出する。DIVERGE → AUFHEBEN → FINALIZE の3段構え（用語変更ではなく機構変更） |
| 1.3.0 | 2026-08-08 | 起動時にユーザーへリポジトリ全体の概要を改行・段落で簡潔に伝える手順を Procedure 冒頭に追加 |
| 1.2.0 | 2026-08-08 | 評価軸をポリシー密着5軸（多様性/統合性/超越性/誠実性/実用性・均等0.20）に再設計（README「評価の5軸」参照）。Risk 軸廃止 |
| 1.1.0 | 2026-08-08 | `improve`（統合版→改修草案→統合の反復）と `compare`（素の生成 vs 統合の実測）をファサードに追加 |
| 1.0.0 | 2026-08-08 | Initial version（ファサード。オーケストレーションは main.py に委譲） |
