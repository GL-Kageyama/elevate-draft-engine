# elevate-draft-engine

**複数の全く異なった draft を統合して、一段高い成果物を生むエンジン。**

AIが一発で出す「平均的な良い答え」を超えるために、**DIVERGE（発散）→ SYNTHESIZE（統合）** の2段構えを取る。

```
            タスク
              │
              ├─→ [Draft: strategist]     価値
              ├─→ [Draft: differentiator] 独自性
              ├─→ [Draft: humanist]       共感
              ├─→ [Draft: futurist]       将来性
              ├─→ [Draft: designer]       体験設計
              ├─→ [Draft: visionary]      世界観
              ├─→ [Draft: implementer]    実現性
              └─→ [Draft: storyteller]    物語
                      │
                      ↓
             [矛盾解決推理 Reconcile]     ← エージェント同士の衝突を検出し、一段高い位置から解決
                      │                    （掛け算の発生点。読者向けではない思考の土台）
                      ↓
             [最終化 Finalize]           ← 解決済み推理だけを読み、B0級の明瞭な成果物に仕上げる
                      │
                      ↓
                最終成果物
```

- **DIVERGE**: 8種のクリエイターエージェント × 温度 0.7 で独立草案を生成。役割多様性（system）＋温度多様性で独立を保証。
- **SYNTHESIZE**（核心）: 全草案を読み、エージェント間の矛盾を解決する推理（temp 0.7）→ 解決済み推理だけを読む最終化（temp 0.0）。**どの草案にも無い第3の位置**を生む「掛け算」。
  - 例えば strategist の「収益」× humanist の「共感」の衝突は、単独のエージェントでは見えない統合解に収束する。
  - `synthesize()` は**外部草案も受け付ける**。人間の専門家が書いた分析、別モデルの出力、過去の成果物など、出所を問わず「複数の異なる視点」を突っ込めば一段高い統合を返す。

## エージェント（agents/）

wisdom-council-layer の `agents/` 方式を踏襲し、**1エージェント=1ファイル**で `agents/{name}.md`
に配置する。正本はファイル。エンジンは起動時に `agents/*.md` を読み込み、
frontmatter の `name` をエージェント名、本文（ペルソナ）をシステムプロンプトとして使う。

```markdown
---
name: strategist
description: 価値の観点。最大の市場価値・成功条件・競合優位。…
---

You are the **Strategist**, a voice of value and markets.
…
```

**エージェントを追加する**: `agents/{name}.md` を追加する（再起動で読込まれる）か、
実行中は `add_agent(name, system_prompt)` で追加する。削除は `remove_agent(name)`。

**草案の定型枠**: 各エージェントは草案の末尾に必ず「最強の主張」1セクションを付ける
（エージェントファイルの「草案の作り方」に組込み済み）。reconcile が各草案の最強の主張を
推測に頼らず確実に拾い、矛盾検出のモデル依存を下げる。本編の自由な論述・声・多様性は
そのまま保たれ、枠は断言に絞る。「反論されそうな点」は**付けない**——草案に弱点を
先読みさせると自由な論述が萎縮するため、反論の検出は統合段階の reconciler が引き受ける。

デフォルト8エージェントは全クリエイター目線で統一されており、エージェント同士の
**生産的衝突**が統合時の掛け算の源泉になる。懐疑・批判は統合段階の reconciler が
引き受ける（草案同士の矛盾を検出して解決する）。

| # | ファイル | 観点 | 着想元 |
|---|---------|------|--------|
| 1 | `designer` | 体験設計 | aesthetic-critic |
| 2 | `differentiator` | 独自性 | originality + anti-generic-filter |
| 3 | `futurist` | 将来性 | future-potential |
| 4 | `humanist` | 共感 | emotional-impact |
| 5 | `implementer` | 実現性 | quality-evaluator |
| 6 | `storyteller` | 物語 | brand narrative + storytelling |
| 7 | `strategist` | 価値 | business-value |
| 8 | `visionary` | 世界観 | philosophical + meaning |

## クイックスタート

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests/ -q     # 45件

# API 不要のモックでパイプライン確認
.venv/bin/python main.py compare "健康AIの企画" --mock --evaluate

# 実API（claude -p 起動・wisdom-council 方式）でサンプル取得・保存
.venv/bin/python main.py elevate "健康AIの企画" \
  --engine claude-code --agents strategist humanist differentiator --out examples/health-ai
```

認証は環境変数で供給する（APIキーをコードに含めない）。

| 環境変数 | 用途 |
|---|---|
| `ANTHROPIC_API_KEY` | 通常の Anthropic API |
| `ANTHROPIC_AUTH_TOKEN` + `ANTHROPIC_BASE_URL` | Claude Code 互換ゲートウェイ |
| `CLAUDE_MIN_INTERVAL_SECONDS` | リクエスト最小間隔（既定 2.0 秒。空応答対策） |
| `CLAUDE_MAX_RETRIES` | 空応答/エラー時の再試行上限（既定 6 回。間欠的空応答対策） |

## CLI

```bash
python main.py generate "タスク"                 # 素のAI（B0相当）, 1 call
python main.py diverge "タスク"                  # 8エージェントで草案生成・一覧出力
python main.py synthesize draft1.txt draft2.txt  # 外部草案を統合（核心）
python main.py elevate "タスク"                  # diverge → synthesize 一気
python main.py compare "タスク"                  # generate vs elevate 両方出力
python main.py compare "タスク" --evaluate       # + 5軸評価でスコア比較
```

共通オプション: `--mock`（API不要）/ `--engine sdk|claude-code`（既定 sdk）/
`--method m2v2|m2`（既定 m2v2）/
`--agents strategist humanist`（エージェントを限定）/ `--out DIR`（成果物保存）

### 生成エンジン（--engine）

| エンジン | 起動方式 | 用途 |
|---|---|---|
| `sdk`（既定） | `anthropic` SDK で1プロセス内から直呼び | 通常の Anthropic API |
| `claude-code` | 呼び出しごとに `claude -p` を独立起動 | Claude Code 互換ゲートウェイ・不安定な SDK 経路の回避 |

wisdom-council-layer の「エージェントは独立したサブエージェントとして起動する」方式に
倣い、`claude-code` エンジンは草案・推理・最終化を**それぞれ独立プロセス**で生成する
（中間コンテキストの混線なし・打ち切り時の再試行もプロセス単位）。温度はシステムプロンプト
内の指示文で近似する（`温度≥0.5` → 発散重視 / `温度<0.5` → 一貫性重視）。

**なぜ claude-code が主経路になりうるか**: このゲートウェイでは SDK 直呼びが間欠的に
`200 + 空content`（`stop_reason=max_tokens`、0文字）を返す（同一プロンプトで成功と失敗が
共存する、コンテンツ非依存の揺らぎ。長いプロンプトほど失敗率が上がる）。`claude -p` は
同一ゲートウェイ上で安定して完全出力を返すため、実測 2026-08-08 時点の実用経路である。
SDK 経由の空応答は `CLAUDE_MAX_RETRIES`（既定6）で再試行する。

## Python API

```python
from elevate import DraftEngine, Draft
from adapters.claude_client import ClaudeClient

engine = DraftEngine(ClaudeClient(), draft_temperature=0.7)

# 素のAI（B0相当）— 1 call
raw = engine.generate("健康AIの企画")

# エージェント管理
engine.list_agents()                 # 8種のデフォルトエージェント（agents/*.md から読込）
engine.add_agent("legal", "あなたは法規制の専門家です。")
engine.remove_agent("storyteller")

# Step 1: DIVERGE — 独立草案を生成（既定は全エージェント）
drafts = engine.diverge("健康AIの企画")

# Step 2: SYNTHESIZE — 複数の異なる草案を統合（核心）
elevated = engine.synthesize(drafts)     # 内部: reconcile → finalize
elevated = engine.synthesize(drafts, method="m2")   # 単発統合（旧 M2）

# 外部草案もそのまま統合できる
external = [Draft(agent="human-expert", content="..."), Draft(agent="other-model", content="...")]
elevated = engine.synthesize(external)

# 便利ラッパー: diverge → synthesize 一気
elevated = engine.elevate("健康AIの企画")
```

## リポジトリ構成

```
elevate-draft-engine/
├── agents/                     # エージェント正本（1エージェント=1ファイル、frontmatter + ペルソナ）
│   ├── designer.md
│   ├── differentiator.md
│   ├── futurist.md
│   ├── humanist.md
│   ├── implementer.md
│   ├── storyteller.md
│   ├── strategist.md
│   └── visionary.md
├── elevate/
│   ├── __init__.py             # from elevate import DraftEngine, Draft
│   └── engine.py               # DraftEngine（agents/ 読込 + synthesize）
├── adapters/
│   ├── claude_client.py        # Claude API クライアント（スロットル・空応答再試行込み）
│   └── claude_code_client.py   # claude -p 独立起動（wisdom-council 方式・--engine claude-code）
├── evaluation/
│   └── evaluator.py            # 5軸評価（自己完結。--evaluate 用）
├── tests/                      # 45件（engine 28 / client 6 / evaluator 11）
├── examples/                   # 実行サンプル集（wisdom-council 風。input + 各草案 + 成果物）
├── main.py                     # 薄い CLI
├── requirements.txt
└── README.md
```

## 設計の経緯（なぜ統合が核心なのか）

insight-synapse の ver1（単一軌道の逐次改良・加算型）は素の生成に -50pp で敗れた。
ver2 の仮説は「**複数の全く異なった草案を強制統合**（乗算型）」が素の生成を上回るというもの。
このリポジトリは ver2 の中核（M2v2: 2段階統合）を**単独のライブラリ**として切り出したもの。
実験ハーネス・過去の対照条件（B1/B2/C4）・設計書群は持ち込まず、統合エンジンに専念する。

検証済みの知見（insight-synapse dev 検証より）:
- 完全性ガード（broken output → regenerate）: 打ち切り/不完全は再生成（最大3回）、直らなければ明示的失敗
- 推理の完全性は**長さ基準**（最小30字）: 推理は「思考の土台」で文終端記号で終わらないため
- 最終化は解決済み推理だけを読み、中間思考（草案同士の比較）が成果物に漏れない
