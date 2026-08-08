# 計測記録: compare --runs 1 --evaluate

- **タスク**: 社内ナレッジ検索ツールの設計
- **日付**: 2026-08-08
- **エンジン**: claude-code（`claude -p` 独立起動）
- **エージェント**: 全8体（designer / differentiator / futurist / humanist / implementer / storyteller / strategist / visionary）
- **統合方式**: two-stage（矛盾解決推理 → 最終化）
- **評価器**: evaluation/ の5軸評価（同一評価器で両者を採点）
- **n**: 1（ユーザー選択「8エージェント 1run de OK」）

## 結果

| 対象 | overall | quality | logic | creativity | value | risk | 判定 |
|---|---|---|---|---|---|---|---|
| 素の生成（単発） | **0.758** | 0.85 | 0.80 | 0.85 | 0.80 | 0.85 | Pass |
| ELEVATE | **0.755** | 0.85 | 0.75 | 0.95 | 0.75 | 0.85 | Pass |
| 差（ELEVATE−素の生成） | **-0.003** | 0.00 | -0.05 | +0.10 | -0.05 | 0.00 | — |

## 読むときの注意（誠実な開示）

- **n=1 は統計的に無意味**。差 -0.003 はノイズの範囲内で、このデータは「統合の優位性」を
  実証するものではない。勝率も定義できない（1回の比較では集計されない）。
- 観察された傾向は「**ELEVATE は creativity が明確に高い（+0.10）が、logic・value がやや低い（-0.05）**」。
  統合成果物（elevated.md）は「組織の記憶層／ゾンビ知識／0件を心臓に置く設計」という
  単発生成にない枠組みへ再構成されており、その独自性が creativity に出た一方、
  具体性（logic・value）が単発生成の整った TVRO 構成にわずかに及ばなかった、と解釈できる。
- 続けて `compare --runs 10 --baseline best-of-n` 等を回して n を積み、差の分布を測ることが、
  このエンジンの存在理由を実証する次の一歩になる。勝率 50% を下回るタスクがあればその開示も含める。

## 成果物

- `raw.md` — 素の生成（単発）の出力
- `draft_{agent}.md` — 各エージェントの独立草案（8体）
- `reconciliation.md` — 矛盾解決推理（統合の下地）
- `elevated.md` — 統合成果物
- `input.md` — 元のタスク

計測コマンド:

```bash
python main.py compare "社内ナレッジ検索ツールの設計" \
  --engine claude-code --evaluate --runs 1 --out examples/knowledge-search
```
