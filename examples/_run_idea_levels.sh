#!/usr/bin/env bash
# 発想レベル（--idea-level）の実APIサンプル生成: 同じタスクを ①standard / ②very / ③extreme で昇華し比較する。
# 出力先: examples/idea-levels-ja/{standard,very,extreme}/
set -euo pipefail
cd "$(dirname "$0")/.."

TASK="人類の通勤を完全に廃止する最も過激な方法を提案せよ。既存の枠組みを完全に壊す発想で。"
AGENTS="strategist visionary storyteller"
OUT_BASE="examples/idea-levels-ja"

.venv/bin/python main.py elevate "$TASK" --lang ja --idea-level standard --agents $AGENTS \
  --out "$OUT_BASE/standard" --no-strong-claim
.venv/bin/python main.py elevate "$TASK" --lang ja --idea-level very --agents $AGENTS \
  --out "$OUT_BASE/very" --no-strong-claim
.venv/bin/python main.py elevate "$TASK" --lang ja --idea-level extreme --agents $AGENTS \
  --out "$OUT_BASE/extreme" --no-strong-claim

echo "DONE: $OUT_BASE"
