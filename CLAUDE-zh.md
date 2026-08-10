**语言:** [English](CLAUDE.md) | [日本語](CLAUDE-ja.md) | [中文](CLAUDE-zh.md)

# elevate-draft-engine — Project Instructions

## 文档的规则

开发的经过・历史（带日期的变更叙事、再调整的经过、与旧设计的比较、过去的实测值等）
**不要写进 README / SKILL / examples/README**。历史统一整理到 `HISTORY.md` 一处。

在 README / SKILL / examples/README 只写**当前的信息**。当前的功能说明、当前的 CLI、
当前的设计理由（不带日期的简洁理由）是 OK 的。当说明某件事需要「过去曾是 X，但改成了 Y」
「因再调整(2)而…」这类导入经过的叙事时，把它写进 HISTORY.md。

**哪里有什么**:
- `README.md`: 当前的功能・CLI・API・五维・仓库结构（概要。仅当前信息）
- `docs/`: README 的深挖细节（`output-format.md` 输出格式识别 / `knowledge.md` 前提知识注入 / `measurement.md` compare・improve / `api.md` Python API）。README 在各节放置概要＋指向 docs/ 的链接
- `HISTORY.md`: 开发史（版本历史、rubric 再调整的经过、实测记录、知恵的评议会评价）
- `examples/README.md`: 当前的样本构成与用法（不刊登过去已删除的样本）
- `skills/elevate-draft-engine/SKILL.md`: 门面 skill（version 编号仅当前值，版本历史表在 HISTORY.md）
- `.claude/agents/`・`.claude/skills/`: 项目内检测用 symlink（指向 root `agents/`・`skills/` 的相对链接。引擎本体直接读取 `agents/*.md`，因此无需安装）
- `.claude-plugin/`: 插件分发定义（用于 `/plugin marketplace add`）。`install.sh` 是既有的全局/本地 symlink 方式

## 政策固定（不可改动）

- **五维 rubric**: 多样性 / 整合性 / 超越性 / 诚实性 / 实用性（均等 0.20）。`evaluation/evaluator.py` 与 `agents/*.md` 禁止修改。这五个维度是政策，不是评分的设计目标。
- **三契机辩证法**: 否定・保存・高次化这三契机是机构的核心。Aufheben 的温度 0.9・最终化的温度 0.0 固定。
- **命题集中形式**: 草案由 核心主张 / 依据 / 前提 这 3 个要素构成・500〜800 字。DRAFT_MAX_LENGTH=1000（创作类放宽到 3000）。

## 测试

用 `pytest tests/` 确认全部。246 件（截至 2026-08-11）。

## 不可破坏的东西

- 完整性保护（broken output → regenerate，最多 3 次）
- per-agent 错误捕捉（不让单个智能体的失败导致整个矩阵崩溃）
- 安全阀（fmt 规范自我矛盾时采用结构上完成的最终尝试）

## Git

- 仅当用户明确指示时才 `git push`。未指示的 push 禁止。
- 在 commit message 末尾追加 `Co-Authored-By: Claude <noreply@anthropic.com>`。
