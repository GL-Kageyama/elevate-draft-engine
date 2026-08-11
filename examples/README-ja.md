**言語:** [English](README.md) | [日本語](README-ja.md) | [中文](README-zh.md)

# Examples — サンプル蓄積

タスクごとに **発散（各エージェント草案）→ 昇華（アウフヘーベン）（成果物）** の実行例を保存する。

## 使い方

**実行して保存:**
```bash
# 実API（ゲートウェイ）でエージェント指定・実行例を保存
.venv/bin/python main.py elevate "タスク" \
  --agents strategist humanist differentiator --out examples/<task-dir>

# モックで一気通貫確認（API不要）
.venv/bin/python main.py compare "タスク" --mock --evaluate
```

## 各タスクのファイル

```
examples/<task-dir>/
├── input.md                          # 元のタスク
├── format.md                         # 抽出された出力形式（OutputFormat）
├── knowledge.md                      # 前提知識（--knowledge 指定時のみ）
├── parameters.md                     # 実行時パラメータ（発想レベル・エンジン・エージェント等）
├── drafts/                           # 各エージェントの独立草案（テーゼ集中形式）
│   ├── draft_strategist.md
│   ├── draft_humanist.md
│   └── ...
└── artifacts/                        # 昇華と最終成果物
    ├── reconciliation.md             # 止揚の下地（昇華推理）
    └── elevated.md                   # 昇華成果物
```

全ファイル Markdown（`.md`）で保存する。

実APIはゲートウェイが間欠的に空応答を返すため、再試行上限6回
（`CLAUDE_MAX_RETRIES`）で自己回復させる。

## 多言語サンプル（i18n）

`i18n/` 以下に、同一タスク（朝のルーティーン設計）を 3言語（en / ja / zh）で
**実生成**したサンプルを保存する。モックではない——実APIでタスクへの
**実際の答え**を生成している。各言語ディレクトリは独立した complete な
サンプル（`input.md` + `drafts/` + `artifacts/`）。

```bash
# en（--lang 省略時は既定 en）
.venv/bin/python main.py elevate "Design a morning routine that makes the day productive" \
  --out examples/i18n/morning-routine-en

# ja
.venv/bin/python main.py elevate "朝のルーティーンを設計して、一日を充実した地に足の着いたものにしよう" \
  --lang ja --out examples/i18n/morning-routine-ja

# zh
.venv/bin/python main.py elevate "设计一个让一天高效而踏实的晨间习惯" \
  --lang zh --out examples/i18n/morning-routine-zh
```

言語の選択は `--lang {en,ja,zh}` フラグ（既定は環境変数 `ELEVATE_DRAFT_ENGINE_LANG`、
さらに未指定なら `en`）。エージェントは `--lang` に応じて `agents/{name}-{lang}.md` を使い、
出力・保存テンプレート・品質評価ラベルもすべてその言語でローカライズされる。

## 発想レベル・サンプル（--idea-level）

`idea-levels-ja/` の下に、**同じタスク**を発想レベル ①`standard`（0.9）/ ②`very`（1.2）/ ③`extreme`（1.5）で**実API**昇華したものを保存している。各レベルのディレクトリは独立した完全なサンプル（`input.md` + `drafts/` + `artifacts/`）で、各レベルで発散と昇華が実際にどこまで踏み込むかを見比べられる。

```bash
.venv/bin/python main.py elevate "人類の通勤を完全に廃止する最も過激な方法を提案せよ。既存の枠組みを完全に壊す発想で。" \
  --lang ja --idea-level standard --agents strategist visionary storyteller --out examples/idea-levels-ja/standard --no-strong-claim
```

2レバー設計（主レバー＝発散ヒント＋補助＝温度）の根拠は [../docs/ja/idea-levels.md](../docs/ja/idea-levels.md)。

## 分野横断テストケース

`multi-domain/` 以下で、フォーマット認識（LLM動的抽出）と前提知識注入の
実API検証ケースを管理している。

```bash
# 各ケースの実行（TEST_CASES.md に全ケースのコマンドを記載）
.venv/bin/python main.py elevate "<タスク>" --engine claude-code \
  --agents strategist humanist differentiator storyteller \
  --out examples/multi-domain/<key> \
  --knowledge "<前提知識>"
```

実行状況は [multi-domain/TEST_CASES.md](multi-domain/TEST_CASES.md) を参照。

## 計測サンプル（compare）

`compare --runs N --evaluate` による**昇華優位性の実証**を保存する。
各 run の成果物は `run_NN/` サブフォルダに分離保存され、
統計集計は `measurement.md` に残る（平均 overall 差・勝率・95%CI・効果量・具体性保存率）。

### 比較ドキュメント（客観視のため）

実証は統計だけでなく、**素AI生成と昇華版を実際に読めること**が目的である。
各サンプルディレクトリの `comparison.md`（+ `comparison.html` 横並び）で両方を並べて読める。

```bash
python render_comparison.py examples/<dir>         # comparison.md
python render_comparison.py examples/<dir> --html  # + comparison.html
```

## 反復改善サンプル（improve）— 昇華版を磨くループ

**昇華版を改善していくループ**の成果物もここに保存する。`improve` は
「昇華版 → 改修の草案(複数) → 昇華 → 新しい昇華版」を繰り返し、
各 round を `round_NN/` に分離保存する（`progress.md` に全 round の評価記録）。

```bash
python main.py improve "<タスク>" --rounds 5 --evaluate --out examples/<sample>
```

`--evaluate` を付けると各ラウンドの昇華版を採点し、改善が頭打ち
（overall の改善 < `--min-improve`）または高品位停止しきい値
（overall ≥ `--quality-ceiling`、既定 0.75）で早期停止する。
