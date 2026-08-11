**语言:** [English](README.md) | [日本語](README-ja.md) | [中文](README-zh.md)

# elevate-draft-engine

<p align="center">
  <img src="assets/repo-hero.png" width="100%" alt="elevate-draft-engine">
</p>

**让多个 AI 各自从不同视角写出的答案相互碰撞，生成任何单一视角都不具备的、更高一层的答案的引擎。**

为了超越 AI 一次给出的「平均化的好答案」，采用 **DIVERGE（发散）→ SYNTHESIZE（升华）** 的两段式结构。

```
            任务
              │
              ├─→ [Draft: strategist]     价值
              ├─→ [Draft: differentiator] 独创性
              ├─→ [Draft: humanist]       共感
              ├─→ [Draft: futurist]       将来性
              ├─→ [Draft: designer]       体验设计
              ├─→ [Draft: visionary]      世界观
              ├─→ [Draft: implementer]    实现性
              └─→ [Draft: storyteller]    故事
                      │
                      ↓
             [升华推理 Aufheben]        ← 在否定各草案片面性的同时，保存真理的契机，
                      │                   创出包摄矛盾的一段更高的框架（思考的根基。不是给读者看的）
                      ↓
             [最终化 Finalize]           ← 只读取升华推理，把超越性整合解打磨成超越单次生成的清晰成果物
                      │
                      ↓
                最终成果物
```

- **DIVERGE**: 8 种创作者智能体各自生成**极限发散**的独立草案。通过角色多样性（system）＋温度多样性保证独立性。通过**创意水平**（`--idea-level`）选择发散要走到多极端：standard（0.9・默认）/ very（1.2）/ extreme（1.5）。每个水平配对一个递进式发散提示。妥协与中间解不会成为素材——而是为了在之后的升华中被提升到更高维度而刻意锐化的个别解。
- **SYNTHESIZE**（核心）: 阅读全部草案，以**否定·保存·高次化**的三契机进行扬弃的升华推理（与创意水平相同的温度）→ 只阅读扬弃推理的最终化（temp 0.0）。构成单一观点草案所不具备的超越性整合解。
  - 例如 strategist 的「收益」与 humanist 的「共感」的冲突，不是逻辑上的妥协（条件性接受），而是被扬弃为**让两者的真理同时成立的新框架**。
  - 「升华优于单次生成」是**设计目标**。通过 `compare` 的实测来验证（参见 [升华优势性的测量](#升华优势性的测量compare)）。
  - `synthesize()` 也接受**外部草案**。人类专家写的分析、其他模型的输出、过去的成果物等，无论出处如何，只要投入「多个不同视角」，就能返回超越性整合解。

## 五维评估（紧扣政策）

`--evaluate` 的评分，把**这个引擎所相信的「好的成果物」**（政策: 升华多个独立视角，产出超越单一视角的成果物）分解为五个维度，各以 0.0〜1.0 测量。

前三个维度测量「发散 → 升华 → 超越」这一引擎动作的质量，其余两个维度测量成果物完成度的质量。

| 维度 | 概要 | 高得分（0.7〜0.8） | 低得分（0.0〜0.4） |
|---|---|---|---|
| **多样性** | 是否从各种立场・领域观察事物 | 横跨多个视角・价值观，广泛覆盖领域 | 封闭在单一看法中 |
| **整合性** | 差异不是「并列」而是「咬合」了吗 | 解决视角间的矛盾，成为相互联结的结构 | 碎片的拼凑・并列（平均化也不合格） |
| **超越性** | 是否产生了任何单一视角都没有的新看法 | 明确存在只有经过整合才能得到的新视角 | 某份草案的翻炒 |
| **诚实性** | 是否区分确定与不确定 | 对不确定之处作为条件・前提明确说明 | 断定没有依据之事 |
| **实用性** | 实际上如何推进、谁如何使用，是否看得见路径 | 能具体描绘执行的路径与使用者 | 抽象，执行可能性无法确认 |

评分的规则:

- **权重均等（各 0.20）**: `5维overall = 多样性×0.20 + 整合性×0.20 + 超越性×0.20 + 诚实性×0.20 + 实用性×0.20`
- **所有维度「越高越好」**: 全部五个维度得分越高表示成果物越好（没有反转逻辑）。
- **评分锚点**: 0.5 = 稳妥（平庸） / 0.7〜0.8 = 确实好 / 0.9 以上 = 平庸生成无法产出的「固有框架・视角转换」。不给平庸输出打 0.7 以上。
- **盲评**: 评价由与生成独立的专用评价模型，在不被告知成果物出处・生成方法的情况下进行。

## 质量评估（整合进 overall）

`--evaluate` 的 overall，把**质量评估（套路程度・独创性）**以乘法整合进五维评估。
由于五维评估不测量「套路程度・独创性」，朴素 AI 生成（仅给指示）在套路化任务中即使给出稳妥的回答，
五维 overall 也会居高不下，独创性的差异得不到反映。质量评估填补这一盲区。

| 观点 | 概要 | 越高 |
|---|---|---|
| **新奇度** | 在多大程度上偏离该任务的「典型回答」 | 新颖，不落于常见套路 |
| **独创性** | 是否有常见套路之外的固有观点・概念框架・造词・哲学 | 有固有框架 |
| **意外性** | 是否有打破读者预期的要素 | 打破预期 |

overall 的公式（α = 0.25。`0.75` 是 `1−α`）:

    overall = 5维overall × (α + (1−α) × 质量分)
    质量分 = (新奇度 + 独创性 + 意外性) / 3

- **套路化回答会被大幅减分**: 质量得分 0.2（套路）时系数 0.40，0.8（独创）时系数 0.85。
- **Pass 阈值为 0.60**: 由于质量评估的乘法使 overall 的绝对值下降，因此从仅有五维时代的 0.70 重新调整。
- 可用 **`--no-quality`** 回到无质量评估（仅五维的 overall）。

## 智能体（agents/）

以**1 智能体=1 文件**的方式放置在 `agents/{name}.md`。正本是文件。
引擎启动时读取 `agents/*.md`，
把 frontmatter 的 `name` 用作智能体名，正文（persona）用作系统提示词。

```markdown
---
name: strategist
description: Value. Maximum market value, success conditions, competitive advantage, and who pays.
---

You are the **Strategist**, a voice of value and markets.
…
```

**添加智能体**: 添加 `agents/{name}.md`（重启时被读取），
或在运行时用 `add_agent(name, system_prompt)` 添加。删除用 `remove_agent(name)`。

**草案的命题集中形式**: 各智能体的草案不是完整的分析报告，而是交给之后升华的
**一条锐化后的论题**（已内置进智能体文件的「草案的写法」）。
只用**核心主张**（3 句以内）・**依据**（最多 3 条・各 1 句）・**前提**（1 句・可省略）
这 3 个要素，收在 500〜800 字以内。草案一旦变成分析报告，升华就会想拾取一切而过度包摄，
捏造无法验证的数字，导致 utility 下降。聚焦论题使对立结构更鲜明，同时改善速度与升华质量。
超过 `DRAFT_MAX_LENGTH`（1000 字）的草案按不完全处理重新生成。「容易被反驳之处」
**不要写**——让草案预先设想弱点会抑制自由的发散，因此反驳的检测由升华阶段的
Aufheber 承担。

默认 8 个智能体统一为创作者视角，智能体之间的**生产性冲突**是升华解的源泉。
怀疑・批判由升华阶段的 Aufheber 承担（检测草案之间的矛盾并扬弃）。

智能体可通过 `./install.sh` 作为 Claude Code 的子智能体（Agent tool / @-mention）
调用。但**引擎不使用子智能体**——
直接从仓库内读取 `agents/*.md`。编排始终在 Python 引擎一侧。

| # | 文件 | 观点 |
|---|---------|------|
| 1 | `designer` | 体验设计 |
| 2 | `differentiator` | 独创性 |
| 3 | `futurist` | 将来性 |
| 4 | `humanist` | 共感 |
| 5 | `implementer` | 实现性 |
| 6 | `storyteller` | 故事 |
| 7 | `strategist` | 价值 |
| 8 | `visionary` | 世界观 |

## 多语言支持（--lang）

引擎支持 en / ja / zh 三种语言（默认为 **en**）。
语言通过 `--lang {en,ja,zh}` 标志指定，按环境变量 `ELEVATE_DRAFT_ENGINE_LANG`、
仍未指定则默认为 `en` 的顺序解析。

| 领域 | 语言的处理 |
|---|---|
| 智能体 | `agents/{name}.md`（en）・`agents/{name}-ja.md`（ja）・`agents/{name}-zh.md`（zh）。像 `--agents strategist` 这样**用基名指定就不依赖语言** |
| LLM 提示词 | `prompts/{lang}.json`（engine 常量・质量 rubric・mock 文本） |
| CLI / 保存模板 | `locales/{lang}.json` |
| 质量评估 JSON | 键始终为英语（`novelty`/`originality`/`surprise`/`rationale`）。仅标签显示按语言区分 |

在 `agents/` 直接下放置无后缀的文件按 **en 处理**
（想把自定义智能体写成日语时放置 `agents/{name}-ja.md`，中文则放置 `-zh.md`）。

## 快速开始

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests/ -q     # 259 个测试

# 无需 API 的 mock，一口气确认流水线
.venv/bin/python main.py compare "健康AI产品策划" --mock --evaluate

# 用真实 API（独立启动 claude -p）取得样本并保存
.venv/bin/python main.py elevate "健康AI产品策划" \
  --engine claude-code --agents strategist humanist differentiator --out examples/health-ai
```

认证通过环境变量提供（不要把 API key 写进代码）。

| 环境变量 | 用途 |
|---|---|
| `ANTHROPIC_API_KEY` | 通常的 Anthropic API |
| `ANTHROPIC_AUTH_TOKEN` + `ANTHROPIC_BASE_URL` | Claude Code 兼容网关 |
| `CLAUDE_MIN_INTERVAL_SECONDS` | 请求最小间隔（默认 2.0 秒。空响应对策） |
| `CLAUDE_MAX_RETRIES` | 空响应/出错时的重试上限（默认 6 次。间歇性空响应对策） |

## CLI

```bash
python main.py generate "任务"                    # 朴素 AI（单次生成），1 次调用
python main.py diverge "任务"                     # 用 8 个智能体生成草案・输出一览
python main.py synthesize draft1.md draft2.md   # 升华外部草案（核心）
python main.py elevate "任务"                     # diverge → synthesize 一气呵成
python main.py compare "任务"                     # 同时输出 generate 和 elevate
python main.py compare "任务" --evaluate          # + 质量评估（5 维 + 新奇度・独创性・意外性）分数比较
python main.py compare "任务" --evaluate --runs 10        # 重复 N 次做统计汇总
python main.py compare "任务" --evaluate --baseline best-of-n  # 虚无假设比较
python main.py compare "任务" --evaluate --no-strong-claim      # 断言框架消融
python main.py compare "任务" --evaluate --logic-check          # 最终化之后恢复逻辑一致性的工序
python main.py calibrate "任务" --mock --runs 3                 # 温度近似的误差定量
python main.py improve "任务" --rounds 3                        # 升华版→修改草案→升华 的循环式反复改进
python main.py improve "任务" --rounds 3 --evaluate             # + 给各轮打分・触顶时早期停止
```

通用选项: `--lang {en,ja,zh}`（语言指定。默认 en）/
`--mock`（不需要 API）/ `--engine sdk|claude-code`（默认 sdk）/
`--method two-stage|single-pass`（默认 two-stage）/
`--idea-level {standard,very,extreme}`（发散・升华的极端程度。默认 standard）/
`--agents strategist humanist`（限定智能体）/ `--out DIR`（成果物的保存位置。省略时
自动保存到 `outputs/{任务名}/`。diverge / elevate / compare / improve 全部以所有成果物为对象）/
`--runs N`（compare 重复 N 次）/ `--baseline single|best-of-n`（比较对象）/
`--no-strong-claim`（去除断言框架）/ `--logic-check`（逻辑一致性恢复工序。默认无效）/
`--rounds N` / `--min-improve` / `--quality-ceiling`（improve 的迭代次数・触顶阈值・高品位停止阈值。高品位默认 0.75 有效）/
`--output-format '<JSON>'`（显式指定输出格式。省略时在实 API 下由 LLM 从任务动态提取）/
`--knowledge 'TEXT'` / `--knowledge-file PATH` / `--ask-knowledge`（前提知识。把素材・约束・背景信息作为生成的根基注入所有阶段。相互排斥。保存位置 `--out/knowledge.md`。运行参数保存到 `--out/parameters.md`）

### 输出格式识别（按领域的形式）

在流水线开始前，由 LLM 从任务动态提取期望的输出格式并注入所有阶段
（标语类用候补形式、分析类用论题形式、直接成果物用长度范围做完整性判定）。
提取失败时的回退・安全阀・`OutputFormat` 表见 [docs/output-format.md](docs/zh/output-format.md)。

### 前提知识的注入（--knowledge）

把素材・约束・背景信息作为生成的根基注入所有阶段（与 fmt=形式的约束相对的内容约束）。
指定方法・注入范围・保存位置的详细见 [docs/knowledge.md](docs/zh/knowledge.md)。

### 创意水平（--idea-level）

用 `--idea-level {standard,very,extreme}` 选择 发散（diverge）与 升华推理（Aufheben）要走到多极端。通过两个杠杆适用：递进式**发散提示**（主杠杆。reasoning 模型对温度超过 1 的反映并不可靠）+ **温度**（辅助）。最终化无论水平如何都始终使用温度 0.0。

| 水平 | 温度 | 含义 |
|---|---|---|
| `standard`（默认） | 0.9 | 一般地极端 — 既有的行为（向后兼容） |
| `very` | 1.2 | 非常极端 |
| `extreme` | 1.5 | 极度极端 |

`sdk` 引擎把温度与提示两者都传给 API。`claude-code` 引擎（没有温度旋钮）仅通过提示来近似水平。两杠杆设计的依据与温度超过 1 的网关发现见 [docs/idea-levels.md](docs/zh/idea-levels.md)。

### 升华优势性的测量（compare）

让「升华」与「单次生成（或不升华的最优草案选择）」在同一输入・同一评价器下运行，
实测得分与胜率。`--runs N` 输出统计汇总（胜率・95%CI・效应量），各 run 的
raw / elevated 可用 `render_comparison.py` 做成比较文档。
详细见 [docs/measurement.md](docs/zh/measurement.md)。

### 迭代改进（improve）

以升华版为根基，反复打磨「修改草案 → 升华」的循环。各 round 保存到 `round_NN/`，
`--evaluate` 时高品位停止・触顶停止的安全阀会生效。详细见 [docs/measurement.md](docs/zh/measurement.md)。

### 生成引擎（--engine）

| 引擎 | 启动方式 | 用途 |
|---|---|---|
| `sdk`（默认） | 用 `anthropic` SDK 在 1 个进程内直接调用 | 通常的 Anthropic API |
| `claude-code` | 每次调用独立启动 `claude -p` | 规避 Claude Code 兼容网关・不稳定的 SDK 路径 |

`claude-code` 引擎以**各自独立进程**生成草案・升华推理・最终化
（中间上下文不混杂・截断时的重试也以进程为单位）。温度通过系统提示词内的指示文近似
（`温度≥0.5` → 重视发散 / `温度<0.5` → 重视连贯性）。
经 SDK 的空响应用 `CLAUDE_MAX_RETRIES`（默认 6）重试。

## 安装与门面（facade）skill

用 `./install.sh` 让它能从 Claude Code 调用（symlink 放置 agents + skill）。

```bash
./install.sh            # 全局: ~/.claude/agents/ + ~/.claude/skills/
./install.sh --local    # 项目: .claude/agents/ + .claude/skills/
./install.sh --uninstall
```

安装的内容:
- **8 个创作者智能体**（`strategist` 等）— 可通过 Agent tool / @-mention 启动
- **`elevate-draft-engine` skill（门面）** — 对 `main.py` 的薄封装调用接口

**门面 skill 的设计**: elevate 的 skill 是**门面而非编排器**。
编排（DIVERGE → 升华推理 → 最终化、完整性保护、温度控制、`claude -p` 稳定路径）
全部在 Python 引擎一侧，skill 只是启动 `main.py` 并报告结果。绕过引擎直接升华
子智能体是一种降级，所以不做。

```bash
# 调用示例（在 Claude Code 中使用 Skill: elevate-draft-engine）
# Args: {"task": "健康AI产品策划", "agents": ["strategist", "humanist", "differentiator"]}
```

## Python API

用 `elevate.DraftEngine` 可直接调用 generate / diverge / synthesize / elevate
（外部草案也能原样升华）。使用例见 [docs/api.md](docs/zh/api.md)。

## 仓库结构

```
elevate-draft-engine/
├── agents/                     # 智能体正本（1 智能体 = 1 文件、frontmatter + 人设）
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
│   └── engine.py               # DraftEngine（读取 agents/ + synthesize）
├── adapters/
│   ├── claude_client.py        # Claude API 客户端（含节流・空响应重试）
│   └── claude_code_client.py   # 独立启动 claude -p（--engine claude-code）
├── evaluation/
│   ├── evaluator.py            # 五维评估（+ 乘法整合。供 --evaluate 用）
│   └── quality.py              # 质量评估的 3 个观点（新奇度・独创性・意外性）
├── skills/
│   └── elevate-draft-engine/SKILL.md   # 门面 skill（启动 main.py。编排委托给引擎）
├── tests/                      # 259 个测试
├── examples/                   # 执行样本集（跨领域测试用例等）
│   └── multi-domain/           # 跨领域格式识别+知识注入的验证用例
├── docs/                       # 深掘详解（output-format / knowledge / measurement / api）
├── CLAUDE.md                   # 项目指示（面向 AI）
├── HISTORY.md                  # 开发历史（rubric 再调整・旧实测等）
├── install.sh                  # 把 agents + skill 以 symlink 安装到 Claude Code 检测路径
├── main.py                     # 薄 CLI（generate / diverge / synthesize / elevate / compare / improve / calibrate）
├── render_comparison.py        # 从 compare 输出生成「朴素 AI 生成 vs 升华版」比较文档
├── requirements.txt
└── README.md
```

设计的要点（详细见代码注释）:
- **完整性保护（broken output → regenerate）**: 截断/不完全时重新生成（最多 3 次），仍不修复则显式失败
- **成果物的文件逐次保存（默认）**: 省略 `--out` 时自动把所有成果物（input / draft_{agent} / reconciliation / raw / elevated / evaluation_* / measurement）保存到 `outputs/{任务名}/`。draft 在生成前作为空的 `draft_{agent}.md` 创建，生成过程中逐次追加。由于文件在全部 8 份草案完成之前就会成长，中途失败也不会丢失已生成的部分。截断后重新生成时先把文件清空再继续。claude-code 引擎把 `claude -p --output-format stream-json` 的累积文本差分通过 `on_chunk` 流出（SDK 引擎在全文齐备时一次性写入）
- **升华推理的完整性以长度为基准**（最小 30 字）: 升华推理是「思考的根基」，不以句末符号结尾
- **最终化只读取扬弃推理**，中间思考（草案之间的比较・辩证法流程说明）不会漏进成果物

## 约束与失败模式

- **升华优势性以实测验证**: 「升华优于单次生成」是设计目标。实测记录统一管理在 [HISTORY.md](./HISTORY.md) 的实测记录部分。用 `compare --runs N` 累积 n 来验证，胜率低于 50% 的结果也作为正常的发现公开。
- **成本**: DIVERGE（8 草案）+ aufheben + finalize 相当于单次生成约 10 次的 API 调用。
  把优势性的验证限定在与该成本相称的任务上，才是实用的。
- **温度近似**: `claude-code` 引擎用系统提示词的指示文近似温度
  （为了回避 SDK 直呼的空响应）。没有数值上的温度重现性。
- **评价的同源**: `--evaluate` 的评价由与生成独立的评价引擎（evaluation/）进行，
  但只要评价模型与生成模型同源，就不是完全的独立评价。把结果作为倾向来解读。
- **消融的范围**: `--no-strong-claim` 只改变框架的有无。框架的贡献可能为正也可能为负，
  两种结果都如实报告。
