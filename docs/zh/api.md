**语言:** [English](../api.md) | [日本語](../ja/api.md) | [中文](api.md)

# Python API

```python
from elevate import DraftEngine, Draft
from adapters.claude_client import ClaudeClient

engine = DraftEngine(ClaudeClient(), draft_temperature=0.9)

# 朴素 AI（单次生成）— 1 call
raw = engine.generate("健康AI产品策划")

# 智能体管理
engine.list_agents()                 # 8 个默认智能体（从 agents/*.md 读取）
engine.add_agent("legal", "你是法规领域的专家。")
engine.remove_agent("storyteller")

# Step 1: DIVERGE — 生成独立草案（默认全部智能体）
drafts = engine.diverge("健康AI产品策划")
# 传入 draft_dir 时，各草案从空文件开始生成并逐次追加（CLI 默认传 outputs/{任务名}/）
drafts = engine.diverge("健康AI产品策划", draft_dir=Path("examples/health-ai"))

# Step 2: SYNTHESIZE — 升华多个不同草案（核心）
elevated = engine.synthesize(drafts)     # 内部: aufheben → finalize
elevated = engine.synthesize(drafts, method="single-pass")   # 单次升华

# 外部草案也能原样升华
external = [Draft(agent="human-expert", content="..."), Draft(agent="other-model", content="...")]
elevated = engine.synthesize(external)

# 便捷包装: diverge → synthesize 一气呵成
elevated = engine.elevate("健康AI产品策划")
```
