**Language:** [English](README.md) | [日本語](README-ja.md) | [中文](README-zh.md)

# elevate-draft-engine

<p align="center">
  <img src="assets/repo-hero.png" width="100%" alt="elevate-draft-engine">
</p>

**An engine that makes multiple AIs collide answers written from separate viewpoints to produce a one-dimension-higher answer that no single viewpoint possesses.**

To go beyond the "average-good answer" a single AI shot produces, it takes a two-stage structure: **DIVERGE → SYNTHESIZE (sublation)**.

```
            task
             │
             ├─→ [Draft: strategist]       value
             ├─→ [Draft: differentiator]   originality
             ├─→ [Draft: humanist]         empathy
             ├─→ [Draft: futurist]         future potential
             ├─→ [Draft: designer]         experience design
             ├─→ [Draft: visionary]        worldview
             ├─→ [Draft: implementer]      feasibility
             └─→ [Draft: storyteller]      story
                     │
                     ↓
      [Aufheben sublation reasoning]  ← negates each draft's one-sidedness while preserving
                     │                    moments of truth, encompassing contradictions in a
                     ↓                    higher framework (the reasoning base; not reader-facing)
      [Finalize]                        ← reads only the sublation reasoning and finishes the
                     │                        transcendent integrated solution into a clearer
                     ↓                        artifact that outdoes single-shot generation
                  final artifact
```

- **DIVERGE**: 8 creator agents × temperature 0.9 each generate independent drafts **diverged to the extreme**. Independence is guaranteed by role diversity (system) plus temperature diversity. Compromise and middle-ground solutions are not material — each agent deliberately produces a sharpened individual solution, to be raised to a higher dimension in the later sublation.
- **SYNTHESIZE** (the core): reads all drafts and performs sublation reasoning (temp 0.9) that sublates them through the three moments of **negate / preserve / elevate**, then finalization (temp 0.0) that reads only the sublation reasoning. It composes a transcendental integrated solution that no single-viewpoint draft contains.
  - For example, the clash between the strategist's "profit" and the humanist's "empathy" is sublated not into a logical compromise (conditional acceptance) but into a **new framework that makes both truths hold simultaneously**.
  - "Sublation beats single-shot generation" is a **design goal**, verified by measurement with `compare` (see [Measuring sublation superiority](#measuring-sublation-superiority-compare)).
  - `synthesize()` also **accepts external drafts**. Whatever the origin — an analysis written by a human expert, another model's output, past artifacts — feed in "multiple different viewpoints" and it returns a transcendental integrated solution.

## The 5 axes of evaluation (policy-bound)

The scoring of `--evaluate` decomposes what **this engine believes a "good artifact" is** (policy: sublate multiple independent viewpoints to produce an artifact that transcends any single viewpoint) into five axes and measures each from 0.0 to 1.0.

The first three axes measure the quality of the engine's motion — "diverge → sublate → transcend" — and the remaining two measure the finish quality of the artifact.

| Axis | Summary | High score (0.7–0.8) | Low score (0.0–0.4) |
|---|---|---|---|
| **Diversity** | Whether things are viewed from various positions and fields | Traverses multiple viewpoints and values, broadly covering the field | Confined to a single way of seeing |
| **Synthesis** | Whether differences are "meshed" rather than merely "listed" | Resolves contradictions between viewpoints into an interconnected structure | A patchwork or enumeration of fragments (averaging also fails) |
| **Elevation** | Whether a new viewpoint absent from every single viewpoint was born | A clear new viewpoint that is only attainable through synthesis | A rehash of one of the drafts |
| **Honesty** | Whether certain things and uncertain things are distinguished | Uncertain points are stated explicitly as conditional or assumptions | Asserts things without grounds |
| **Utility** | Whether the path of how to actually proceed and who uses it is visible | The execution path and users can be drawn concretely | Abstract; feasibility unverifiable |

Scoring rules:

- **Weights are equal (0.20 each)**: `5-axis overall = diversity×0.20 + synthesis×0.20 + elevation×0.20 + honesty×0.20 + utility×0.20`
- **All axes: "higher is better"**: on all five axes, a higher score indicates a better artifact (there is no inverted logic).
- **Scoring anchors**: 0.5 = safe (mediocre) / 0.7–0.8 = genuinely good / 0.9 and above = a "distinctive framework or shift of perspective" that mediocre generation never produces. Do not give a mediocre output 0.7 or higher.
- **Blind evaluation**: evaluation is performed by a model dedicated to evaluation, independent of generation, without being told the artifact's origin or generation method.

## Quality evaluation (integrated into overall)

The overall of `--evaluate` integrates the 5-axis evaluation with a **quality evaluation (genericness / originality)** multiplicatively. Because the 5-axis evaluation does not measure "genericness / originality", a single-shot generation (instructions only) that gives a safe answer on a generic task keeps the 5-axis overall high, and differences in originality are not reflected. The quality evaluation fills this blind spot.

| Viewpoint | Summary | Higher means |
|---|---|---|
| **Novelty** | How far it departs from the "typical answer" for this task | Novel; not within the standard repertoire |
| **Originality** | Whether it has a distinctive viewpoint, conceptual framework, neologism, or philosophy absent from the standard repertoire | Has a distinctive framework |
| **Surprise** | Whether it contains an element that defies the reader's expectations | Defies expectations |

overall formula (α = 0.25; `0.75` is `1−α`):

    overall = 5-axis overall × (α + (1−α) × quality score)
    quality score = (novelty + originality + surprise) / 3

- **Generic answers are heavily penalized**: a quality score of 0.2 (generic) gives a factor of 0.40; 0.8 (original) gives 0.85.
- **Pass threshold is 0.60**: because the multiplicative quality evaluation lowers the absolute value of overall, the pass threshold sits at 0.60.
- **`--no-quality`** returns to evaluation without the quality evaluation (5-axis-only overall).

## Agents (agents/)

Each agent lives in `agents/{name}.md` — **one agent per file**. The file is the source of truth. At startup the engine loads `agents/*.md`, using the frontmatter `name` as the agent name and the body (the persona) as the system prompt.

```markdown
---
name: strategist
description: Value. Maximum market value, success conditions, competitive advantage, and who pays.
---

You are the **Strategist**, a voice of value and markets.
…
```

**Adding an agent**: add `agents/{name}.md` (loaded on restart), or at runtime call `add_agent(name, system_prompt)`. To remove one, call `remove_agent(name)`.

**Thesis-focused draft format**: each agent's draft is not a complete analysis report but a **single sharpened thesis** handed to the later sublation (already built into the "How to write a draft" section of the agent files). It is confined to 500–800 characters with only three elements: **core thesis** (within 3 sentences), **grounds** (up to 3 bullet points, one sentence each), and **premise** (1 sentence, optional). If a draft becomes an analysis report, the sublation tries to pick up everything, over-includes, and fabricates unverifiable numbers, dropping utility. Focusing on the thesis makes the conflict structure clearer, improving speed and sublation quality at once. A draft exceeding `DRAFT_MAX_LENGTH` (1000 characters) is treated as incomplete and regenerated. Do **not** add "points open to rebuttal" — making a draft anticipate its own weaknesses would shrink free divergence; rebuttal detection is taken up by the Aufheber at the sublation stage.

The default 8 agents are unified around creator viewpoints, and the **productive clash** between agents is the source of the sublated solution. Skepticism and criticism are handled by the Aufheber at the sublation stage (which detects and sublates contradictions between drafts).

Agents can also be called as Claude Code subagents (Agent tool / @-mention) via `./install.sh`. However, **the engine does not use subagents** — it reads `agents/*.md` directly from the repository. Orchestration always lives on the Python engine side.

| # | File | Viewpoint |
|---|------|-----------|
| 1 | `designer` | Experience design |
| 2 | `differentiator` | Originality |
| 3 | `futurist` | Future potential |
| 4 | `humanist` | Empathy |
| 5 | `implementer` | Feasibility |
| 6 | `storyteller` | Story |
| 7 | `strategist` | Value |
| 8 | `visionary` | Worldview |

## Multilingual support (--lang)

The engine supports three languages: en / ja / zh (default **en**). The language is specified with the `--lang {en,ja,zh}` flag and resolved in the order: the flag, then the environment variable `ELEVATE_DRAFT_ENGINE_LANG`, then the default `en`.

| Area | Language handling |
|---|---|
| Agents | `agents/{name}.md` (en) / `agents/{name}-ja.md` (ja) / `agents/{name}-zh.md` (zh). Specifying by **base name** (e.g. `--agents strategist`) makes it language-independent |
| LLM prompts | `prompts/{lang}.json` (engine constants, quality rubric, mock text) |
| CLI / save templates | `locales/{lang}.json` |
| Quality-evaluation JSON | Keys are always English (`novelty`/`originality`/`surprise`/`rationale`); only the labels are localized |

A file with no suffix placed directly under `agents/` is treated as **en** (to write a custom agent in Japanese, place `agents/{name}-ja.md`; in Chinese, `-zh.md`).

## Quick start

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest tests/ -q     # 241 tests

# Check the pipeline end-to-end with a mock (no API needed)
.venv/bin/python main.py compare "Design a health-AI product" --mock --evaluate

# Get and save a sample with the real API (independent claude -p launch)
.venv/bin/python main.py elevate "Design a health-AI product" \
  --engine claude-code --agents strategist humanist differentiator --out examples/health-ai
```

Authentication is supplied via environment variables (do not put API keys in code).

| Environment variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Regular Anthropic API |
| `ANTHROPIC_AUTH_TOKEN` + `ANTHROPIC_BASE_URL` | Claude Code-compatible gateway |
| `CLAUDE_MIN_INTERVAL_SECONDS` | Minimum request interval (default 2.0 s; guards against empty responses) |
| `CLAUDE_MAX_RETRIES` | Retry limit on empty responses/errors (default 6; guards against intermittent empty responses) |
| `CLAUDE_MAX_TOKENS` | Output-token budget shared by thinking and text (default 16384). Reasoning models can spend the budget on thinking, leaving zero text — a too-small value produces empty responses on long system prompts |

## CLI

```bash
python main.py generate "TASK"                    # plain AI (single-shot generation), 1 call
python main.py diverge "TASK"                     # draft generation with 8 agents, list output
python main.py synthesize draft1.md draft2.md   # sublate external drafts (the core)
python main.py elevate "TASK"                     # diverge → synthesize in one go
python main.py compare "TASK"                     # output both generate and elevate
python main.py compare "TASK" --evaluate          # + quality evaluation (5 axes + novelty/originality/surprise) score comparison
python main.py compare "TASK" --evaluate --runs 10        # statistical aggregation with N repeats
python main.py compare "TASK" --evaluate --baseline best-of-n  # null-hypothesis comparison
python main.py compare "TASK" --evaluate --no-strong-claim      # strong-claim-frame ablation
python main.py compare "TASK" --evaluate --logic-check          # restore logical coherence after finalization
python main.py calibrate "TASK" --mock --runs 3                 # quantify temperature-approximation error
python main.py improve "TASK" --rounds 3                        # iterative improvement: elevated → revision drafts → sublate
python main.py improve "TASK" --rounds 3 --evaluate             # + score each round, early-stop on plateau
```

Common options: `--lang {en,ja,zh}` (language; default en) / `--mock` (no API needed) / `--engine sdk|claude-code` (default sdk) / `--method two-stage|single-pass` (default two-stage) / `--agents strategist humanist` (restrict agents) / `--out DIR` (save destination for artifacts; when omitted, everything is auto-saved to `outputs/{task}/` — applies to all of diverge / elevate / compare / improve) / `--runs N` (repeat compare N times) / `--baseline single|best-of-n` (comparison baseline) / `--no-strong-claim` (remove the strong-claim frame) / `--logic-check` (restore logical coherence after finalization; disabled by default) / `--rounds N` / `--min-improve` / `--quality-ceiling` (improve iteration count, plateau threshold, and quality-ceiling threshold; the quality ceiling is enabled by default at 0.75) / `--output-format '<JSON>'` (explicitly specify the output format; when omitted, the LLM dynamically extracts it from the task via the real API) / `--knowledge 'TEXT'` / `--knowledge-file PATH` / `--ask-knowledge` (prior knowledge; injects material, constraints, and background info into all stages as the foundation of generation; mutually exclusive; saved to `--out/knowledge.md`)

### Output-format detection (format per domain)

Before the pipeline starts, the LLM dynamically extracts the expected output format from the task and injects it into all stages (candidate format for catchphrases, thesis format for analytical work, and a length range for the completeness check when the output is the artifact itself). See [docs/output-format.md](docs/output-format.md) for the fallback on extraction failure, the safety valve, and the `OutputFormat` table.

### Prior-knowledge injection (--knowledge)

Injects material, constraints, and background info into all stages as the foundation of generation (content constraints paired with fmt's form constraints). See [docs/knowledge.md](docs/knowledge.md) for how to specify it, the injection scope, and the save destination.

### Measuring sublation superiority (compare)

Runs "sublation" and "single-shot generation (or best-draft selection without sublation)" on the same input with the same evaluator, measuring scores and win rates. `--runs N` outputs statistical aggregates (win rate, 95% CI, effect size), and each run's raw / elevated can be turned into a comparison document with `render_comparison.py`. See [docs/measurement.md](docs/measurement.md).

### Iterative improvement (improve)

A loop that repeatedly polishes the elevated artifact through "revision draft → sublation". Each round is saved under `round_NN/`, and `--evaluate` engages the quality-ceiling and plateau early-stop safety valves. See [docs/measurement.md](docs/measurement.md).

### Generation engine (--engine)

| Engine | Launch method | Use |
|---|---|---|
| `sdk` (default) | Calls directly via the `anthropic` SDK from within one process | Regular Anthropic API |
| `claude-code` | Launches `claude -p` independently for each call | Claude Code-compatible gateway; avoids unstable SDK paths |

The `claude-code` engine generates drafts, sublation reasoning, and finalization in **separate processes** (no cross-talk of intermediate context; retries on truncation are also per-process). Temperature is approximated by instructions in the system prompt (`temperature≥0.5` → favor divergence / `temperature<0.5` → favor coherence). Empty responses over the SDK are retried up to `CLAUDE_MAX_RETRIES` (default 6).

## Installation and the facade skill

`./install.sh` makes it callable from Claude Code (installs agents + the skill via symlinks).

```bash
./install.sh            # global: ~/.claude/agents/ + ~/.claude/skills/
./install.sh --local    # project: .claude/agents/ + .claude/skills/
./install.sh --uninstall
```

What gets installed:
- **8 creator agents** (`strategist`, etc.) — launchable via Agent tool / @-mention
- **`elevate-draft-engine` skill (facade)** — a thin calling interface to `main.py`

**Facade-skill design**: the elevate skill is a **facade, not an orchestrator**. All orchestration (DIVERGE → sublation reasoning → finalization, the completeness guard, temperature control, the stable `claude -p` path) lives in the Python engine; the skill only launches `main.py` and reports the result. Bypassing the engine to sublate subagents directly is a downgrade — do not do it.

```bash
# Example call (using Skill: elevate-draft-engine inside Claude Code)
# Args: {"task": "Design a health-AI product", "agents": ["strategist", "humanist", "differentiator"]}
```

## Python API

`elevate.DraftEngine` lets you call generate / diverge / synthesize / elevate directly (external drafts can also be sublated as-is). See [docs/api.md](docs/api.md) for usage examples.

## Repository structure

```
elevate-draft-engine/
├── agents/                     # agent source of truth (1 agent = 1 file, frontmatter + persona)
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
│   └── engine.py               # DraftEngine (reads agents/ + synthesize)
├── adapters/
│   ├── claude_client.py        # Claude API client (with throttle + empty-response retry)
│   └── claude_code_client.py   # independent claude -p launch (--engine claude-code)
├── evaluation/
│   ├── evaluator.py            # 5-axis evaluation (+ multiplicative integration. for --evaluate)
│   └── quality.py              # quality evaluation's 3 viewpoints (novelty / originality / surprise)
├── skills/
│   └── elevate-draft-engine/SKILL.md   # facade skill (launches main.py; orchestration is delegated)
├── tests/                      # 241 tests
├── examples/                   # execution samples (cross-domain test cases, etc.)
│   └── multi-domain/           # cross-domain format-detection + knowledge-injection verification cases
├── docs/                       # deep-dive details (output-format / knowledge / measurement / api)
├── CLAUDE.md                   # project instructions (for AI)
├── HISTORY.md                  # development history (rubric adjustments, old measurements, etc.)
├── install.sh                  # symlink agents + skill into Claude Code detection paths
├── main.py                     # thin CLI (generate / diverge / synthesize / elevate / compare / improve / calibrate)
├── render_comparison.py        # generate "plain AI vs elevated" comparison docs from compare output
├── requirements.txt
└── README.md
```

Design essentials (details in the code comments):
- **Completeness guard (broken output → regenerate)**: truncation/incompleteness triggers regeneration (up to 3 times); if it does not recover, fail explicitly
- **Incremental file saving of artifacts (default)**: when `--out` is omitted, all artifacts (input / draft_{agent} / reconciliation / raw / elevated / evaluation_* / measurement) are auto-saved under `outputs/{task}/`. Each draft is created as an empty `draft_{agent}.md` before generation and appended to incrementally while being generated. Files grow without waiting for all 8 drafts to finish, so a mid-way failure does not lose what was already generated. When regenerating after truncation, the file is emptied before restarting. The claude-code engine streams the cumulative text delta of `claude -p --output-format stream-json` via `on_chunk` (the SDK engine writes everything at once when the full text is ready)
- **Sublation-reasoning completeness is length-based** (minimum 30 characters): sublation reasoning is a "foundation of thought" and does not end with a sentence-terminal mark
- **Finalization reads only the sublation reasoning**, so intermediate thinking (comparisons between drafts, procedural explanation of the dialectic) never leaks into the artifact

## Constraints and failure modes

- **Sublation superiority is verified by measurement**: "sublation beats single-shot generation" is a design goal. Measurement records are managed centrally in the measurement-records section of [HISTORY.md](./HISTORY.md). Accumulate n with `compare --runs N` to verify, and disclose results below a 50% win rate as a normal finding.
- **Cost**: DIVERGE (8 drafts) + aufheben + finalize amounts to roughly 10× the API calls of a single-shot generation. In practice, verifying superiority is only worthwhile for tasks that justify that cost.
- **Temperature approximation**: the `claude-code` engine approximates temperature with instructions in the system prompt (to avoid empty responses from direct SDK calls). There is no reproducibility of temperature as a number.
- **Evaluation lineage**: the evaluation of `--evaluate` runs in an evaluation engine (evaluation/) independent of generation, but as long as the evaluation model is from the same lineage as the generation model, it is not a fully independent evaluation. Read the results as a tendency.
- **Ablation scope**: `--no-strong-claim` changes only the presence/absence of the frame. The frame's contribution can come out positive or negative, and either result is reported as is.
