#!/usr/bin/env bash
# 統合優位性の実証: サンプル行列（分野×エージェント数×ループ数）
#
# full（8体×1回）だけでなく、エージェント数を振り、分野をばらけさせて実測する。
# 各 run は run_NN/ に素AI生成（raw.md）と統合版（elevated.md）を両方保存する。
# 完了後: python render_comparison.py examples/<dir> で比較ドキュメントを生成する。
#
# 使い方:
#   bash examples/run_comparison_matrix.sh            # 全サンプルを順次実行
#   bash examples/run_comparison_matrix.sh 1 2        # 指定番号だけ実行
set -eo pipefail  # -u は空配列の展開で死ぬため使わない
cd "$(dirname "$0")/.."

ROOT="$(pwd)"
PY="$ROOT/.venv/bin/python"
CLAUDE_MIN_INTERVAL_SECONDS="${CLAUDE_MIN_INTERVAL_SECONDS:-2}"  # 空応答対策の間隔
TOTAL=6

run() {
  local n="$1"; local label="$2"; local task="$3"; local agents="$4"; local runs="$5"
  echo "=================================================="
  echo "[$n/$TOTAL] $label (agents=${agents:-全8}, runs=$runs)"
  echo "  タスク: $task"
  echo "=================================================="
  local agents_args=()
  if [ -n "$agents" ]; then agents_args=(--agents $agents); fi
  $PY main.py compare "$task" \
    --engine claude-code --evaluate --runs "$runs" \
    "${agents_args[@]}" \
    --out "$ROOT/examples/$label"
  $PY render_comparison.py "$ROOT/examples/$label" --html
  echo "[$n/$TOTAL] $label 完了"
}

# 1: 死・喪失・遺産（報告の推奨6が指定する中心タスク）— 8体×3回
run 1 legacy-memory \
  "認知症の母の記憶を子孫に残す「デジタル遺産」装置の設計" \
  "" 3

# 2: 事業 — 3体×5回
run 2 ledger-startup \
  "ミニマリスト向け家計簿アプリ「Rei」の事業計画" \
  "strategist differentiator humanist" 5

# 3: 歌詞（creative）— 2体×3回
run 3 rain-phone-lyrics \
  "「雨上がりの電話」というタイトルの歌謡曲の歌詞を書け" \
  "storyteller humanist" 3

# 4: 科学仮説 — 5体×3回
run 4 ml-hypothesis \
  "深層学習の解釈可能性に関する新しい科学仮説を提案せよ" \
  "differentiator futurist implementer strategist visionary" 3

# 5: 建築 — 4体×3回
run 5 rain-house \
  "個人邸「雨を聴く家」の建築設計コンセプト" \
  "designer visionary differentiator humanist" 3

# 6: 文化・哲学 — 6体×2回
run 6 aging-essay \
  "老いと記憶についてのエッセイ" \
  "humanist storyteller visionary futurist differentiator strategist" 2

echo ""
echo "=== 全サンプル完了 ==="
