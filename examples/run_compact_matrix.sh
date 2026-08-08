#!/usr/bin/env bash
# コンパクト実測行列（2026-08-08）— 全4観点を短時間で
#
# 観点: ①素AI比較（compare: generate vs elevate） ②複数エージェント（同事業で2体 vs 4体）
#       ③ループ回数（improve: 統合版→改修草案→統合） ④分野のばらつき（事業/歌詞/科学）
#
# 各ケース: --engine claude-code（安定経路）・--evaluate・最小コール数（エージェント最小）
# compare は --runs 2 で統計（勝率・平均差）を measurement.md に集計し、
# check_matrix_progress.py の事前登録打ち切り規則（累積勝率≤50% かつ平均差≤0）に供する。
#
# 使い方:
#   bash examples/run_compact_matrix.sh            # 全4ケースを順次実行
set -eo pipefail
cd "$(dirname "$0")/.."

ROOT="$(pwd)"
PY="$ROOT/.venv/bin/python"
CLAUDE_MIN_INTERVAL_SECONDS="${CLAUDE_MIN_INTERVAL_SECONDS:-2}"  # 空応答対策の間隔
LOG="${ELEVATE_MATRIX_LOG:-/tmp/elevate_compact_matrix.log}"
TOTAL=4
ts() { date '+%H:%M:%S'; }

echo "[$(ts)] === コンパクト行列 開始（全4ケース）===" | tee "$LOG"

run_compare() {
  local n="$1"; local label="$2"; local task="$3"; shift 3
  echo "[$(ts)] [$n/$TOTAL] $label 開始 compare（agents: $*）" | tee -a "$LOG"
  $PY main.py compare "$task" \
    --engine claude-code --evaluate --runs 2 \
    --agents "$@" \
    --out "$ROOT/examples/$label"
  $PY render_comparison.py "$ROOT/examples/$label" --html >/dev/null 2>&1 || true
  echo "[$(ts)] [$n/$TOTAL] $label 完了（measurement.md 保存）" | tee -a "$LOG"
}

# 1: 事業計画（2体）— 素AI比較のベース
run_compare 1 ledger-2agents \
  "ミニマリスト向け家計簿アプリ「Rei」の事業計画を設計せよ" \
  differentiator strategist

# 2: 事業計画（4体・1の上位集合）— エージェント数の効果（2体 vs 4体）
run_compare 2 ledger-4agents \
  "ミニマリスト向け家計簿アプリ「Rei」の事業計画を設計せよ" \
  differentiator strategist humanist visionary

# 3: 歌詞 — ループ回数（improve rounds 2: 統合版→改修草案→統合）
echo "[$(ts)] [3/$TOTAL] lyrics-improve 開始 improve（agents: storyteller humanist）" | tee -a "$LOG"
$PY main.py improve "「雨上がりの電話」というタイトルの歌謡曲の歌詞を書け" \
  --engine claude-code --rounds 2 --evaluate \
  --agents storyteller humanist \
  --out "$ROOT/examples/lyrics-improve"
echo "[$(ts)] [3/$TOTAL] lyrics-improve 完了（progress.md 保存）" | tee -a "$LOG"

# 4: 科学仮説（2体）— 分野のばらつき
run_compare 4 ml-hypothesis \
  "深層学習の解釈可能性に関する新しい科学仮説を提案せよ" \
  differentiator futurist

echo "[$(ts)] === 全サンプル完了 ===" | tee -a "$LOG"
echo "" | tee -a "$LOG"
$PY examples/check_matrix_progress.py | tee -a "$LOG"
