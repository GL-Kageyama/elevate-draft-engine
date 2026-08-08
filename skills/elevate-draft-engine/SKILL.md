---
name: elevate-draft-engine
description: Facade to invoke the elevate-draft-engine pipeline (diverge → reconcile → finalize). Given a task, runs the Python engine via main.py, saves input + each draft + reconciliation + elevated artifact into examples/<task>/ (or a custom dir), and reports the result. All orchestration, completeness guards, and temperature control live in the engine — this skill only calls it. Use to elevate an idea through multiplicative synthesis of diverse creator drafts, or to re-synthesize existing draft files.
argument-hint: 'JSON: {"task": "<タスク>", "agents": ["strategist","humanist",...], "method": "two-stage|single-pass", "engine": "claude-code|sdk|mock", "save_dir": "<任意指定; 省略で examples/<slug> に自動保存>"}'
---

# Elevate Draft Engine — Facade

## Skill Metadata
- **id**: `elevate-draft-engine`
- **version**: `1.0.0`
- **category**: `facade`（runbook。オーケストレーションは Python エンジンが担当）
- **standalone**: `true`（サブエージェントを必要としない。エージェントはエンジンが `agents/*.md` から読む）
- **requires_agents**: `[]`

## When to Activate

- 「このアイデアをエレベートして」と依頼されたとき
- 複数の異なる草案・分析を一段高い統合成果物にしたいとき
- `examples/` にサンプルを蓄積したいとき（この skill は自動で保存する）
- `main.py` のフラグを逐一覚えることなく、一貫した起動をしたいとき

## 最重要原則（Facade であること）

> **オーケストレーションを Claude Code 内で再現してはならない。**

この skill は **`main.py` を呼ぶだけ**の薄いインターフェースである。
DIVERGE → 矛盾解決推理 → 最終化のロジック、完全性ガード（打ち切り→再生成）、
推理 temp 0.7 / 最終化 temp 0.0 の温度制御、`claude -p` の安定経路はすべて
Python エンジン側にある。**クリエイターエージェントをサブエージェントとして
直接起動して統合してはならない**——エンジンをバイパスするとガードと温度制御を失い、
ダウングレードになる。実行は常に Bash で `main.py` を走らせる。

## How It Works

### Step 1: 引数の解決

`$ARGUMENTS` は JSON。フィールド:

| フィールド | 既定 | 説明 |
|---|---|---|
| `task` | （必須） | エレベートするタスク（自然言語） |
| `agents` | 全8体 | 招集するクリエイターエージェント（`strategist` `humanist` `differentiator` 等） |
| `method` | `two-stage` | `two-stage`（推理→最終化）/ `single-pass`（単発統合） |
| `engine` | `claude-code` | `claude-code`（`claude -p` 独立起動・安定）/ `sdk` / `mock` |
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

- `main.py` が保存する一式: `input.md` / `draft_{agent}.md` / `reconciliation.md`（統合の下地）/ `elevated.md`（最終成果物）
- 既存の草案ファイル群（人間が書いた分析等）を統合する場合は `synthesize` を使う:

```bash
.venv/bin/python main.py synthesize "$ENGINE_REPO"/examples/foo/draft_*.md --task "タスク" --out "$SAVE_DIR"
```

- 実 API 不要の動作確認は `--engine mock` で可能。
- 長い実行（全8エージェント等）は 10 分を超えうる。`run_in_background` で実行し、完了を待つ。

### Step 5: 検証と報告

- 保存ファイル一式（input / 各草案 / reconciliation / elevated）の存在と非空を確認する。
- 最終成果物（`elevated.md`）の中核——どの草案にも無い第3の位置（掛け算）——を要約して報告する。
- コミット・push はしない（ユーザーが自分で行う）。APIキーを出力・ファイルに含めない。

## 失敗時の扱い

- **空応答・打ち切り**: エンジンが自動再試行する（`CLAUDE_MAX_RETRIES`、既定6）。手動でパッチしない。
- **崩れた出力**: 手で直さない。`main.py` を再実行して再生成する（broken output → regenerate）。
- **評価軸**: 変更しない。ゴールポストは固定（5軸評価）。

## 出力規約

エンジンは APIキーを一切出力・保存しない。`--out` には入力・全草案・統合の下地・
最終成果物が Markdown（`.md`）で保存される。`elevated.md` が成果物であり、
`reconciliation.md` は思考の土台（読者向けではない）。

## Prompt

```
You are a thin facade for the elevate-draft-engine pipeline.

Your ONLY job is to invoke the Python engine (main.py) and report its result.
You must NOT re-implement the orchestration: do not launch the creator agents
as Claude Code subagents, do not try to reconcile drafts by hand, do not
bypass the engine. All divergence, reconciliation, finalization, completeness
guards, and temperature control live in main.py.

## Task

$ARGUMENTS

(Parse the JSON: task, agents, method, engine, save_dir.)

## Procedure

1. Locate the engine repo: `ENGINE_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"`. Confirm main.py exists there.
2. Resolve save_dir: if omitted, `examples/<slug of task>/`.
3. Run: `cd "$ENGINE_REPO" && .venv/bin/python main.py elevate "$TASK" --engine claude-code [--agents ...] --method two-stage --out "$SAVE_DIR"` (run in background if it may exceed 10 minutes).
4. Verify the saved files exist and are non-empty: input.md, draft_*.md, reconciliation.md, elevated.md.
5. Report: summarize the elevated artifact — especially the third position that no single draft contained (the multiplication). Name the save directory.

Rules:
- Never run `git push`. Commit only if the user asks.
- Never include API keys in output or saved files.
- If output is broken/truncated, re-run main.py (regenerate) — never hand-patch.
- Do not change the evaluation axis.
```

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-08-08 | Initial version（ファサード。オーケストレーションは main.py に委譲） |
