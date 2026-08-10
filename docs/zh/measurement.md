**语言:** [English](../measurement.md) | [日本語](../ja/measurement.md) | [中文](measurement.md)

# 升华优势性的测量与迭代改进（compare / improve）

## compare — 升华 vs 单次生成的实测

`compare` 是把「升华」与「单次生成（或不升华的最优草案选择）」在同一输入下运行、
实测得分与胜率进行比较的装置。不断言优势性，把结论交给数值。

| 选项 | 行为 |
|---|---|
| `--runs N` | 把比较重复 N 次，输出平均 overall・标准差・胜率（ELEVATE > 基线）。默认 1 |
| `--baseline single` | 基线 = 朴素 AI 单次生成（`generate`）。默认 |
| `--baseline best-of-n` | 基线 = **不升华的最优草案选择**（零假设）。在同一评价器下测量「从同一 8 份草案中不升华、选择最高得分草案」与「升华」两种情况。需要 `--evaluate` |
| `--no-strong-claim` | 从智能体去除旧「最强主张」断言框架（在命题集中形式下实质 no-op。为向后兼容而保留） |

传入 `--runs N`（N>1）时，汇总各 run 的得分并输出以下内容:

```bash
=== 比较汇总 ===
朴素生成（单次）: mean=0.778 sd=0.012（n=3）
ELEVATE:           mean=0.812 sd=0.009（n=3）
差（ELEVATE−基线）: mean=0.034 sd=0.015（n=3）
胜率（ELEVATE > 基线）: 3/3 = 100.0%
  胜率 95%CI（Wilson）: 43.8%〜100.0%
  差的 95%CI（t, 双侧）: -0.003〜+0.071
  效应量（Cohen's d）: +1.90
```

（上述是汇总格式的形式示例，不是实测值。
95%CI 在小样本时会很宽——请收集到 n≥10 之后再讨论统计上的优势性。）

**实证不仅是统计，也在于阅读成果物。** `compare` 在每次 run 中都同时保存朴素 AI 生成（`raw.md`）与
升华版（`elevated.md`）。为客观审视它们而生成比较文档:

```bash
python render_comparison.py examples/<sample_dir>        # comparison.md（把两者束在一起）
python render_comparison.py examples/<sample_dir> --html # + comparison.html（并排显示）
```

在同一任务・同一模型下多次执行本测量并公开结果到 examples/，是证明本引擎存在理由的路径。
存在胜率低于 50% 的任务也没关系（公开这一点才是诚实的陈述）。不要让样本只偏向「full」——
分散领域，改变智能体数量・循环次数。目的是用多条件的实测表明升华优势性不依赖特定任务・构成。

## improve — 打磨升华版的循环

`improve` 是把做好的升华版**反复打磨**的循环:

```
升华版 → 修改草案(复数) → 升华 → 新的升华版 → （重复）
```

- round 1: 从原始任务发散 → 用升华制作**初次升华版**。
- round 2 起: 各智能体写出**修改了上一版升华版的草案**，升华它们来制作下一版升华版。
  升华版的成果每转一圈循环就被继承、积累起来。
  （不是「升华为止」，而是以升华版为根基进一步打磨。）
- 各 round 分离保存到 `round_NN/`（`draft_*` / `reconciliation` / `elevated`），
  可追溯历史。全部 round 的长度与评价记录在 `progress.md`。

```bash
python main.py improve "任务" --rounds 3                # 重复升华 3 次
python main.py improve "任务" --rounds 5 --evaluate     # 对各轮做质量评估
```

| 选项 | 行为 |
|---|---|
| `--rounds N` | 重复升华的次数（默认 3） |
| `--evaluate` | 对每轮升华版做质量评估，把 overall 记录到 progress.md |
| `--min-improve` | 触顶阈值。与上一轮相比 overall 的改善低于此值则提前停止（默认 0.01）。仅 `--evaluate` 时 |
| `--quality-ceiling` | 高品位停止阈值。overall 高于此值则不生成修改轮次并停止（默认 0.75）。仅 `--evaluate` 时・默认有效 |

`--evaluate` 的提前停止，是**不让过度修正破坏原有优点**的安全阀。
(1) **高品位停止**: 升华版的 overall 达到 `--quality-ceiling`（默认 0.75）以上时，
不生成下一个修改轮次并停止。越已具高品位的成果物越容易因修改而破坏。
(2) **触顶停止**: 与上一轮相比的改善低于 `--min-improve`（默认 0.01）
则停止。与从零重新开始的 `compare` 相对，`improve` 通过继承来改善。
停止理由记录在 `progress.md` 的「**停止理由**」中。

用 mock 的动作确认（质量评估在 mock 中无效，因此 overall = 均等权重 × 各轴。相当于朴素 AI 生成的值从 0.600 开始。Pass 阈值 0.60）:

```
[round 1 升华版] overall=0.600（Pass）   ← 相当于朴素生成。不是天花板，还有改善余地
[round 2 升华版] overall=0.720（Pass）   +0.120
[round 3 升华版] overall=0.720（Pass）   +0.000 → 判断为触顶并停止（避免过度修正）
```
