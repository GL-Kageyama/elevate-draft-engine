**Language:** [English](output-format.md) | [日本語](ja/output-format.md) | [中文](zh/output-format.md)

# Output-format detection (--output-format / auto-extraction)

Before the pipeline starts, the LLM dynamically extracts the expected output format from the task (`extract_format` — one lightweight call, temperature 0.0, cached for identical tasks). The extracted `OutputFormat` is injected into all stages:

```
Task → extract_format(task) [1 lightweight LLM call] → OutputFormat
                                                          │
    ┌─────────────────────────────────────────────────────┼──────────────────────────┐
    ↓                                                     ↓                          ↓
diverge()                                           aufheben()                 finalize()
・append fmt.draft_guidance to the task            ・append an instruction    ・replace TVRO with
  (for catchphrases, "candidates + grounds")         to keep deliverable_type   fmt.finalize_guidance
・if output_is_direct, relax the draft cap            in mind                   ・completeness check with
  to the creative-task limit                         (the dialectic itself       fmt.{min,max}_output_length
                                                      is unchanged)
```

`OutputFormat` ([elevate/engine.py](../elevate/engine.py)):

| Field | Meaning |
|---|---|
| `deliverable_type` | Name of the deliverable type (e.g. catchphrase / business plan / lyrics / novel) |
| `description` | What a good artifact for this task is (one sentence) |
| `draft_guidance` | Format instruction for agent drafts (thesis format for analytical work, candidates + grounds for short formats) |
| `finalize_guidance` | Format instruction for finalization (replaces the generic TVRO with a task-specific structure) |
| `min_output_length` / `max_output_length` | Length range of the final artifact (task-specific; e.g. tagline min=2 / novel max=8000) |
| `output_is_direct` | `true` = the artifact itself (copy, poem, lyrics) / `false` = an analysis about the artifact |

## Detailed behavior

- **On extraction failure, falls back to the existing behavior (analysis-report assumption, fixed values)** — a retreat to the safe side, not a degradation. For analytical tasks the LLM returns a `finalize_guidance` equivalent to TVRO, so behavior is identical to the existing one.
- `--output-format '<JSON>'` skips extraction and specifies explicitly (also works under mock; used for tests and reproduction).
- The extracted/specified spec is saved to `--out/format.md` (transparency).
- The completeness guard checks against the task-specific length range, and **direct artifacts (`output_is_direct`) are not required to end with a sentence-terminal mark** (taglines and poems normally do not end with "。"; requiring a fixed sentence-terminal check would send finished forms into a regeneration loop).
- **Spec self-contradiction is absorbed by the safety valve**: when an LLM-extracted format is effectively unachievable due to self-contradiction (e.g. the structure demanded by the extracted `finalize_guidance` exceeds the extracted `max_output_length`), after the maximum number of regenerations, accept and continue with the last structurally complete attempt (with a sentence-terminal mark), emitting a warning to stderr. A healthy artifact is not discarded over a spec inconsistency, and the whole pipeline is not brought down. Without fmt (the existing fixed-value check) it fails explicitly as before.
- Format conformance is a hard gate (the completeness guard) and is **not** part of the 5-axis rubric's score (the 5 axes are fixed policy; the goalposts are not moved).
