**Language:** [English](idea-levels.md) | [日本語](ja/idea-levels.md) | [中文](zh/idea-levels.md)

# Idea levels (--idea-level)

The idea level selects how extreme a position the divergence (diverge) and the sublation reasoning (Aufheben) reach. It is applied through **two levers**: an escalating **divergence hint** (the primary lever) plus a **temperature** (the secondary lever). The two-lever design exists because the reasoning model (deepseek-v4-pro via the gateway) may not reliably honor temperature >1 — the hint carries the "more extreme" semantics in the prompt, and the temperature reinforces it in the sampling.

| Level | Temperature | Meaning | Diverge / Aufheben hint |
|---|---|---|---|
| `standard` (default) | 0.9 | generally extreme — the previous behavior (backward compatible) | `[発散を重視]` divergence-priority |
| `very` | 1.2 | very extreme | `[非常に極端な発散を重視]` very-extreme divergence |
| `extreme` | 1.5 | extremely extreme | `[極度に極端な発散を重視]` extremely-extreme divergence |

Finalization always runs at temperature **0.0** regardless of the level.

## Why two levers (research findings)

- **Temperature >1 is accepted by the gateway.** Direct API calls confirmed that the DeepSeek Anthropic-compatible endpoint accepts temperature 1.2 and 1.5 without error. This answers the original research question "温度の1越え設定の可否" — yes, values above 1 are settable.
- **Temperature alone is not a reliable lever on a reasoning model.** The gateway's reasoning model routes the answer through an extended thinking block, and a single-sample probe could not prove that temperature alone yields measurably more extreme output. The semantics are therefore carried primarily by the hint, with temperature as reinforcement.
- **Appropriate parameter values** (the "どの程度のパラメータが適切なのか" question): the levels form a monotone ladder at 0.9 / 1.2 / 1.5. Values beyond 1.5 risk incoherence; 0.9 keeps the default behavior identical to the previous release.

## Engine behavior

| Engine | How the level is applied |
|---|---|
| `sdk` (default) | Both the temperature and the hint are passed to the API |
| `claude-code` | No temperature knob (`claude -p`); the level is approximated through the hint alone |

The `sdk` engine injects the hint **only when `idea_level` is explicitly given**, so existing pure-temperature calls keep their previous behavior. The `claude-code` engine uses the idea level first (three tiers) and falls back to the temperature-based two-tier hint when no level is given.

## Related

- `elevate/engine.py` — the `IDEA_LEVELS` table (the engine owns the temperature)
- `elevate/i18n.py` — `adapter_hint()` (i18n owns the hint keys)
- `main.py` — the `--idea-level {standard,very,extreme}` common CLI option
