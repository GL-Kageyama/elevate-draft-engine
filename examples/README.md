**Language:** [English](README.md) | [日本語](README-ja.md) | [中文](README-zh.md)

# Examples — accumulated samples

For each task, saves an execution example of **diverge (each agent's draft) → sublation (Aufheben) (artifact)**.

## Usage

**Run and save:**
```bash
# Real API (gateway): specify agents and save the execution sample
.venv/bin/python main.py elevate "TASK" \
  --agents strategist humanist differentiator --out examples/<task-dir>

# End-to-end check with a mock (no API needed)
.venv/bin/python main.py compare "TASK" --mock --evaluate
```

## Files per task

```
examples/<task-dir>/
├── input.md                          # the original task
├── format.md                         # extracted output format (OutputFormat)
├── knowledge.md                      # prior knowledge (only with --knowledge)
├── parameters.md                     # the run parameters (idea level, engine, agents, …)
├── drafts/                           # each agent's independent draft (thesis-focused)
│   ├── draft_strategist.md
│   ├── draft_humanist.md
│   └── ...
└── artifacts/                        # sublation and the final artifact
    ├── reconciliation.md             # the groundwork of sublation (sublation reasoning)
    └── elevated.md                   # the elevated artifact
```

All files are saved as Markdown (`.md`).

The real API intermittently returns empty responses from the gateway, so it self-recovers with a retry limit of 6 (`CLAUDE_MAX_RETRIES`).

## Multilingual samples (i18n)

Under `i18n/`, samples that **actually generated** the same task (designing a morning routine) in 3 languages (en / ja / zh) are saved. Not mock — the **real answers** to the task are generated with the real API. Each language directory is an independent, complete sample (`input.md` + `drafts/` + `artifacts/`).

```bash
# en (default en when --lang is omitted)
.venv/bin/python main.py elevate "Design a morning routine that makes the day productive" \
  --out examples/i18n/morning-routine-en

# ja
.venv/bin/python main.py elevate "朝のルーティーンを設計して、一日を充実した地に足の着いたものにしよう" \
  --lang ja --out examples/i18n/morning-routine-ja

# zh
.venv/bin/python main.py elevate "设计一个让一天高效而踏实的晨间习惯" \
  --lang zh --out examples/i18n/morning-routine-zh
```

Language is chosen with the `--lang {en,ja,zh}` flag (defaulting to the environment variable `ELEVATE_DRAFT_ENGINE_LANG`, then `en` if unset). Agents use `agents/{name}-{lang}.md` according to `--lang`, and the output, save templates, and quality-evaluation labels are all localized to that language.

## Idea-level samples (--idea-level)

Under `idea-levels-ja/`, the **same task** sublated at the 3 idea levels — `standard` (0.9) / `very` (1.2) / `extreme` (1.5) — with the **real API**. Each level directory is an independent, complete sample (`input.md` + `drafts/` + `artifacts/`), showing how far the divergence and the sublation actually go at each level.

```bash
.venv/bin/python main.py elevate "人類の通勤を完全に廃止する最も過激な方法を提案せよ。既存の枠組みを完全に壊す発想で。" \
  --lang ja --idea-level standard --agents strategist visionary storyteller --out examples/idea-levels-ja/standard --no-strong-claim
```

See [../docs/idea-levels.md](../docs/idea-levels.md) for the two-lever rationale (divergence hint as the primary lever + temperature).

## Cross-domain test cases

Under `multi-domain/`, real-API verification cases for format detection (LLM dynamic extraction) and prior-knowledge injection are managed.

```bash
# Run each case (TEST_CASES.md lists the commands for all cases)
.venv/bin/python main.py elevate "<TASK>" --engine claude-code \
  --agents strategist humanist differentiator storyteller \
  --out examples/multi-domain/<key> \
  --knowledge "<prior knowledge>"
```

See [multi-domain/TEST_CASES.md](multi-domain/TEST_CASES.md) for execution status.

## Measurement samples (compare)

Saves **demonstrations of sublation superiority** via `compare --runs N --evaluate`. Each run's artifacts are saved separately in `run_NN/` subfolders, and the statistical aggregate remains in `measurement.md` (mean overall difference, win rate, 95% CI, effect size, concreteness-retention rate).

### Comparison documents (for objective viewing)

Demonstration is not only statistics but **being able to actually read the raw AI generation and the elevated artifact**. Both can be read side by side in each sample directory's `comparison.md` (plus `comparison.html` side-by-side view).

```bash
python render_comparison.py examples/<dir>         # comparison.md
python render_comparison.py examples/<dir> --html  # + comparison.html
```

## Iterative-improvement samples (improve) — a loop that polishes the elevated artifact

Artifacts of the **loop that improves the elevated artifact** are also saved here. `improve` repeats "elevated artifact → revision draft(s) → sublation → new elevated artifact", saving each round separately under `round_NN/` (with every round's evaluation recorded in `progress.md`).

```bash
python main.py improve "<TASK>" --rounds 5 --evaluate --out examples/<sample>
```

With `--evaluate`, each round's elevated artifact is scored, and early-stopping happens when improvement plateaus (overall improvement < `--min-improve`) or reaches the quality-ceiling threshold (overall ≥ `--quality-ceiling`, default 0.75).
