# elevate-draft-engine

<p align="center">
  <img src="assets/repo-hero.png" width="100%" alt="elevate-draft-engine">
</p>

**複数のAIがそれぞれ別の視点から書いた答えをぶつけ合って、どの単一の視点にもない一段高い答えを生むエンジン。**

AIが一発で出す「平均的な良い答え」を超えるために、**DIVERGE（発散）→ SYNTHESIZE（昇華）** の2段構えを取る。

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
             [昇華推理 Aufheben]        ← 各草案の一面性を否定しつつ、真理の契機を保存し、
                      │                   矛盾を包括する一段高い枠組みを創出（思考の土台。読者向けではない）
                      ↓
             [最終化 Finalize]           ← 止揚推理だけを読み、超越的統合解を単発生成を上回る明瞭な成果物に仕上げる
                      │
                      ↓
                最終成果物
```

- **DIVERGE**: 8種のクリエイターエージェント × 温度 0.9 で、それぞれが**極限まで逸脱した**独立草案を生成。役割多様性（system）＋温度多様性で独立を保証。妥協や中間解は素材にならない——後の昇華で一段高い次元へ引き上げるための、あえて先鋭化した個別解を出す。
- **SYNTHESIZE**（核心）: 全草案を読み、**否定・保存・高次化**の三契機で止揚する昇華推理（temp 0.9）→ 止揚推理だけを読む最終化（temp 0.0）。単一観点の草案にはない超越的な統合解を構成する。
  - 例えば strategist の「収益」と humanist の「共感」の衝突は、論理的な妥協（条件付き受容）ではなく、両者の真理を**同時に成立させる新たな枠組み**へ止揚される。
  - 「昇華が単発生成を上回る」は**設計目標**。現時点の実測では**過半のタスクで昇華が上回るが、タスク依存で素の生成が勝つこともある**。`compare` による実測で検証する。検証の経路は [昇華優位性の計測](#昇華優位性の計測compare) を参照。
  - `synthesize()` は**外部草案も受け付ける**。人間の専門家が書いた分析、別モデルの出力、過去の成果物など、出所を問わず「複数の異なる視点」を突っ込めば超越的な統合解を返す。

## 評価の5軸（ポリシー密着）

`--evaluate` の採点は、**このエンジンが「良い成果物」だと信じていること**（ポリシー）を測る。

> **複数の独立した視点を昇華して、単一視点を超える成果物を生む** —— このポリシーを5つの軸に分解し、それぞれ 0.0〜1.0 で採点する。

最初の3軸は「発散 → 昇華 → 超越」というエンジンの動きの質を、残る2軸は成果物の仕上がりの質を測る。

| 軸 | 概要 | 高得点（0.7〜0.8） | 低得点（0.0〜0.4） |
|---|---|---|---|
| **多様性** | 物事を色々な立場・分野から眺めているか | 複数の視点・価値観を横断し、分野を広く賄っている | ひとつの見方に閉じている |
| **統合性** | 違いを「並べた」のではなく「噛み合わせた」か | 視点間の矛盾を解決し、相互に連結した構造になっている | 断片の寄せ集め・併記（平均化も不合格） |
| **超越性** | どの単一視点にもなかった新しい見方が生まれたか | 統合を経て初めて得られる新たな視点が明確にある | どれかの草案の焼き直し |
| **誠実性** | 確かなことと不確かなことを区別しているか | 不確実な点は条件付き・前提として明示している | 根拠のないことを断定している |
| **実用性** | 実際にどう進めて誰がどう使うか、筋道が見えるか | 実行の筋道と利用者が具体的に描ける | 抽象的で実行可能性が確認できない |

採点のルール:

- **重みは均等（各 0.20）**: `5軸overall = 多様性×0.20 + 統合性×0.20 + 超越性×0.20 + 誠実性×0.20 + 実用性×0.20`
- **全軸「高いほど良い」**: 全5軸ともスコアが高いほど良い成果物を示す（反転ロジックはない）。
- **採点アンカー**: 0.5 = 無難（凡庸） / 0.7〜0.8 = 確かに良い / 0.9 以上 = 凡庸な生成では出ない「固有の枠組み・見方の転換」。凡庸な出力に 0.7 以上をつけない。
- **盲検**: 評価は生成とは独立した評価専用モデルが、成果物の出所・生成方法を知らされずに行う。

## 品質評価（overall に統合）

`--evaluate` の overall は、5軸評価に**品質評価（定番さ・独自性）**を掛け算で統合する。
5軸評価は「定番さ・独自性」を測らないため、素の生成（指示のみ）が定番タスクで無難な回答を
出しても 5軸 overall が高止まりし、独自性の差が反映されない。品質評価がこの死角を埋める。

| 観点 | 概要 | 高いほど |
|---|---|---|
| **新奇度** | そのタスクの「典型的な回答」からどの程度逸脱しているか | 目新しく、定番レパートリーに収まっていない |
| **独自性** | 定番レパートリーにない固有の視点・概念枠組み・造語・哲学があるか | 固有の枠組みがある |
| **意外性** | 読み手の予想を裏切る要素があるか | 予想を裏切る |

overall の式（α = 0.25。`0.75` は `1−α`）:

    overall = 5軸overall × (α + (1−α) × 品質スコア)
    品質スコア = (新奇度 + 独自性 + 意外性) / 3

- **定番回答は大幅に減点される**: 品質スコア 0.2（定番）なら係数 0.40、0.8（独自）なら係数 0.85。
  実測では素の生成（定番）と昇華（独自）の overall 差が、5軸単独の 0.03 程度から 0.4 前後に拡大する。
- **Pass しきい値は 0.60**: 品質評価の掛け算で overall の絶対値が下がるため、5軸単独時代の 0.70 から再調整。
- **`--no-quality`** で品質評価なし（5軸のみの overall）に戻せる。

## エージェント（agents/）

**1エージェント=1ファイル**方式で `agents/{name}.md` に配置する。正本はファイル。
エンジンは起動時に `agents/*.md` を読み込み、
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

**草案のテーゼ集中形式**: 各エージェントの草案は完全な分析レポートではなく、後の昇華に渡す
**先鋭化した1つのテーゼ**である（エージェントファイルの「草案の作り方」に組込み済み）。
**核心的主張**（3文以内）・**根拠**（箇条書き3点以内・各1文）・**前提**（1文・省略可）の
3要素のみで500〜800字に収める。草案が分析レポート化すると昇華が全てを拾おうとして過剰包摂し、
検証不能な数字を捏造して utility が落ちる。テーゼに絞ることで対立構造が鮮明になり、速度と昇華品質を同時に改善する。
`DRAFT_MAX_LENGTH`（1000字）を超える草案は不完全扱いで再生成される。「反論されそうな点」は
**付けない**——草案に弱点を先読みさせると自由な逸脱が萎縮するため、反論の検出は昇華段階の
Aufheber が引き受ける。

デフォルト8エージェントは全クリエイター目線で統一されており、エージェント同士の
**生産的衝突**が昇華解の源泉になる。懐疑・批判は昇華段階の Aufheber が
引き受ける（草案同士の矛盾を検出して止揚する）。

エージェントは `./install.sh` で Claude Code のサブエージェント（Agent tool / @-mention）
としても呼べるようになる。ただし**エンジンはサブエージェントを使わない**——
`agents/*.md` をリポジトリ内から直接読む。オーケストレーションは常に Python エンジン側。

| # | ファイル | 観点 |
|---|---------|------|
| 1 | `designer` | 体験設計 |
| 2 | `differentiator` | 独自性 |
| 3 | `futurist` | 将来性 |
| 4 | `humanist` | 共感 |
| 5 | `implementer` | 実現性 |
| 6 | `storyteller` | 物語 |
| 7 | `strategist` | 価値 |
| 8 | `visionary` | 世界観 |

## クイックスタート

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests/ -q     # 184件

# API 不要のモックでパイプライン確認
.venv/bin/python main.py compare "健康AIの企画" --mock --evaluate

# 実API（claude -p 独立起動）でサンプル取得・保存
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
python main.py generate "タスク"                 # 素のAI（単発生成）, 1 call
python main.py diverge "タスク"                  # 8エージェントで草案生成・一覧出力
python main.py synthesize draft1.md draft2.md  # 外部草案を昇華（核心）
python main.py elevate "タスク"                  # diverge → synthesize 一気
python main.py compare "タスク"                  # generate vs elevate 両方出力
python main.py compare "タスク" --evaluate       # + 品質評価（5軸+新奇度・独自性・意外性）でスコア比較
python main.py compare "タスク" --evaluate --runs 10        # N回反復で統計集計
python main.py compare "タスク" --evaluate --baseline best-of-n  # 帰無仮説比較
python main.py compare "タスク" --evaluate --no-strong-claim      # 断言枠アブレーション
python main.py compare "タスク" --evaluate --logic-check          # 最終化後に論理一貫性の復元工程
python main.py calibrate "タスク" --mock --runs 3                 # 温度近似の誤差定量
python main.py improve "タスク" --rounds 3                        # 昇華版→改修の草案→昇華 のループで反復改善
python main.py improve "タスク" --rounds 3 --evaluate             # + 各ラウンド採点・頭打ちで早期停止
```

共通オプション: `--mock`（API不要）/ `--engine sdk|claude-code`（既定 sdk）/
`--method two-stage|single-pass`（既定 two-stage）/
`--agents strategist humanist`（エージェントを限定）/ `--out DIR`（成果物の保存先。省略時は
`outputs/{タスク名}/` に自動保存。diverge / elevate / compare / improve すべて全成果物を対象）/
`--runs N`（compare を N 回反復）/ `--baseline single|best-of-n`（比較対象）/
`--no-strong-claim`（断言枠除去）/ `--logic-check`（論理一貫性の復元工程。既定は無効）/
`--rounds N` / `--min-improve` / `--quality-ceiling`（improve の反復回数・頭打ちしきい値・高品位停止しきい値。高品位は既定 0.75 で有効）/
`--output-format '<JSON>'`（出力形式の明示指定。省略時は実APIでタスクから LLM が動的に抽出）/
`--knowledge 'TEXT'` / `--knowledge-file PATH` / `--ask-knowledge`（前提知識。素材・制約・背景情報を生成の土台として全段階に注入。相互排他。保存先 `--out/knowledge.md`）

### 出力フォーマット認識（分野ごとの形式）

パイプライン開始前に、タスクから期待される出力形式を LLM が動的に抽出する
（`extract_format`。1回の軽量コール、温度0.0、同一タスクはキャッシュ）。
抽出した `OutputFormat` を全段階に注入する:

```
Task → extract_format(task) [1 lightweight LLM call] → OutputFormat
                                                          │
    ┌─────────────────────────────────────────────────────┼──────────────────────────┐
    ↓                                                     ↓                          ↓
diverge()                                           aufheben()                 finalize()
・fmt.draft_guidance をタスクに追記                  ・deliverable_type を       ・fmt.finalize_guidance
  （キャッチコピーなら「候補+意図」形式で）           意識させる指示を追記         で TVRO を置換
・出力が成果物そのもの（output_is_direct）なら           （弁証法自体は不変）      ・fmt.{min,max}_output_length
  草案上限を創作系上限に緩める                                                 で完全性判定
```

`OutputFormat`（[elevate/engine.py](elevate/engine.py)）:

| フィールド | 意味 |
|---|---|
| `deliverable_type` | 成果物の種別名（例: キャッチコピー / 事業計画書 / 歌詞 / 小説） |
| `description` | このタスクで良い成果物とは何か（1文） |
| `draft_guidance` | エージェント草案の形式指示（分析系ならテーゼ形式、短形式なら候補+根拠） |
| `finalize_guidance` | 最終化の形式指示（汎用 TVRO をタスク固有の構造で置換） |
| `min_output_length` / `max_output_length` | 最終成果物の長さ範囲（タスク固有。タグライン min=2 / 小説 max=8000 等） |
| `output_is_direct` | `true`=成果物そのもの（コピー・詩・歌詞） / `false`=成果物についての分析 |

- **抽出失敗時は既存挙動（分析レポート前提・固定値）にフォールバック**する——劣化ではなく安全側への退避。
  分析系タスクは LLM が TVRO 相当の `finalize_guidance` を返すため、既存と同一の挙動になる。
- `--output-format '<JSON>'` で抽出をスキップして明示指定できる（mock でも有効。テスト・再現に使う）。
- 抽出/指定された仕様は `--out/format.md` に保存される（透明性）。
- 完全性ガードはタスク固有の長さ範囲で判定し、**直接成果物（output_is_direct）は文末記号を要求しない**
  （タグラインや詩は「。」で終わらないのが普通。固定の文終端チェックを要求すると完成形を再生成ループに落とす）。
- **仕様の自己矛盾は安全弁で吸収**: LLM 抽出のフォーマットが自己矛盾（抽出した `finalize_guidance` が
  要求する構造 > 抽出した `max_output_length` 等）で実質達成不能なとき、上限回数の再生成後、
  構造的に完成した（文終端のある）最後の試行を受け入れて続行する（警告を stderr に出す）。
  健全な成果物を仕様不整合だけで捨ててパイプライン全体を落とさない。fmt なし（既存の固定値判定）は
  従来どおり明示的失敗する。
- フォーマット適合性はハードゲート（完全性ガード）であり、5軸ルーブリックのスコアには**しない**
  （5軸はポリシー固定。ゴールポストは動かさない）。

### 前提知識の注入（--knowledge）

タスクに付随する素材・制約・背景情報（材料、ターゲット層、価格帯、資料等）を
生成の土台として全段階に注入する。fmt（形の制約）と対になる**内容の制約**であり、直交する:

```
Task → 【前提知識】 → 【このタスクの草案形式 / 最終成果物形式】（fmt）
```

| CLI | 動作 |
|---|---|
| `--knowledge "材料: 再生PET。ターゲット: 20〜30代。"` | 知識を直接指定 |
| `--knowledge-file PATH` | 長文の資料・設計情報をファイルから読み込む |
| `--ask-knowledge` | 起動時に対話的に入力する（Ctrl+D で終了） |

- 指定した知識は **diverge（草案）/ aufheben（止揚）/ finalize（最終化）/ generate（単発）** の
  全生成段階にタスク直後として注入される。素材を超えた捏造を防ぎ、成果物が知識と矛盾しない。
- **extract_format には注入しない**——形式抽出（形）はタスクのみから行い、知識（内容）を混ぜない。
- **5軸評価には注入しない**——ポリシー固定。生成の土台の範囲外。
- **improve の改修ラウンドに永続する**——diverge が内部で知識を付与するため、ラウンドをまたいで落ちない。
- **compare は公平**——素の生成ベースラインにも同じ知識を注入して比較する。
- 指定した知識は `--out/knowledge.md` に保存される（input.md / format.md と並列・透明性）。
- 知識なし（従来挙動）は一切注入しない。3つの指定方法は相互排他。

### 昇華優位性の計測（compare）

`compare` は「昇華」と「単発生成（または昇華しない最良草案選択）」を同じ入力で走らせ、
スコアと勝率を実測して比較する装置である。優位性の断言はせず、数値に委ねる。

| オプション | 動作 |
|---|---|
| `--runs N` | 比較を N 回反復し、平均 overall・標準偏差・勝率（ELEVATE > ベースライン）を出力。既定 1 |
| `--baseline single` | ベースライン = 素の単発生成（`generate`）。既定 |
| `--baseline best-of-n` | ベースライン = **昇華しない最良草案選択**（帰無仮説）。同一の8草案から昇華せず最高スコアの草案を選ぶ場合と、昇華する場合を同一評価器で測る。`--evaluate` 必須 |
| `--no-strong-claim` | エージェントから旧「最強の主張」断言枠を除去（テーゼ集中形式では実質 no-op。後方互換のため維持） |

`--runs N`（N>1）を渡すと、各 run のスコアを集計して以下を出力する:

```bash
=== 比較集計 ===
素の生成（単発）: mean=0.778 sd=0.012（n=3）
ELEVATE:            mean=0.812 sd=0.009（n=3）
差（ELEVATE−ベースライン）: mean=0.034 sd=0.015（n=3）
勝率（ELEVATE > ベースライン）: 3/3 = 100.0%
  勝率 95%CI（Wilson）: 43.8%〜100.0%
  差の 95%CI（t, 両側）: -0.003〜+0.071
  効果量（Cohen's d）: +1.90
```

（上記は集計フォーマットの形式例であり、値は実測ではない。
95%CI は小標本では広く開く——n≥10 まで集めてから統計的優位性を論じること。）

同一タスク・同一モデルでこの計測を多数回実行し、結果を examples/ に公開することが、
本エンジンの存在理由を実証する経路である。勝率が 50% を下回るタスクが存在してもよい
（その開示こそが誠実な主張になる）。

**実証は統計だけでなく、成果物を読むことでもある。** `compare` は各 run に素AI生成（`raw.md`）と
昇華版（`elevated.md`）を両方保存する。それらを客観視するための比較ドキュメントを生成する:

```bash
python render_comparison.py examples/<sample_dir>        # comparison.md（両方を束ねる）
python render_comparison.py examples/<sample_dir> --html # + comparison.html（横並び表示）
```

**サンプルは「full」だけに偏らせない。** 分野をばらけさせ、エージェント数・ループ数を振る。
昇華優位性が特定のタスク・構成に依存しないことを、複数条件の実測で示すのが目的である。

### 反復改善（improve）— 昇華版を磨くループ

`improve` は、一度作った昇華版を**繰り返し磨き上げる**ためのループである:

```
昇華版 → 改修の草案(複数) → 昇華 → 新しい昇華版 → （繰り返し）
```

- round 1: オリジナルタスクから発散 → 昇華で**初回の昇華版**を作る。
- round 2 以降: 各エージェントが**前回の昇華版を改修した草案**を書き、それらを昇華して
  次の昇華版を作る。昇華版の成果がループを回すごとに相続され、積み上がっていく。
  （「昇華したらおしまい」ではなく、昇華版を土台にしてさらに磨く。）
- 各 round は `round_NN/` に分離保存（`draft_*` / `reconciliation` / `elevated`）され、
  履歴が追える。`progress.md` に全 round の長さと評価が記録される。

```bash
python main.py improve "タスク" --rounds 3                # 3回の昇華を繰り返す
python main.py improve "タスク" --rounds 5 --evaluate     # 各ラウンドを品質評価
```

| オプション | 動作 |
|---|---|
| `--rounds N` | 昇華を繰り返す回数（既定 3） |
| `--evaluate` | 各ラウンドの昇華版を品質評価し、overall を progress.md に記録 |
| `--min-improve` | 頭打ちしきい値。直前ラウンドからの overall 改善がこれ未満なら早期停止（既定 0.01）。`--evaluate` 時のみ |
| `--quality-ceiling` | 高品位停止しきい値。overall がこれ以上なら改修ラウンドを生成せず停止（既定 0.75）。`--evaluate` 時のみ・既定で有効 |

`--evaluate` の早期停止は、**過修正で元の良さを失わせない**ための安全弁である。
(1) **高品位停止**: 昇華版の overall が `--quality-ceiling`（既定 0.75）以上なら、
次の改修ラウンドを生成せず停止する。既に高品位な成果物ほど改修で壊れやすい。
(2) **頭打ち停止**: 直前ラウンドからの改善が `--min-improve`（既定 0.01）
未満なら停止。ゼロからやり直す `compare` とは対照的に、`improve` は相続によって
改善していく。停止理由は `progress.md` の「**停止理由**」に記録される。

mock での動作確認（品質評価は mock では無効のため、overall = 均等重み × 各軸。素の生成相当は 0.600 から始まる。Pass しきい値 0.60）:

```
[round 1 昇華版] overall=0.600（Pass）     ← 素の生成相当。天井でなく改善の余地がある
[round 2 昇華版] overall=0.720（Pass）   +0.120
[round 3 昇華版] overall=0.720（Pass）   +0.000 → 頭打ちと判断し停止（過修正を避ける）
```

### 生成エンジン（--engine）

| エンジン | 起動方式 | 用途 |
|---|---|---|
| `sdk`（既定） | `anthropic` SDK で1プロセス内から直呼び | 通常の Anthropic API |
| `claude-code` | 呼び出しごとに `claude -p` を独立起動 | Claude Code 互換ゲートウェイ・不安定な SDK 経路の回避 |

`claude-code` エンジンは草案・昇華推理・最終化を**それぞれ独立プロセス**で生成する
（中間コンテキストの混線なし・打ち切り時の再試行もプロセス単位）。温度はシステムプロンプト
内の指示文で近似する（`温度≥0.5` → 発散重視 / `温度<0.5` → 一貫性重視）。
SDK 経由の空応答は `CLAUDE_MAX_RETRIES`（既定6）で再試行する。

## インストールとファサード skill

`./install.sh` で Claude Code から呼べるようにする（agents + skill を symlink 設置）。

```bash
./install.sh            # グローバル: ~/.claude/agents/ + ~/.claude/skills/
./install.sh --local    # プロジェクト: .claude/agents/ + .claude/skills/
./install.sh --uninstall
```

インストールされるもの:
- **8クリエイターエージェント**（`strategist` 等）— Agent tool / @-mention で起動可能
- **`elevate-draft-engine` skill（ファサード）** — `main.py` への薄い呼び出しインターフェース

**ファサード skill の設計**: elevate の skill は**オーケストレーターではなくファサード**である。
オーケストレーション（DIVERGE → 昇華推理 → 最終化、完全性ガード、温度制御、`claude -p` 安定経路）
はすべて Python エンジン側にあり、skill は `main.py` を起動して結果を報告するだけ。エンジンを
バイパスしてサブエージェントを直接昇華するのはダウングレードなので行わない。

```bash
# 呼び出し例（Claude Code 内で Skill: elevate-draft-engine を使用）
# Args: {"task": "健康AIの企画", "agents": ["strategist", "humanist", "differentiator"]}
```

## Python API

```python
from elevate import DraftEngine, Draft
from adapters.claude_client import ClaudeClient

engine = DraftEngine(ClaudeClient(), draft_temperature=0.9)

# 素のAI（単発生成）— 1 call
raw = engine.generate("健康AIの企画")

# エージェント管理
engine.list_agents()                 # 8種のデフォルトエージェント（agents/*.md から読込）
engine.add_agent("legal", "あなたは法規制の専門家です。")
engine.remove_agent("storyteller")

# Step 1: DIVERGE — 独立草案を生成（既定は全エージェント）
drafts = engine.diverge("健康AIの企画")
# draft_dir を渡すと各草案を空ファイルから生成中に逐次追記（CLI は既定で outputs/{タスク名}/ を渡す）
drafts = engine.diverge("健康AIの企画", draft_dir=Path("examples/health-ai"))

# Step 2: SYNTHESIZE — 複数の異なる草案を昇華（核心）
elevated = engine.synthesize(drafts)     # 内部: aufheben → finalize
elevated = engine.synthesize(drafts, method="single-pass")   # 単発昇華

# 外部草案もそのまま昇華できる
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
│   └── claude_code_client.py   # claude -p 独立起動（--engine claude-code）
├── evaluation/
│   ├── evaluator.py            # 品質評価（5軸 + 掛け算統合。--evaluate 用）
│   └── quality.py              # 品質評価の3観点（新奇度・独自性・意外性）
├── skills/
│   └── elevate-draft-engine/SKILL.md   # ファサード skill（main.py を起動。オーケストレーションは委譲）
├── tests/                      # 184件
├── examples/                   # 実行サンプル集（分野横断テストケース等）
│   └── multi-domain/           # 分野横断フォーマット認識+知識注入の検証ケース
├── CLAUDE.md                   # プロジェクト指示（AI向け）
├── HISTORY.md                  # 開発履歴（ルーブリック再調整・旧実測等）
├── install.sh                  # agents + skill を Claude Code 検出先へ symlink 設置
├── main.py                     # 薄い CLI（generate / diverge / synthesize / elevate / compare / improve / calibrate）
├── render_comparison.py        # compare 出力から「素AI生成 vs 昇華版」比較ドキュメントを生成
├── requirements.txt
└── README.md
```

設計の要点（詳細はコードのコメント参照）:
- **完全性ガード（broken output → regenerate）**: 打ち切り/不完全は再生成（最大3回）、直らなければ明示的失敗
- **成果物のファイル逐次保存（既定）**: `--out` を省略すると `outputs/{タスク名}/` に全成果物（input / draft_{agent} / reconciliation / raw / elevated / evaluation_* / measurement）を自動保存する。draft は生成前に空の `draft_{agent}.md` として作られ、生成中に逐次追記される。全8草案の完了を待たずにファイルが育つため、途中で失敗しても生成済み分は消えない。打ち切りで再生成するときはファイルを空に戻してから再開する。claude-code エンジンは `claude -p --output-format stream-json` の累積テキスト差分を `on_chunk` で流す（SDK エンジンは全文が揃った時点で一括書き込み）
- **昇華推理の完全性は長さ基準**（最小30字）: 昇華推理は「思考の土台」で文終端記号で終わらないため
- **最終化は止揚推理だけを読み**、中間思考（草案同士の比較・弁証法の手続き説明）が成果物に漏れない

## 制約と失敗モード

- **昇華優位性は実測で検証する**: 「昇華が単発生成を上回る」は設計目標。現時点の実測（multi-domain 6分野、
  素の生成はフォーマットなし・知識あり）では**昇華が過半のタスクで上回る**（6ケースで5勝、平均差 +0.21）
  が、**素の生成が勝つタスクもありタスク依存**（lyrics のみ素の生成が勝利）。`compare --runs N` で n を積んで検証し、
  勝率 50% を下回る結果も正常な知見として開示する。
- **コスト**: DIVERGE（8草案）+ aufheben + finalize は単発生成の約10回分の API 呼び出しになる。
  優位性の検証はそのコストに見合うタスクに限るのが実用的である。
- **温度近似**: `claude-code` エンジンでは温度をシステムプロンプトの指示文で近似する
  （SDK 直呼びの空応答回避のため）。数値としての温度再現性はない。
- **評価の系統**: `--evaluate` の評価は生成と独立した評価エンジン（evaluation/）で行うが、
  評価モデルが生成モデルと同系である限り、完全な独立評価ではない。結果は傾向として読む。
- **アブレーションの範囲**: `--no-strong-claim` は枠の有無だけを変える。枠の貢献度が正にも負にも
  出る可能性があり、どちらの結果もそのまま報告する。
