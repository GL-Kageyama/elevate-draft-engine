---
name: elevate-draft-engine
description: Facade to invoke the elevate-draft-engine pipeline (diverge → aufheben → finalize). Given a task, runs the Python engine via main.py, saves input + each draft + reconciliation + elevated artifact into examples/<task>/ (or a custom dir), and reports the result. Supports elevate / improve (iterative refinement: previous elevated → revision drafts → elevation) / compare (measured vs single-shot generation). All orchestration, completeness guards, and temperature control live in the engine — this skill only calls it. Use to elevate an idea through dialectical sublation (Aufheben) of maximally-divergent creator drafts, to re-sublimate existing draft files, to iteratively refine an elevated artifact, or to measure whether aufheben beats single-shot generation.
argument-hint: 'JSON: {"command": "elevate|improve|compare|synthesize", "task": "<task>", "lang": "en|ja|zh", "agents": ["strategist","humanist",...], "method": "two-stage|single-pass", "engine": "claude-code|sdk|mock", "rounds": 3, "evaluate": true, "min_improve": 0.01, "quality_ceiling": 0.75, "runs": 1, "baseline": "single|best-of-n", "output_format": "<optional; OutputFormat JSON. Omitted → LLM dynamically extracts from the task>", "knowledge": "<optional; prior knowledge (material / constraints / context). Injected into every generation stage, saved to --out/knowledge.md>", "knowledge_file": "<optional; load prior knowledge from a file>", "ask_knowledge": "<optional; prompt for prior knowledge interactively>", "save_dir": "<optional; defaults to examples/<slug>)"}'
---
---

# Elevate Draft Engine — Facade

## Skill Metadata
- **id**: `elevate-draft-engine`
- **version**: `2.3.0`
- **category**: `facade` (runbook. Orchestration is handled by the Python engine)
- **standalone**: `true` (no subagents required. The engine reads the agents from `agents/*.md`)
- **requires_agents**: `[]`

## Language Mode

The execution language is decided by `$ARGUMENTS.lang`, the `ELEVATE_DRAFT_ENGINE_LANG`
environment variable, or the default `en` — in that order.

- **en** (default): run the engine with no suffix. Output is English.
- **ja**: pass `--lang ja`. Agent definitions / LLM prompts / CLI & saved templates switch to Japanese.
- **zh**: pass `--lang zh`. Agent definitions / LLM prompts / CLI & saved templates switch to Chinese (Simplified).

Agent name resolution: `--agents` always takes language-independent base names
(`strategist`, `humanist`, …). The engine strips the language suffix and maps them to
`agents/*-{lang}.md` itself.

All **user-facing text** — the artifacts saved to `--out` and the report given back to
the user — must be in the requested language. Match the language of the user's request:
Japanese request → `--lang ja`, Chinese request → `--lang zh`, otherwise `en`.

## When to Activate

- When asked to "elevate this idea"
- When you want to raise multiple divergent drafts/analyses into a single higher artifact that no single view contains
- When asked to "polish / iteratively refine the elevated version" (`improve`: elevated → revision drafts (multiple) → elevation loop. From round 2 onward each agent revises the previous elevated, and that is elevated into the next version)
- When you want to measure whether elevation beats single-shot generation (`compare`: plain generation vs elevation, judged by the same evaluator)
- When you want to accumulate samples in `examples/` (this skill saves them automatically)
- When you want consistent invocation without memorizing every `main.py` flag

## Core Principle (being a facade)

> **Do NOT re-implement the orchestration inside Claude Code.**

This skill is a thin interface that **only calls `main.py`**. DIVERGE → elevation
reasoning → finalization logic, the completeness guard (truncation → regenerate),
the Aufheben temp 0.9 / finalize temp 0.0 temperature control, and the stable
`claude -p` path all live in the Python engine. **Do not launch the creator agents
as subagents and elevate by hand** — bypassing the engine loses the guard and
temperature control and is a downgrade. Execution is always `main.py` via Bash.

## How It Works

### Step 1: Resolve the arguments

`$ARGUMENTS` is JSON. Fields:

| Field | Default | Description |
|---|---|---|
| `command` | `elevate` | `elevate` (diverge → elevate) / `improve` (iterative refinement: elevated → revision drafts → elevation) / `compare` (measured comparison of plain generation vs elevation) / `synthesize` (elevate existing draft files) |
| `task` | (required) | the task (natural language) |
| `lang` | `en` | execution language (`en`/`ja`/`zh`). Agent definitions, LLM prompts, CLI, and saved templates all switch to this language. Default `en`. Also settable via the `ELEVATE_DRAFT_ENGINE_LANG` env var (CLI `--lang` wins) |
| `agents` | all 8 | creator agents to convene (`strategist` `humanist` `differentiator` etc.) |
| `method` | `two-stage` | `two-stage` (elevate → finalize) / `single-pass` (single-pass elevation) |
| `engine` | `claude-code` | `claude-code` (independent `claude -p` launch, stable) / `sdk` / `mock` |
| `rounds` | `3` | `improve` only: how many times to repeat elevation. From round 2 onward the drafts revise the previous elevated |
| `evaluate` | `false` | `improve`: quality-evaluate each round's elevated and early-stop when improvement plateaus / `compare`: enable score comparison |
| `min_improve` | `0.01` | `improve --evaluate` early-stop threshold. If overall improvement over the previous round is below this, stop (plateau; avoid over-correction) |
| `quality_ceiling` | `0.75` | `improve --evaluate` high-quality stop threshold. If the elevated's overall is at/above this, generate no further revision rounds (already-high-quality artifacts are fragile under revision. Re-tuned 0.85→0.75 because quality multiplication lowers the absolute overall) |
| `runs` | `1` | `compare` only: repeat the comparison N times and aggregate statistics (mean, win rate, standard deviation, 95% CI) |
| `baseline` | `single` | `compare` only: `single` (plain single-shot generation) / `best-of-n` (best draft without elevation = null hypothesis) |
| `output_format` | dynamic | specify the OutputFormat JSON explicitly (skips LLM extraction; also effective under mock). If omitted, the LLM dynamically extracts it from the task on the real API (catchphrases, lyrics, business plans — per-domain formats) |
| `knowledge` | none | prior knowledge (material / constraints / background). Injected directly after the task into every generation stage (draft / elevate / finalize) and saved to `--out/knowledge.md` (parallel to input.md / format.md). `knowledge_file` (read a path) / `ask_knowledge` (interactive input at launch) also available. Mutually exclusive |
| `knowledge_file` | none | load prior knowledge from a file (mutually exclusive with `knowledge`) |
| `ask_knowledge` | `false` | interactively prompt for prior knowledge at launch (mutually exclusive with `knowledge`) |
| `save_dir` | auto | save location. Default `examples/<slug>/` (below) |

### Step 2: Locate the engine

This skill is likely symlinked from the repository's `skills/elevate-draft-engine/`.
The engine (repo root) is two levels up from the skill file:

```bash
ENGINE_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
```

If `main.py` is not at the repo root, check where `ENGINE_REPO` resolves (if this skill
is symlinked, find the repo holding the symlink target and base from there).

### Step 3: Determine the save location

- If `save_dir` is not given, make a slug from the task: whitespace → hyphens, strip `/\:*?"<>|`, truncate to 30 chars. Japanese may be left as-is.
- Save under `$ENGINE_REPO/examples/<slug>/`.

### Step 4: Execute (launch main.py via Bash)

```bash
cd "$ENGINE_REPO"
.venv/bin/python main.py elevate "$TASK" \
  --engine claude-code \
  ${LANG:+--lang "$LANG"} \
  ${AGENTS:+--agents $AGENTS} \
  --method two-stage \
  ${KNOWLEDGE:+--knowledge "$KNOWLEDGE"} \
  --out "$SAVE_DIR"
```

**Language mode**: choose the execution language with `lang` (default `en`, `ja`/`zh`
also available). The engine resolves `--lang` → `ELEVATE_DRAFT_ENGINE_LANG` in that
order and switches agent definitions (`agents/*-{lang}.md`), LLM prompts
(`prompts/{lang}.json`), and CLI/saved templates (`locales/{lang}.json`) all to that
language. Agent selection (`--agents strategist` etc.) keeps language-independent base
names. If the user's request is in Japanese, pass `--lang ja`; if Chinese, pass `--lang zh`.

- The files saved by `main.py` are categorized by type: `input.md` (task) at the top of `--out`, `knowledge.md` (prior knowledge, only when given) also at the top of `--out` (parallel to input/format), `draft_{agent}.md` under `drafts/`, `reconciliation.md` (basis of the elevation) / `elevated.md` / `raw.md` under `artifacts/`, `evaluation_*.md` under `evaluations/`. compare separates further into `run_NN/`, improve into `round_NN/`. Old (flat) layouts can be realigned with `python examples/reclassify_output.py <dir>`.
- Each draft uses the **thesis-focused format** (core thesis / grounds / premise, 500–800 chars. Over `DRAFT_MAX_LENGTH`=1000 chars → regenerate) — a sharpened single thesis for the later elevation, not a full analysis report. **Creative tasks** (lyrics / novel / story / poem / catchphrase etc., judged by the `_is_creative_task` keywords) relax the cap to `DRAFT_MAX_LENGTH_CREATIVE`=3000 because finished works can be long.
- **Output format recognition**: on the real API the expected output format is dynamically extracted by the LLM before the pipeline starts (`extract_format`, one lightweight call; the result is saved to `--out/format.md`). The extracted `OutputFormat` is injected into every stage — `draft_guidance` (task-specific draft format) appended to agent drafts, `finalize_guidance` replacing the generic TVRO in finalization, and the completeness guard judging with the task-specific `{min,max}_output_length` (short artifacts like taglines are judged with the task-specific lower bound). `--output-format '<JSON>'` also allows explicit specification (skips extraction; also effective under mock). On extraction failure it falls back to existing behavior (analysis-report assumption). If the extracted spec is self-contradictory (required structure > max, unachievable), the safety valve accepts the last structurally complete attempt after the retry limit.
- The final artifact (`elevated.md`) also has two-way size constraints (`ELEVATED_MIN_LENGTH`=300 to `ELEVATED_MAX_LENGTH`=1500) — a conclusion too small, or over-inclusive as a report, fails and regenerates (judged by the task-specific length range when a task-specific `OutputFormat` was extracted).
- To elevate existing draft files (e.g., human-written analyses), use `synthesize`:

```bash
.venv/bin/python main.py synthesize "$ENGINE_REPO"/examples/foo/draft_*.md --task "TASK" ${LANG:+--lang "$LANG"} --out "$SAVE_DIR"
```

- To iteratively refine an elevated, use `improve` (elevated → revision drafts (multiple) → elevation loop. From round 2 onward each agent revises the previous elevated, and that is elevated into the next version):

```bash
.venv/bin/python main.py improve "$TASK" --rounds 3 --evaluate ${LANG:+--lang "$LANG"} --out "$SAVE_DIR/improve"
```

  - With `--evaluate` each round's elevated is quality-evaluated and stops when (1) overall is already ≥ `--quality-ceiling` (default 0.75) → **high-quality stop** (no further revision rounds), or (2) improvement is below `--min-improve` (default 0.01) → plateau stop. Both avoid losing the original quality through over-correction (already-high-quality artifacts are fragile under revision). The stop reason is recorded in `progress.md` under "停止理由". Each round is saved separately under `round_NN/`.

- To measure whether elevation beats single-shot generation, use `compare` (generate vs elevate, judged by the same evaluator; the condition labels are not passed to the evaluator so it stays blind):

```bash
.venv/bin/python main.py compare "$TASK" --evaluate --runs 3 ${LANG:+--lang "$LANG"} --out "$SAVE_DIR/comparison"
```

  - `--baseline best-of-n` switches to comparing against best-draft-without-elevation (the null hypothesis). `--runs N` accumulates n and aggregates mean / win rate / 95% CI / Cohen's d in `measurement.md` (**n=1 is statistically meaningless** — collect n≥10 before arguing superiority).

- Use `--engine mock` for smoke checks without the real API.
- Long runs (all 8 agents, etc.) can exceed 10 minutes. Run in the background (`run_in_background`) and wait for completion.

### Step 5: Verify and report

- Verify the saved files (input / each draft / reconciliation / elevated) exist and are non-empty.
- For `improve`, report the overall trajectory in `progress.md` (is improvement visible?); for `compare`, report the stats in `measurement.md` (win rate, 95% CI, effect size).
- Report a summary of the final artifact (`elevated.md`) — the core, the transcendent synthesis that no single-view draft contained (the result of the Aufhebung).
- **Write the report in the requested language (`lang`)** — the same language as the user's request.
- Do not commit or push (the user does that themselves). Do not include API keys in output or files.

## Failure Handling

- **Empty response / truncation**: the engine retries automatically (`CLAUDE_MAX_RETRIES`, default 6). Don't hand-patch.
- **Broken output**: don't fix by hand. Re-run `main.py` to regenerate (broken output → regenerate).
- **Evaluation axes**: the 5 axes are policy-bound (diversity / synthesis / elevation / honesty / utility, equal weight 0.20) and fixed. Don't change them (see README "評価の5軸").

## Output Conventions

The engine never outputs or saves API keys. `--out` saves input, all drafts, the basis
of the elevation, and the final artifact as Markdown (`.md`). `elevated.md` is the
artifact; `reconciliation.md` is the basis of the thinking (not for readers).

## Prompt

```
You are a thin facade for the elevate-draft-engine pipeline.

Your ONLY job is to invoke the Python engine (main.py) and report its result.
You must NOT re-implement the orchestration: do not launch the creator agents
as Claude Code subagents, do not try to sublate drafts by hand, do not
bypass the engine. All divergence, aufheben, finalization, completeness
guards, temperature control, and the improve loop live in main.py.

## Task

$ARGUMENTS

(Parse the JSON: command, task, lang (default "en"), agents, method, engine,
rounds/evaluate/min_improve for improve, runs/baseline for compare, save_dir.
Match the language of the task: if the task is in Japanese pass --lang ja,
if Chinese pass --lang zh, otherwise en.)

## Procedure

0. First, briefly tell the user the overview of this repository — **in the
   requested language (translate the following to ja for Japanese, zh for Chinese)**:

   > This is **Elevate-Draft-Engine** — an engine that pits the answers of
   > multiple AIs written from separate viewpoints against each other and produces
   > a single higher answer that none of the individual viewpoints contains.
   >
   > Each creator agent writes an independent draft diverging as far as possible
   > (DIVERGE), and those drafts are sublated together with their contradictions
   > (Aufheben) into a higher integrated answer.
   >
   > The artifact is evaluated on 5 axes (diversity / synthesis / elevation /
   > honesty / utility).

1. Locate the engine repo: `ENGINE_REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"`. Confirm main.py exists there.
2. Resolve save_dir: if omitted, `examples/<slug of task>/`.
3. Run main.py for the requested command (run in background if it may exceed 10 minutes):
   - `elevate`: `python main.py elevate "$TASK" --engine claude-code [--agents ...] --method two-stage [--lang "$LANG"] [--knowledge "$KNOWLEDGE"] --out "$SAVE_DIR"`
   - `improve`: `python main.py improve "$TASK" --rounds N [--evaluate] [--lang "$LANG"] [--knowledge "$KNOWLEDGE"] --out "$SAVE_DIR"` — elevated → revision drafts (multiple) → elevation loop
   - `compare`: `python main.py compare "$TASK" --evaluate --runs N [--baseline best-of-n] [--lang "$LANG"] [--knowledge "$KNOWLEDGE"] --out "$SAVE_DIR"` — measured comparison of plain generation vs elevation
   - `synthesize`: `python main.py synthesize "$ENGINE_REPO"/examples/foo/draft_*.md --task "$TASK" [--lang "$LANG"] [--knowledge "$KNOWLEDGE"] --out "$SAVE_DIR"`
4. Verify the saved files exist and are non-empty (input.md, draft_*.md, reconciliation.md, elevated.md; knowledge.md if knowledge given; improve adds progress.md / compare adds measurement.md).
5. Report — **in the requested language (lang)** — a summary of the elevated artifact:
   especially the sublation, the third position that no single draft contained (the
   Aufhebung). For improve, report the overall trajectory across rounds (is improvement
   visible?); for compare, report the stats (win rate, 95% CI, Cohen's d) and do not
   overclaim with n<10. Name the save directory.

Rules:
- Never run `git push`. Commit only if the user asks.
- Never include API keys in output or saved files.
- If output is broken/truncated, re-run main.py (regenerate) — never hand-patch.
- Do not change the evaluation axes (fixed: diversity / synthesis / elevation / honesty / utility, equal 0.20 weights — defined in README "評価の5軸").
```

Version history is consolidated in the repository's `HISTORY.md`.
