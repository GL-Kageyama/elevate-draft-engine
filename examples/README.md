# Examples — サンプル蓄積

タスクごとに **発散（各エージェント草案）→ 統合（成果物）** の実行例を保存する。
wisdom-council-layer の `examples/` の体裁を踏襲。

## フォルダ構成

| フォルダ | タスク | エージェント数 | 状態 |
|----------|--------|--------------|------|
| `health-ai/` | 健康AIの企画 | 3（strategist / humanist / differentiator） | 実API出力 |

## 使い方

**実行して保存:**
```bash
# 実API（ゲートウェイ）で3エージェント・実行例を保存
.venv/bin/python main.py elevate "健康AIの企画" \
  --agents strategist humanist differentiator --out examples/health-ai

# モックで一気通貫確認（API不要）
.venv/bin/python main.py compare "健康AIの企画" --mock --evaluate
```

## 各タスクのファイル

- `input.md` — 元のタスク
- `draft_{agent}.md` — 各エージェントの独立草案（末尾に「最強の主張」）
- `reconciliation.md` — 統合の下地（矛盾解決推理。最終化が読む思考の土台）
- `elevated.md` — 統合成果物（推理 → 最終化の結果）

全ファイル Markdown（`.md`）で保存する。

実APIはゲートウェイが間欠的に空応答を返すため、再試行上限6回
（`CLAUDE_MAX_RETRIES`）で自己回復させる。
