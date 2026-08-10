**Language:** [English](measurement.md) | [日本語](ja/measurement.md) | [中文](zh/measurement.md)

# Measuring sublation superiority and iterative improvement (compare / improve)

## compare — measuring sublation vs single-shot generation

`compare` is a device that runs "sublation" and "single-shot generation (or best-draft selection without sublation)" on the same input, measuring scores and win rates to compare them. It does not assert superiority; it leaves that to the numbers.

| Option | Behavior |
|---|---|
| `--runs N` | Runs the comparison N times and outputs the mean overall, standard deviation, and win rate (ELEVATE > baseline). Default 1 |
| `--baseline single` | Baseline = raw single-shot generation (`generate`). Default |
| `--baseline best-of-n` | Baseline = **best-draft selection without sublation** (the null hypothesis). From the same 8 drafts, choosing the highest-scoring draft without sublating vs. sublating are measured with the same evaluator. Requires `--evaluate` |
| `--no-strong-claim` | Removes the "strongest claim" strong-claim frame from agents (effectively a no-op under the thesis-focused format; kept for backward compatibility) |

Passing `--runs N` (N>1) aggregates each run's scores and outputs the following:

```bash
=== comparison aggregate ===
plain generation (single-shot): mean=0.778 sd=0.012 (n=3)
ELEVATE:                        mean=0.812 sd=0.009 (n=3)
difference (ELEVATE − baseline): mean=0.034 sd=0.015 (n=3)
win rate (ELEVATE > baseline): 3/3 = 100.0%
  win-rate 95% CI (Wilson): 43.8% to 100.0%
  difference 95% CI (t, two-sided): -0.003 to +0.071
  effect size (Cohen's d): +1.90
```

(The above is a format example of the aggregate output; the values are not measurements. The 95% CI is wide for small samples — gather n≥10 before discussing statistical significance.)

**Demonstration is not only statistics but also reading the artifacts.** `compare` saves both the raw AI generation (`raw.md`) and the elevated artifact (`elevated.md`) for each run. It generates a comparison document to view them objectively:

```bash
python render_comparison.py examples/<sample_dir>        # comparison.md (binds both)
python render_comparison.py examples/<sample_dir> --html # + comparison.html (side-by-side view)
```

Running this measurement many times on the same task and model and publishing the results under examples/ is the path that demonstrates this engine's reason to exist. It is fine for some tasks to fall below a 50% win rate (disclosing that is exactly what makes the claim honest). Do not bias the samples toward "full" only — spread across domains and vary the agent count and loop count. The goal is to show with measurements under multiple conditions that sublation superiority does not depend on a particular task or configuration.

## improve — a loop that polishes the elevated artifact

`improve` is a loop that **repeatedly polishes** an elevated artifact that was once produced:

```
elevated → revision draft(s) → sublate → new elevated → (repeat)
```

- round 1: diverge from the original task → sublation produces the **initial elevated artifact**.
- from round 2 on: each agent writes a **draft revising the previous elevated artifact**, and these are sublated into the next elevated artifact. The elevated artifact's results are inherited and accumulate with each loop turn. (Rather than "sublate once and done", it polishes further on top of the elevated artifact.)
- Each round is saved separately under `round_NN/` (`draft_*` / `reconciliation` / `elevated`), so history can be traced. `progress.md` records the length and evaluation of every round.

```bash
python main.py improve "TASK" --rounds 3                # repeat the sublation 3 times
python main.py improve "TASK" --rounds 5 --evaluate     # quality-evaluate each round
```

| Option | Behavior |
|---|---|
| `--rounds N` | Number of sublation rounds (default 3) |
| `--evaluate` | Quality-evaluates each round's elevated artifact and records overall in progress.md |
| `--min-improve` | Plateau threshold. Early-stops when the overall improvement from the previous round is below this (default 0.01). Only with `--evaluate` |
| `--quality-ceiling` | Quality-ceiling threshold. Stops without generating a revision round when overall is at or above this (default 0.75). Only with `--evaluate`; enabled by default |

`--evaluate`'s early stopping is a safety valve that keeps **over-correction from losing the original quality**. (1) **Quality-ceiling early-stop**: if the elevated artifact's overall is at or above `--quality-ceiling` (default 0.75), stop without generating the next revision round. The higher-quality an artifact already is, the more easily revision breaks it. (2) **Plateau early-stop**: stop when the improvement from the previous round is below `--min-improve` (default 0.01). In contrast to `compare`, which starts from zero each time, `improve` improves through inheritance. The stop reason is recorded under "**stop reason**" in progress.md.

Behavior check with mock (quality evaluation is disabled under mock, so overall = equal weights × each axis. The single-shot-generation equivalent starts at 0.600. Pass threshold 0.60):

```
[round 1 elevated] overall=0.600 (Pass)   ← equivalent to plain generation; room for improvement, not the ceiling
[round 2 elevated] overall=0.720 (Pass)   +0.120
[round 3 elevated] overall=0.720 (Pass)   +0.000 → judged plateaued and stopped (avoids over-correction)
```
