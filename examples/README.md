# Examples — サンプル蓄積

タスクごとに **発散（各エージェント草案）→ 統合（成果物）** の実行例を保存する。

## フォルダ構成

| フォルダ | タスク | エージェント数 | 状態 |
|----------|--------|--------------|------|
| `health-ai/` | 健康AIの企画 | 3（strategist / humanist / differentiator） | 実API出力 |
| `knowledge-search/` | 社内ナレッジ検索ツールの設計 | 8（全クリエイター） | 実API出力 + 計測記録（compare, n=1） |
| `reading-log/` | 本を読む時間を確保する小さな仕組み | 1（storyteller） | 実API出力 + ストリーム保存の動作確認（空ファイル先作成→バーストで全文追記） |

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

## 実演: humanist エージェントの出力例

`health-ai/draft_humanist.md` は、8エージェントのうち humanist（共感）が
「健康AIの企画」に対して発散した草案の冒頭部分である。

> 私の仕事は最初から「健康」を再定義することだ。既存の健康AIは歩数・睡眠・心拍を測り、
> ゲーミフィケーションで貼り付け、機械としての身体を最適化する。それは「死なないこと」の
> 最適化であり、**死の否定**の上に築かれた産業だ。ここから一度自由に発散する。
>
> この業界は健康な人にしか投資しないから、死にゆく人は誰にも見捨てられている。
> 見捨てられた人が、この企画の主人公だ。
>
> **藤原浩一、73歳。** 元・建設会社の現場監督。ステージ4の膵臓がん。余命半年。

エージェントは単なる役割ラベルではなく、**具体的な人物を設定して感情の真実に降りる**
ところまで発散する。この草案が統合段階で他の観点（収益・独自性）とどう衝突し、
解消されるかは `reconciliation.md` → `elevated.md` に跡が残る。

## 計測サンプル（compare）

`knowledge-search/` は `compare --runs N --evaluate` による**統合優位性の実測**を
保存する。`--runs > 1` のとき各 run の成果物は `run_NN/` サブフォルダに分離保存され、
統計集計は `measurement.md` に残る（平均 overall 差・勝率）。

### 実測結果（2026-08-08, n=1）

| 対象 | overall | 判定 |
|---|---|---|
| 素の生成（単発） | **0.758** | Pass |
| ELEVATE | **0.755** | Pass |
| 差 | **-0.003** | — |

詳細は [knowledge-search/measurement.md](knowledge-search/measurement.md)。n=1 のため
差は統計的に無意味であり、**統合の優位性を実証するデータではない**ことを明示する。
観察された傾向は ELEVATE の creativity 高（+0.10）に対して logic・value 低（-0.05）——
統合成果物が単発生成にない枠組み（記憶層／ゾンビ知識）へ再構成された独自性の代償と読める。
`--runs 10` 等で n を積んだ分布を測るのが次の実証ステップである。
