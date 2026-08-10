**Language:** [English](api.md) | [日本語](ja/api.md) | [中文](zh/api.md)

# Python API

```python
from elevate import DraftEngine, Draft
from adapters.claude_client import ClaudeClient

engine = DraftEngine(ClaudeClient(), draft_temperature=0.9)

# plain AI (single-shot generation) — 1 call
raw = engine.generate("Design a health-AI product")

# Agent management
engine.list_agents()                 # 8 default agents (read from agents/*.md)
engine.add_agent("legal", "You are an expert on regulations.")
engine.remove_agent("storyteller")

# Step 1: DIVERGE — generate independent drafts (all agents by default)
drafts = engine.diverge("Design a health-AI product")
# Passing draft_dir appends each draft incrementally from an empty file while generating
# (the CLI passes outputs/{task}/ by default)
drafts = engine.diverge("Design a health-AI product", draft_dir=Path("examples/health-ai"))

# Step 2: SYNTHESIZE — sublate multiple different drafts (the core)
elevated = engine.synthesize(drafts)     # internally: aufheben → finalize
elevated = engine.synthesize(drafts, method="single-pass")   # single-shot sublation

# External drafts can also be sublated as-is
external = [Draft(agent="human-expert", content="..."), Draft(agent="other-model", content="...")]
elevated = engine.synthesize(external)

# Convenient wrapper: diverge → synthesize in one go
elevated = engine.elevate("Design a health-AI product")
```
