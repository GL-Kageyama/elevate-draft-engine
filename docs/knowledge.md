**Language:** [English](knowledge.md) | [日本語](ja/knowledge.md) | [中文](zh/knowledge.md)

# Prior-knowledge injection (--knowledge)

Injects the material, constraints, and background info attached to a task (ingredients, target audience, price range, documents, etc.) into all stages as the foundation of generation. It is the **content constraint** paired with fmt (the form constraint), and the two are orthogonal:

```
Task → 【prior knowledge】 → 【this task's draft format / final-artifact format】（fmt）
```

| CLI | Behavior |
|---|---|
| `--knowledge "Material: recycled PET. Target: ages 20–30."` | Specify the knowledge directly |
| `--knowledge-file PATH` | Read long documents / design info from a file |
| `--ask-knowledge` | Enter interactively at startup (finish with Ctrl+D) |

## Injection scope

- The specified knowledge is injected immediately after the task into all generation stages — **diverge (draft) / aufheben (sublation) / finalize (finalization) / generate (single-shot)**. This prevents fabrication beyond the material and keeps the artifact consistent with the knowledge.
- **Not injected into extract_format** — format extraction (form) is done from the task alone; knowledge (content) is not mixed in.
- **Not injected into the 5-axis evaluation** — fixed policy. Outside the scope of the generation foundation.
- **Persists across improve's revision rounds** — because diverge attaches the knowledge internally, it does not drop between rounds.
- **compare is fair** — the same knowledge is injected into the single-shot generation baseline for comparison.
- The specified knowledge is saved to `--out/knowledge.md` (alongside input.md / format.md, for transparency).
- Without knowledge (previous behavior) nothing is injected. The three specification methods are mutually exclusive.
