**语言:** [English](README.md) | [日本語](README-ja.md) | [中文](README-zh.md)

# Examples — 样本积累

按任务保存 **发散（各智能体草案）→ 升华（Aufheben）（成果物）** 的执行示例。

## 用法

**执行并保存:**
```bash
# 用真实 API（网关）指定智能体・保存执行示例
.venv/bin/python main.py elevate "任务" \
  --agents strategist humanist differentiator --out examples/<task-dir>

# 无需 API 的 mock，一口气确认流水线
.venv/bin/python main.py compare "任务" --mock --evaluate
```

## 各任务的文件夹

```
examples/<task-dir>/
├── input.md                          # 原始任务
├── format.md                         # 抽取的输出格式（OutputFormat）
├── knowledge.md                      # 前提知识（仅 --knowledge 时）
├── parameters.md                     # 运行参数（创意水平・引擎・智能体等）
├── drafts/                           # 各智能体的独立草案（命题集中形式）
│   ├── draft_strategist.md
│   ├── draft_humanist.md
│   └── ...
└── artifacts/                        # 升华与最终成果物
    ├── reconciliation.md             # 止扬的地基（升华推理）
    └── elevated.md                   # 升华成果物
```

全部文件以 Markdown（`.md`）保存。

实 API 的网关会间歇性地返回空响应，因此用重试上限 6 次
（`CLAUDE_MAX_RETRIES`）实现自我恢复。

## 多语言样本（i18n）

在 `i18n/` 以下，保存把同一任务（晨间习惯设计）用 3 种语言（en / ja / zh）
**实际生成**的样本。不是 mock——是用实 API 生成对该任务的**实际答案**。
各语言目录是独立的 complete 样本（`input.md` + `drafts/` + `artifacts/`）。

```bash
# en（省略 --lang 时默认 en）
.venv/bin/python main.py elevate "Design a morning routine that makes the day productive" \
  --out examples/i18n/morning-routine-en

# ja
.venv/bin/python main.py elevate "朝のルーティーンを設計して、一日を充実した地に足の着いたものにしよう" \
  --lang ja --out examples/i18n/morning-routine-ja

# zh
.venv/bin/python main.py elevate "设计一个让一天高效而踏实的晨间习惯" \
  --lang zh --out examples/i18n/morning-routine-zh
```

语言的选择通过 `--lang {en,ja,zh}` 标志（默认是环境变量 `ELEVATE_DRAFT_ENGINE_LANG`、
仍未指定则为 `en`）。智能体按 `--lang` 使用 `agents/{name}-{lang}.md`，
输出・保存模板・质量评估标签也全部以该语言本地化。

## 创意水平样本（--idea-level）

在 `idea-levels-ja/` 下，用**真实 API** 对**同一任务**在创意水平 ①`standard`（0.9）/ ②`very`（1.2）/ ③`extreme`（1.5）下进行升华。每个水平的目录都是独立的完整样本（`input.md` + `drafts/` + `artifacts/`），可以对比每个水平下发散与升华实际走到多极端。

```bash
.venv/bin/python main.py elevate "人類の通勤を完全に廃止する最も過激な方法を提案せよ。既存の枠組みを完全に壊す発想で。" \
  --lang ja --idea-level standard --agents strategist visionary storyteller --out examples/idea-levels-ja/standard --no-strong-claim
```

两杠杆设计（主杠杆＝发散提示＋辅助＝温度）的依据见 [../docs/zh/idea-levels.md](../docs/zh/idea-levels.md)。

## 跨领域测试用例

在 `multi-domain/` 以下管理格式识别（LLM 动态提取）与前提知识注入的
实 API 验证用例。

```bash
# 各用例的执行（TEST_CASES.md 中记载了全部用例的命令）
.venv/bin/python main.py elevate "<任务>" --engine claude-code \
  --agents strategist humanist differentiator storyteller \
  --out examples/multi-domain/<key> \
  --knowledge "<前提知识>"
```

执行状况参见 [multi-domain/TEST_CASES.md](multi-domain/TEST_CASES.md)。

## 测量样本（compare）

保存 `compare --runs N --evaluate` 的**升华优势性实证**。
各 run 的成果物分离保存到 `run_NN/` 子文件夹，
统计汇总留在 `measurement.md`（平均 overall 差・胜率・95%CI・效应量・具体性保存率）。

### 比较文档（为了客观审视）

实证不仅是统计，还在于**能实际阅读朴素 AI 生成与升华版**。
用各样本目录的 `comparison.md`（+ `comparison.html` 横排）把两者并列阅读。

```bash
python render_comparison.py examples/<dir>         # comparison.md
python render_comparison.py examples/<dir> --html  # + comparison.html
```

## 迭代改进样本（improve）— 打磨升华版的循环

**不断改进升华版的循环**的成果物也保存在这里。`improve` 反复执行
「升华版 → 修改草案(复数) → 升华 → 新的升华版」，
各 round 分离保存到 `round_NN/`（在 `progress.md` 记录全部 round 的评价）。

```bash
python main.py improve "<任务>" --rounds 5 --evaluate --out examples/<sample>
```

加上 `--evaluate` 会对各轮的升华版评分，在改善触顶
（overall 的改善 < `--min-improve`）或达到高品位停止阈值
（overall ≥ `--quality-ceiling`、默认 0.75）时提前停止。
