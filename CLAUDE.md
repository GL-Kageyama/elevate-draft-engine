**Language:** [English](CLAUDE.md) | [日本語](CLAUDE-ja.md) | [中文](CLAUDE-zh.md)

# elevate-draft-engine — Project Instructions

## Document rules

Development history (dated change stories, adjustment history, comparisons with past designs, past measurement values, etc.) must **not** be written in **README / SKILL / examples/README**. History is consolidated in `HISTORY.md` alone.

README / SKILL / examples/README must contain **only current information**. Current feature descriptions, the current CLI, and current design rationale (brief reasons without dates) are fine. If explaining something requires a story of how it came to be — "it used to be X but was changed to Y", "per adjustment (2)…" — that goes in HISTORY.md.

**Where things live**:
- `README.md`: current features, CLI, API, the 5 axes, and repository structure (overview; current information only)
- `docs/`: deep-dive details for the README (`output-format.md` output-format detection / `knowledge.md` prior-knowledge injection / `measurement.md` compare and improve / `api.md` Python API). The README places an overview plus a docs/ link in each section
- `HISTORY.md`: development history (version history, rubric adjustment history, measurement records, Wisdom Council evaluations)
- `examples/README.md`: current sample structure and usage (do not include past deleted samples)
- `skills/elevate-draft-engine/SKILL.md`: the facade skill (only the current version number; the version-history table lives in HISTORY.md)
- `.claude/agents/` and `.claude/skills/`: symlinks for in-project detection (relative links to the root `agents/` and `skills/`; no installation needed because the engine itself reads `agents/*.md` directly)
- `.claude-plugin/`: plugin distribution definition (for `/plugin marketplace add`). `install.sh` is the conventional global/local symlink method

## Fixed policies (do not touch)

- **5-axis rubric**: diversity / synthesis / elevation / honesty / utility (equal weights of 0.20). `evaluation/evaluator.py` and `agents/*.md` must not be changed. These five axes are policy, not scoring design goals.
- **Three-moment dialectic**: the three moments of negate / preserve / elevate are the core of the mechanism. The idea level (`--idea-level`) selects how extreme a position the divergence and Aufheben reach: standard 0.9 (default, backward compatible) / very 1.2 / extreme 1.5 — each paired with an escalating divergence hint. Finalization temperature 0.0 is fixed.
- **Thesis-focused format**: a draft consists of three elements — core thesis / grounds / premise — in 500–800 characters. DRAFT_MAX_LENGTH=1000 (relaxed to 3000 for creative tasks).
- **i18n baseline**: multilingual support (en/ja/zh) is the default baseline for any fix or change. New or modified prompts, CLI messages, templates, and saved output must resolve through the 3-layer mechanism (locale JSON / per-language prompts / mirror tree), and user-facing text must be produced in the run's language (`--lang`).

## Tests

Run all tests with `pytest tests/`. 259 tests.

## Things that must not be broken

- Completeness guard (broken output → regenerate, up to 3 times)
- Per-agent error capture (a single agent's failure must not bring down the whole matrix)
- Safety valve (when the fmt spec is self-contradictory, adopt the last structurally complete attempt)

## Git

- Only push with `git push` when the user explicitly asks. Pushing without such a request is forbidden.
- Append `Co-Authored-By: Claude <noreply@anthropic.com>` to the end of commit messages.
