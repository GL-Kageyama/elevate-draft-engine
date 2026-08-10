**语言:** [English](../output-format.md) | [日本語](../ja/output-format.md) | [中文](output-format.md)

# 输出格式识别（--output-format / 自动提取）

在流水线开始前，由 LLM 从任务动态提取期望的输出格式
（`extract_format`。1 次轻量调用、温度 0.0、同一任务有缓存）。
把提取出的 `OutputFormat` 注入所有阶段:

```
Task → extract_format(task) [1 lightweight LLM call] → OutputFormat
                                                          │
    ┌─────────────────────────────────────────────────────┼──────────────────────────┐
    ↓                                                     ↓                          ↓
diverge()                                           aufheben()                 finalize()
・把 fmt.draft_guidance 追记到任务                ・追加让 deliverable_type  ・用 fmt.finalize_guidance
  （标语类用「候补+意图」形式）                   有意识的指示                  替换 TVRO
・若 output_is_direct（成果物本身）                ・（辩证法本身不变）       ・用 fmt.{min,max}_output_length
  则把草案上限放宽到创作系上限                                                   做完整性判定
```

`OutputFormat`（[elevate/engine.py](../elevate/engine.py)）:

| 字段 | 含义 |
|---|---|
| `deliverable_type` | 成果物的种类名（例: 标语 / 事业计划书 / 歌词 / 小说） |
| `description` | 这个任务中好的成果物是什么（1 句） |
| `draft_guidance` | 智能体草案的形式指示（分析类用论题形式，短形式用候补+依据） |
| `finalize_guidance` | 最终化的形式指示（把通用 TVRO 替换为任务固有结构） |
| `min_output_length` / `max_output_length` | 最终成果物的长度范围（任务固有。tagline min=2 / 小说 max=8000 等） |
| `output_is_direct` | `true`=成果物本身（copy・诗・歌词） / `false`=关于成果物的分析 |

## 行为细则

- **提取失败时回退到既有行为（以分析报告为前提・固定值）**——不是劣化，而是退避到安全一侧。
  分析类任务 LLM 会返回与 TVRO 相当的 `finalize_guidance`，因此与既有行为相同。
- 可以用 `--output-format '<JSON>'` 跳过提取而显式指定（mock 中也有效。用于测试・复现）。
- 提取/指定的规范保存到 `--out/format.md`（透明性）。
- 完整性保护按任务固有的长度范围判定，**直接成果物（output_is_direct）不要求句末符号**
  （标语和诗通常不以「。」结尾。要求固定的句末检查会把完成形态扔进重新生成循环）。
- **规范的自我矛盾由安全阀吸收**: 当 LLM 提取的格式自我矛盾（提取的 `finalize_guidance` 要求的结构 >
  提取的 `max_output_length` 等）、实质上无法达成时，在达到上限次数的重新生成后，
  接受结构上完成（有句末）的最后一次尝试并继续（向 stderr 输出警告）。
  不因为规范不一致就丢弃健全的成果物、导致整条流水线崩溃。无 fmt（既有的固定值判定）则
  照旧显式失败。
- 格式适合性是硬闸门（完整性保护），**不**作为五维 rubric 的得分
  （五维是政策固定。不移动球门柱）。
