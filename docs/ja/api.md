**言語:** [English](../api.md) | [日本語](api.md) | [中文](../zh/api.md)

# Python API

```python
from elevate import DraftEngine, Draft
from adapters.claude_client import ClaudeClient

engine = DraftEngine(ClaudeClient(), draft_temperature=0.9)

# 素のAI（単発生成）— 1 call
raw = engine.generate("健康AIの企画")

# エージェント管理
engine.list_agents()                 # 8種のデフォルトエージェント（agents/*.md から読込）
engine.add_agent("legal", "あなたは法規制の専門家です。")
engine.remove_agent("storyteller")

# Step 1: DIVERGE — 独立草案を生成（既定は全エージェント）
drafts = engine.diverge("健康AIの企画")
# draft_dir を渡すと各草案を空ファイルから生成中に逐次追記（CLI は既定で outputs/{タスク名}/ を渡す）
drafts = engine.diverge("健康AIの企画", draft_dir=Path("examples/health-ai"))

# Step 2: SYNTHESIZE — 複数の異なる草案を昇華（核心）
elevated = engine.synthesize(drafts)     # 内部: aufheben → finalize
elevated = engine.synthesize(drafts, method="single-pass")   # 単発昇華

# 外部草案もそのまま昇華できる
external = [Draft(agent="human-expert", content="..."), Draft(agent="other-model", content="...")]
elevated = engine.synthesize(external)

# 便利ラッパー: diverge → synthesize 一気
elevated = engine.elevate("健康AIの企画")
```
