"""DraftEngine のテスト（モッククライアント使用）。

DraftEngine の公開API（generate / diverge / synthesize / elevate / エージェント管理）を
検証する。プロンプトの実測観察に依存しすぎないよう、呼出数・温度・引数構成・
中間思考の非混入を検証する。

検証対象: elevate/engine.py（DIVERGE → SYNTHESIZE の2段構え）
エージェントは agents/*.md から読込まれる（正本はファイル）。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from elevate import Draft, DraftEngine  # noqa: E402
from elevate.engine import (  # noqa: E402
    ANALYSIS_SYSTEM,
    FINALIZE_SYSTEM,
    RECONCILIATION_SYSTEM,
    SYNTHESIS_SYSTEM,
    SYNTHESIS_MAX_ATTEMPTS,
    load_agents,
)

# agents/*.md のアルファベット順（ファイル名順）のデフォルトエージェント
DEFAULT_AGENTS = [
    "designer",
    "differentiator",
    "futurist",
    "humanist",
    "implementer",
    "storyteller",
    "strategist",
    "visionary",
]


class MockGenerator:
    """完全性ガードを必ず通過する応答を返すモック。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def generate(self, system: str, user: str, *, temperature: float | None = None) -> str:
        self.calls.append({"system": system, "user": user, "temperature": temperature})
        if "矛盾解決推理" in system:
            # 推理は長さ基準（30字以上）で判定される
            return (
                "草案間の対立は「価値の最大化と実現性の担保」という軸に集約される。"
                "解決仮説として、最小単位で制度に埋め込み、実証データで価値の主張を強化する。"
                "この統合を経て、単一観点では見えなかった第3の位置が得られる。"
            )
        return (
            "完全な分析である。Target は明確、Value は実現可能、Risk は具体的な対策つき、"
            "Opportunity は拡張性を持つ。以上が結論である。"
        )


class FlakyGenerator:
    """最初の n_broken 回だけ不完全応答を返すモック（完全性ガードの検証用）。

    broken は「推理（長さ<30）にも最終化（終端記号なし）にも不合格」な文字列。
    """

    def __init__(self, n_broken: int) -> None:
        self.n_broken = n_broken
        self.calls = 0

    def generate(self, system: str, user: str, *, temperature: float | None = None) -> str:
        self.calls += 1
        if self.calls <= self.n_broken:
            return "途中で打ち切られた不十分な応答"
        return (
            "完全な分析である。Target は明確、Value は実現可能、Risk は具体的な対策つき、"
            "Opportunity は拡張性を持つ。以上が結論である。"
        )


def _draft_pair() -> list[Draft]:
    return [
        Draft(agent="strategist", content="草案Aの内容である。価値の最大化を狙う。"),
        Draft(agent="humanist", content="草案Bの内容である。共感を大切にする。"),
    ]


# ---- 素の生成 ----

def test_generate_uses_analysis_system_at_default_temperature() -> None:
    """generate() は ANALYSIS_SYSTEM + 既定温度（None → 0.0）で1回だけ呼ぶ。"""
    client = MockGenerator()
    engine = DraftEngine(client)
    out = engine.generate("タスク")
    assert len(client.calls) == 1
    assert client.calls[0]["system"] == ANALYSIS_SYSTEM
    assert client.calls[0]["user"] == "タスク"
    assert client.calls[0]["temperature"] is None
    assert out


# ---- エージェント管理 ----

def test_list_agents_defaults_to_eight_creator_agents() -> None:
    """デフォルトエージェントは agents/*.md から読込まれる（アルファベット順）。"""
    engine = DraftEngine(MockGenerator())
    assert engine.list_agents() == DEFAULT_AGENTS
    assert set(load_agents()) == set(DEFAULT_AGENTS)


def test_load_agents_parses_frontmatter_name_and_body() -> None:
    """frontmatter の name がエージェント名、本文（ペルソナ）がシステムプロンプト。"""
    agents = load_agents()
    assert set(agents) == set(DEFAULT_AGENTS)
    for prompt in agents.values():
        assert "You are the" in prompt  # ペルソナ本文が読まれている
        assert not prompt.startswith("---")  # frontmatter 区切りが本文に混入しない
    assert "---" not in agents["strategist"]  # frontmatter 区切りが本文に残らない


def test_agents_mandate_draft_frame() -> None:
    """各エージェントは草案末尾に「最強の主張」の定型を要求する。

    reconcile が「各草案の最強の主張」を推測に頼らず確実に拾うための軽い枠。
    「反論されそうな点」は含めない——草案に弱点を先読みさせると自由な論述が
    萎縮するため、反論の検出は統合段階の reconciler に任せる（不要・干渉）。
    """
    agents = load_agents()
    for name, prompt in agents.items():
        assert "最強の主張" in prompt, f"{name}: 最強の主張セクションが欠落"
        assert "反論されそうな点" not in prompt, f"{name}: 反論されそうな点セクションが残存"


def test_add_agent_and_use_in_diverge() -> None:
    engine = DraftEngine(MockGenerator())
    engine.add_agent("legal", "あなたは法規制の専門家です。")
    assert "legal" in engine.list_agents()
    drafts = engine.diverge("タスク", agents=["legal"])
    assert [d.agent for d in drafts] == ["legal"]


def test_add_agent_duplicate_raises() -> None:
    engine = DraftEngine(MockGenerator())
    with pytest.raises(ValueError, match="既に登録"):
        engine.add_agent("strategist", "重複")


def test_remove_agent() -> None:
    engine = DraftEngine(MockGenerator())
    engine.remove_agent("storyteller")
    assert "storyteller" not in engine.list_agents()
    assert len(engine.list_agents()) == 7


def test_remove_agent_unknown_raises() -> None:
    engine = DraftEngine(MockGenerator())
    with pytest.raises(ValueError, match="登録されていません"):
        engine.remove_agent("ghost")


def test_agents_override_param() -> None:
    """agents dict を渡すとファイル読込を上書きできる（in-memory エージェント）。"""
    engine = DraftEngine(MockGenerator(), agents={"custom": "カスタムエージェント。"})
    assert engine.list_agents() == ["custom"]


# ---- DIVERGE ----

def test_diverge_generates_one_draft_per_agent() -> None:
    """diverge() は登録済み全エージェントで草案を生成し、エージェント名と温度を渡す。"""
    client = MockGenerator()
    engine = DraftEngine(client, draft_temperature=0.7)
    drafts = engine.diverge("タスク")
    assert [d.agent for d in drafts] == DEFAULT_AGENTS
    assert len(client.calls) == 8
    assert all(c["temperature"] == 0.7 for c in client.calls)
    assert all(d.content for d in drafts)


def test_diverge_subset_agents() -> None:
    engine = DraftEngine(MockGenerator())
    drafts = engine.diverge("タスク", agents=["strategist", "humanist"])
    assert [d.agent for d in drafts] == ["strategist", "humanist"]


def test_diverge_unknown_agent_raises() -> None:
    engine = DraftEngine(MockGenerator())
    with pytest.raises(ValueError, match="未登録のエージェント"):
        engine.diverge("タスク", agents=["ghost"])


# ---- SYNTHESIZE（核心） ----

def test_synthesize_two_stage_reconcile_then_finalize() -> None:
    """two-stage: 推理（RECONCILIATION）→ 最終化（FINALIZE）の2回呼び。"""
    client = MockGenerator()
    engine = DraftEngine(client)
    drafts = _draft_pair()
    out = engine.synthesize(drafts)
    assert len(client.calls) == 2
    assert RECONCILIATION_SYSTEM in client.calls[0]["system"]
    assert ANALYSIS_SYSTEM in client.calls[1]["system"] and FINALIZE_SYSTEM in client.calls[1]["system"]
    assert out


def test_synthesize_two_stage_reconcile_uses_draft_temperature_finalize_zero() -> None:
    """推理は温度 0.7（深度）、最終化は 0.0（一貫性）。"""
    client = MockGenerator()
    engine = DraftEngine(client, draft_temperature=0.7)
    engine.synthesize(_draft_pair())
    assert client.calls[0]["temperature"] == 0.7
    assert client.calls[1]["temperature"] is None  # 既定温度（0.0）


def test_synthesize_reconcile_prompt_lists_all_agents() -> None:
    """推理プロンプトに各草案がエージェント名付きで含まれる（N草案対応）。"""
    client = MockGenerator()
    engine = DraftEngine(client)
    engine.synthesize(_draft_pair())
    reconcile_user = client.calls[0]["user"]
    assert "【草案（観点: strategist）】" in reconcile_user
    assert "【草案（観点: humanist）】" in reconcile_user


def test_synthesize_finalize_excludes_draft_content() -> None:
    """最終化は解決済み推理だけを読み、草案本文（中間思考）が漏れない。"""
    client = MockGenerator()
    engine = DraftEngine(client)
    drafts = _draft_pair()
    engine.synthesize(drafts)
    finalize_user = client.calls[1]["user"]
    for d in drafts:
        assert d.content not in finalize_user


def test_synthesize_single_pass_single_call() -> None:
    """single-pass: 単発統合（1回呼び）。"""
    client = MockGenerator()
    engine = DraftEngine(client)
    out = engine.synthesize(_draft_pair(), method="single-pass")
    assert len(client.calls) == 1
    assert ANALYSIS_SYSTEM in client.calls[0]["system"] and SYNTHESIS_SYSTEM in client.calls[0]["system"]
    assert out


def test_synthesize_accepts_external_drafts() -> None:
    """外部草案（人間が書いた等）を Draft として渡せる。出所は問わない。"""
    client = MockGenerator()
    engine = DraftEngine(client)
    external = [
        Draft(agent="human-expert", content="専門家による草案である。現場の知見に基づく。"),
        Draft(agent="other-model", content="別モデルによる草案である。"),
    ]
    out = engine.synthesize(external)
    assert out


def test_synthesize_empty_drafts_raises() -> None:
    engine = DraftEngine(MockGenerator())
    with pytest.raises(ValueError, match="草案がありません"):
        engine.synthesize([])


def test_synthesize_unknown_method_raises() -> None:
    engine = DraftEngine(MockGenerator())
    with pytest.raises(ValueError, match="未知の method"):
        engine.synthesize(_draft_pair(), method="m3")


# ---- ELEVATE（diverge + synthesize 一気） ----

def test_elevate_runs_diverge_then_synthesize() -> None:
    """elevate() = diverge（全エージェント）+ synthesize（推理・最終化）。"""
    client = MockGenerator()
    engine = DraftEngine(client, draft_temperature=0.7)
    out = engine.elevate("タスク")
    assert len(client.calls) == 8 + 2
    assert out


# ---- 完全性ガード（broken output → regenerate） ----

def test_diverge_regenerates_when_draft_truncated() -> None:
    """草案が文途中で打ち切られたら再生成する（打ち切り草案を統合に流さない）。"""
    client = FlakyGenerator(n_broken=1)
    engine = DraftEngine(client)
    drafts = engine.diverge("タスク", agents=["strategist", "humanist"])
    assert len(drafts) == 2
    # strategist: 打ち切り→再生成（2回呼び）、humanist: 成功（1回）。計3回。
    assert client.calls == 3
    assert all(d.content for d in drafts)


def test_diverge_raises_after_max_attempts() -> None:
    """草案が上限回数で直らない場合は明示的失敗（打ち切り草案を渡さない）。"""
    client = FlakyGenerator(n_broken=100)
    engine = DraftEngine(client)
    with pytest.raises(RuntimeError, match="草案生成"):
        engine.diverge("タスク", agents=["strategist"])


def test_draft_complete_allows_markdown_closing() -> None:
    """末尾のマークダウン装飾（** の閉じ等）は打ち切りと判定しない。"""
    from elevate.engine import _draft_is_complete

    assert _draft_is_complete("結論である。")
    assert _draft_is_complete("結論である。**")
    assert _draft_is_complete("結論である。  ")
    assert not _draft_is_complete("結論は「この健保")

def test_reconciliation_regenerates_when_too_short() -> None:
    """推理が30字未満（推理放棄）なら再生成する。"""
    client = FlakyGenerator(n_broken=1)
    engine = DraftEngine(client)
    out = engine.synthesize(_draft_pair())
    assert client.calls == 3  # 推理1回失敗→再生成 → 最終化（再生成後は1回で成功）
    assert out


def test_finalize_regenerates_when_incomplete() -> None:
    """最終化が終端記号なしで打ち切られたら再生成する。"""
    client = FlakyGenerator(n_broken=2)
    engine = DraftEngine(client)
    out = engine.synthesize(_draft_pair())
    # 推理(1)・最終化(1)が失敗→それぞれ再生成。成功するまで2+2=4回。
    assert client.calls == 4
    assert out


def test_synthesis_regenerates_when_incomplete() -> None:
    """単発統合（single-pass）が打ち切られたら再生成する。"""
    client = FlakyGenerator(n_broken=1)
    engine = DraftEngine(client)
    out = engine.synthesize(_draft_pair(), method="single-pass")
    assert client.calls == 2
    assert out


def test_completeness_guard_raises_after_max_attempts() -> None:
    """上限回数（3回）で直らない場合は明示的失敗（不完全出力を渡さない）。"""
    client = FlakyGenerator(n_broken=100)
    engine = DraftEngine(client)
    with pytest.raises(RuntimeError, match="打ち切り/不完全"):
        engine.synthesize(_draft_pair())
    assert client.calls == SYNTHESIS_MAX_ATTEMPTS
