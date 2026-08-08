#!/usr/bin/env bash
# コンパクト実測行列（2026-08-08 中立ベースラインで再登録）— 全7ケースを短時間で
#
# 観点: ①素AI比較（compare: generate vs elevate、ベースラインは中立化済み）
#       ②複数エージェント（同事業で2体 vs 4体） ③ループ回数（improve: 昇華版→改修草案→昇華）
#       ④分野のばらつき（事業/歌詞/科学）
#       ⑤分野横断の2体 improve サンプル（素AI比較なし）: 新規事業/小説プロット/キャッチコピー
#
# 各ケース: --engine claude-code（安定経路）・--evaluate・最小コール数（エージェント最小）
# compare は --runs 2 で統計（勝率・平均差）を measurement.md に集計し、
# check_matrix_progress.py の事前登録打ち切り規則（累積勝率≤50% かつ平均差≤0）に供する。
# 打ち切り判定は新設計の行列ドメイン（ledger-2agents ledger-4agents ml-hypothesis）のみ
# 集計する（旧設計の knowledge-search 等を混ぜない）。
# ⑤の improve ケース（素AI比較なし）は素の生成を呼ばず昇華版の相続的改善（progress.md）
# だけを記録するため、事前登録の打ち切り規則には供しない——分野横断の反復改善サンプル。
#
# 使い方:
#   bash examples/run_compact_matrix.sh            # 全7ケースを順次実行
set -eo pipefail
cd "$(dirname "$0")/.."

ROOT="$(pwd)"
PY="$ROOT/.venv/bin/python"
CLAUDE_MIN_INTERVAL_SECONDS="${CLAUDE_MIN_INTERVAL_SECONDS:-2}"  # 空応答対策の間隔
LOG="${ELEVATE_MATRIX_LOG:-/tmp/elevate_compact_matrix.log}"
TOTAL=7
ts() { date '+%H:%M:%S'; }

echo "[$(ts)] === コンパクト行列 開始（全7ケース）===" | tee "$LOG"

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

run_improve() {
  local n="$1"; local label="$2"; local task="$3"; shift 3
  echo "[$(ts)] [$n/$TOTAL] $label 開始 improve（agents: $*）" | tee -a "$LOG"
  $PY main.py improve "$task" \
    --engine claude-code --rounds 2 --evaluate \
    --agents "$@" \
    --out "$ROOT/examples/$label"
  echo "[$(ts)] [$n/$TOTAL] $label 完了（progress.md 保存）" | tee -a "$LOG"
}

# # 1: 事業計画（2体）— 素AI比較のベース
# run_compare 1 ledger-2agents \
#   "ミニマリスト向け家計簿アプリ「Rei」の事業計画を設計せよ" \
#   differentiator strategist

# # 2: 事業計画（4体・1の上位集合）— エージェント数の効果（2体 vs 4体）
# run_compare 2 ledger-4agents \
#   "ミニマリスト向け家計簿アプリ「Rei」の事業計画を設計せよ" \
#   differentiator strategist humanist visionary

# # 3: 歌詞 — ループ回数（improve rounds 2: 統合版→改修草案→統合）
# run_improve 3 lyrics-improve \
#   "「雨上がりの電話」というタイトルの歌謡曲の歌詞を書け" \
#   storyteller humanist

# 4: 科学仮説（2体）— 分野のばらつき
run_compare 4 ml-hypothesis \
  "深層学習の解釈可能性に関する新しい科学仮説を提案せよ" \
  differentiator futurist

# ---- 分野横断の2体 improve（素AI比較なし・2026-08-09）----
# 昇華版を相続的に磨く improve を、異なる分野 × 異なる2体ペアで回す。
# 素の生成を呼ばないため measurement.md（勝率）は作らず、progress.md の
# overall 推移だけを記録する（事前登録の打ち切り規則には供しない）。

# 5: 新規事業コンセプト（2体）— 価値 × 未来性
run_improve 5 concept-improve \
  "大学生向けの新しいアプリサービスのコンセプトを設計せよ" \
  strategist futurist

# 6: 短編小説のプロット（2体）— 物語 × 感情
run_improve 6 story-plot-improve \
  "無人駅を舞台にした短編小説のプロットを構想せよ" \
  storyteller humanist

# 7: 商品キャッチコピー（2体）— 独自性 × 世界観
run_improve 7 tagline-improve \
  "リサイクル素材のスニーカー『Maru』のキャッチコピーを開発せよ" \
  differentiator visionary

echo "[$(ts)] === 全サンプル完了 ===" | tee -a "$LOG"
echo "" | tee -a "$LOG"
$PY examples/check_matrix_progress.py --domains ledger-2agents ledger-4agents ml-hypothesis | tee -a "$LOG"
