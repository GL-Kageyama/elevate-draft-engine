"""DraftEngine のテスト（モッククライアント使用）。

DraftEngine の公開API（generate / diverge / synthesize / elevate / エージェント管理）を
検証する。プロンプトの実測観察に依存しすぎないよう、呼出数・温度・引数構成・
中間思考の非混入を検証する。

検証対象: elevate/engine.py（DIVERGE → AUFHEBEN → FINALIZE の2段構え）
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
    LOGIC_CHECK_SYSTEM,
    AUFHEBEN_SYSTEM,
    SYNTHESIS_SYSTEM,
    AUFHEBEN_MAX_ATTEMPTS,
    _detect_sentimentality,
    _strip_strong_claim,
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
        if "Aufheben" in system:
            # 昇華推理は長さ基準（60字以上）で判定される
            return (
                "草案間の対立は「価値の最大化と実現性の担保」という軸に集約されるが、"
                "弁証法的止揚（アウフヘーベン）により両者は一段高い次元で統合される。"
                "否定・保存・高次化の三契機を経て、この昇華は単一観点の草案にはない解を構成する。"
            )
        return (
            "完全な分析である。Target は明確、Value は実現可能、Risk は具体的な対策つき、"
            "Opportunity は拡張性を持つ。以上が結論である。"
        )


class FlakyGenerator:
    """最初の n_broken 回だけ不完全応答を返すモック（完全性ガードの検証用）。

    broken は「推理（長さ<60）にも最終化（終端記号なし）にも不合格」な文字列。
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
    """各エージェントは草案を「核心的主張/根拠/前提」のテーゼ集中形式で書くことを要求する。

    草案は完全な分析レポートではなく、後の昇華（Aufheben）に渡す先鋭化した1つのテーゼ。
    「反論されそうな点」は含めない——草案に弱点を先読みさせると自由な逸脱が
    萎縮するため、反論の検出は昇華段階の Aufheber に任せる（不要・干渉）。
    """
    agents = load_agents()
    for name, prompt in agents.items():
        assert "核心的主張" in prompt, f"{name}: 核心的主張セクションが欠落"
        assert "根拠" in prompt, f"{name}: 根拠セクションが欠落"
        assert "前提" in prompt, f"{name}: 前提セクションが欠落"
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


# ---- 断言枠アブレーション（strong_claim_frame） ----

def test_strip_strong_claim_removes_frame_from_all_agents() -> None:
    """_strip_strong_claim は旧「最強の主張」枠と「枠を埋める」ステップを除去する。

    新フォーマットの組み込みエージェントには旧枠が存在しないため除去は no-op だが、
    旧枠を持つプロンプトが混入しても確実に除去される（後方互換の安全網）。
    """
    agents = load_agents()
    for name, prompt in agents.items():
        stripped = _strip_strong_claim(prompt)
        assert "最強の主張" not in stripped, f"{name}: 最強の主張が残存"
        assert "枠を埋める" not in stripped, f"{name}: 枠を埋めるが残存"
        assert "You are the" in stripped, f"{name}: ペルソナ本文が失われている"
        assert "核心的主張" in stripped, f"{name}: 新草案フォーマットが失われている"
    # 旧枠を持つプロンプトでも除去される（後方互換の安全網）
    # 「最強の主張」セクションは末尾まで除去される（旧形式では声の行が枠の後ろにあったため、
    # 声の行も一緒に消える＝従来動作のまま）。
    legacy = (
        "## 草案の作り方\n6. **枠を埋める**: 末尾に付ける。\n\n"
        "## 最強の主張\n（この草案で最も強く主張したいこと。）\nあなたの声は残る。"
    )
    stripped = _strip_strong_claim(legacy)
    assert "最強の主張" not in stripped
    assert "枠を埋める" not in stripped
    assert "草案の作り方" in stripped  # 前置き部分は残る


def test_strip_strong_claim_keeps_core_persona() -> None:
    """枠除去はペルソナ（本文・草案の作り方の指示）を壊さない。"""
    prompt = load_agents()["strategist"]
    stripped = _strip_strong_claim(prompt)
    assert "You are the **Strategist**" in stripped
    assert "草案の作り方" in stripped
    assert "核心的主張" in stripped  # テーゼ集中形式の指示は残る


def test_draftengine_no_strong_claim_strips_agents() -> None:
    """strong_claim_frame=False でエージェントプロンプトから枠が除去される。"""
    engine = DraftEngine(MockGenerator(), strong_claim_frame=False)
    assert len(engine.list_agents()) == len(DEFAULT_AGENTS)
    for name in engine.list_agents():
        assert "最強の主張" not in engine._agents[name]
        assert "枠を埋める" not in engine._agents[name]
        assert "核心的主張" in engine._agents[name]  # テーゼ集中形式は維持


def test_draftengine_strong_claim_default_keeps_frame() -> None:
    """既定（strong_claim_frame=True）でもテーゼ集中形式が維持される（旧枠は新形式に置換）。"""
    engine = DraftEngine(MockGenerator())
    assert "核心的主張" in engine._agents["strategist"]


def test_diverge_without_strong_claim_passes_stripped_prompt() -> None:
    """枠なしで diverge すると、除去済みプロンプトが生成器に渡る。"""
    client = MockGenerator()
    engine = DraftEngine(client, strong_claim_frame=False)
    engine.diverge("タスク", agents=["strategist"])
    system = client.calls[0]["system"]
    assert "最強の主張" not in system
    assert "枠を埋める" not in system
    assert "核心的主張" in system  # テーゼ集中形式の指示は残る


# ---- DIVERGE ----

def test_diverge_generates_one_draft_per_agent() -> None:
    """diverge() は登録済み全エージェントで草案を生成し、エージェント名と温度を渡す。"""
    client = MockGenerator()
    engine = DraftEngine(client, draft_temperature=0.9)
    drafts = engine.diverge("タスク")
    assert [d.agent for d in drafts] == DEFAULT_AGENTS
    assert len(client.calls) == 8
    assert all(c["temperature"] == 0.9 for c in client.calls)
    assert all(d.content for d in drafts)


def test_diverge_subset_agents() -> None:
    engine = DraftEngine(MockGenerator())
    drafts = engine.diverge("タスク", agents=["strategist", "humanist"])
    assert [d.agent for d in drafts] == ["strategist", "humanist"]


def test_diverge_unknown_agent_raises() -> None:
    engine = DraftEngine(MockGenerator())
    with pytest.raises(ValueError, match="未登録のエージェント"):
        engine.diverge("タスク", agents=["ghost"])


def test_diverge_on_draft_fires_per_generated_draft() -> None:
    """on_draft は各草案の生成完了時点で逐次呼ばれる（全完了を待たない）。"""
    client = MockGenerator()
    engine = DraftEngine(client)
    seen: list[str] = []
    drafts = engine.diverge(
        "タスク", agents=["strategist", "humanist"], on_draft=lambda d: seen.append(d.agent)
    )
    # 生成順に逐次通知され、戻り値の草案と同一内容を持つ
    assert seen == ["strategist", "humanist"]
    assert [d.agent for d in drafts] == seen


# ---- ストリーム草案保存（draft_dir: 空ファイル先作成 + 逐次追記） ----

class _StreamingMockGenerator:
    """on_chunk でチャンク列を逐次に流すモック（ストリーム草案保存の検証用）。

    n_broken で最初の n 回を「途中で打ち切られた不完全文」にする（完全性ガードの
    再生成と、失敗試行のファイルリセットを検証するため）。
    """

    def __init__(self, chunks: list[str], *, n_broken: int = 0) -> None:
        self.chunks = chunks
        self.n_broken = n_broken
        self.calls = 0
        self.file_state_at_first_chunk: tuple[bool, int] | None = None
        self.first_chunk_sink = None  # 最初の on_chunk 時のファイル状態を調べるための注入点

    def generate(
        self,
        system: str,
        user: str,
        *,
        temperature: float | None = None,
        on_chunk=None,
    ) -> str:
        self.calls += 1
        if self.calls <= self.n_broken:
            partial = self.chunks[0][:-1]  # 終端記号を欠いた不完全文
            if on_chunk is not None:
                on_chunk(partial)
            return partial
        full = "".join(self.chunks)
        for c in self.chunks:
            if on_chunk is not None:
                if self.file_state_at_first_chunk is None and self.first_chunk_sink is not None:
                    path = self.first_chunk_sink
                    self.file_state_at_first_chunk = (path.exists(), path.stat().st_size)
                on_chunk(c)
        return full


def test_diverge_draft_dir_writes_streamed_draft(tmp_path) -> None:
    """draft_dir 指定時、草案ファイルが生成内容と一致して保存される（on_chunk 経由）。"""
    client = _StreamingMockGenerator(["完全な", "草案", "である。"])
    engine = DraftEngine(client)
    drafts = engine.diverge("タスク", agents=["strategist"], draft_dir=tmp_path)
    assert drafts[0].content == "完全な草案である。"
    assert (tmp_path / "draft_strategist.md").read_text() == "完全な草案である。"


def test_diverge_draft_dir_creates_empty_file_before_generation(tmp_path) -> None:
    """空ファイルが生成開始（最初のチャンク到着）時点で既に存在し、中身が空である。

    ユーザー要望「草案作成時にまず空ファイルを作って、そこに逐次追記していく」の検証。
    """
    client = _StreamingMockGenerator(["完全な", "草案", "である。"])
    client.first_chunk_sink = tmp_path / "draft_strategist.md"
    engine = DraftEngine(client)
    engine.diverge("タスク", agents=["strategist"], draft_dir=tmp_path)
    assert client.file_state_at_first_chunk is not None
    exists, size = client.file_state_at_first_chunk
    assert exists is True  # 生成開始時点でファイルが既に作られている
    assert size == 0       # まだ空（これから追記される）


def test_diverge_draft_dir_truncates_on_regeneration(tmp_path) -> None:
    """打ち切りで再生成したとき、ファイルは失敗試行の部分文を残さない。

    失敗試行が書いた内容を空に戻してから再生成する（部分文 + 全文の重複を防ぐ）。
    """
    client = _StreamingMockGenerator(["完全な草案である。"], n_broken=1)
    engine = DraftEngine(client)
    drafts = engine.diverge("タスク", agents=["strategist"], draft_dir=tmp_path)
    assert client.calls == 2  # 失敗→再生成
    assert drafts[0].content == "完全な草案である。"
    path = tmp_path / "draft_strategist.md"
    # ファイルは成功試行の全文だけを持つ（失敗試行の部分文が残らない）
    assert path.read_text() == "完全な草案である。"


# ---- SYNTHESIZE（核心） ----

def test_synthesize_two_stage_reconcile_then_finalize() -> None:
    """two-stage: 昇華（AUFHEBEN）→ 最終化（FINALIZE）の2回呼び。"""
    client = MockGenerator()
    engine = DraftEngine(client)
    drafts = _draft_pair()
    out = engine.synthesize(drafts)
    assert len(client.calls) == 2
    assert AUFHEBEN_SYSTEM in client.calls[0]["system"]
    assert ANALYSIS_SYSTEM in client.calls[1]["system"] and FINALIZE_SYSTEM in client.calls[1]["system"]
    assert out


def test_synthesize_two_stage_reconcile_uses_draft_temperature_finalize_zero() -> None:
    """昇華推理は温度 0.9（極限の逸脱）、最終化は 0.0（一貫性）。"""
    client = MockGenerator()
    engine = DraftEngine(client, draft_temperature=0.9)
    engine.synthesize(_draft_pair())
    assert client.calls[0]["temperature"] == 0.9
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
    """single-pass: 単発昇華（1回呼び）。"""
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
    engine = DraftEngine(client, draft_temperature=0.9)
    out = engine.elevate("タスク")
    assert len(client.calls) == 8 + 2
    assert out


# ---- 完全性ガード（broken output → regenerate） ----

def test_diverge_regenerates_when_draft_truncated() -> None:
    """草案が文途中で打ち切られたら再生成する（打ち切り草案を昇華に流さない）。"""
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


def test_draft_over_max_length_is_incomplete() -> None:
    """草案が上限（DRAFT_MAX_LENGTH）を超えたら不完全扱い（分析レポート化の防止）。"""
    from elevate.engine import DRAFT_MAX_LENGTH, _draft_is_complete

    assert _draft_is_complete("核心的主張。")
    # 上限以内（本体 + 終端記号でちょうど上限）なら完全
    assert _draft_is_complete("あ" * (DRAFT_MAX_LENGTH - 1) + "。")
    # 上限を超えたら不完全（終端記号つきでも分析レポート化として再生成対象）
    long = "あ" * DRAFT_MAX_LENGTH + "。"
    assert not _draft_is_complete(long)


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
    """単発昇華（single-pass）が打ち切られたら再生成する。"""
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
    assert client.calls == AUFHEBEN_MAX_ATTEMPTS


# ---- 論理一貫性の復元工程（--logic-check） ----

def test_synthesize_logic_check_adds_third_call() -> None:
    """enable_logic_check=True で最終化の後に論理検査が追加呼び出しされる（3 call）。"""
    client = MockGenerator()
    engine = DraftEngine(client, enable_logic_check=True)
    engine.synthesize(_draft_pair())
    assert len(client.calls) == 3
    assert LOGIC_CHECK_SYSTEM in client.calls[-1]["system"]
    # 論理検査は温度 0.0（一貫性のため）
    assert client.calls[-1]["temperature"] is None


def test_synthesize_logic_check_disabled_no_extra_call() -> None:
    """既定（無効）では追加呼び出しが無い（従来の 2 call のまま）。"""
    client = MockGenerator()
    engine = DraftEngine(client)  # enable_logic_check は既定 False
    engine.synthesize(_draft_pair())
    assert len(client.calls) == 2


def test_synthesize_logic_check_method_override() -> None:
    """呼び出し時 enable_logic_check がコンストラクタ設定を上書きできる。"""
    client = MockGenerator()
    engine = DraftEngine(client, enable_logic_check=False)
    engine.synthesize(_draft_pair(), enable_logic_check=True)
    assert len(client.calls) == 3


# ---- 感情の道具化ガード（soft guard） ----

def test_detect_sentimentality_three_term_trope() -> None:
    """末期疾患 × 高齢 × 見捨てられ の三項共起は型通りの感傷として検出される。"""
    text = "藤原浩一、73歳。ステージ4の膵臓がん。余命半年。見捨てられた。"
    assert _detect_sentimentality(text) is True


def test_detect_sentimentality_missing_term_not_detected() -> None:
    """三項の一部だけでは検出しない（末期疾患だけでは自然な悲しみ文脈と区別できない）。"""
    assert _detect_sentimentality("末期がんと闘う患者の記録。") is False


def test_detect_sentimentality_cliche_emotion() -> None:
    """型通りの感傷定式（泣かせ定式）は単独でも検出される。"""
    assert _detect_sentimentality("この物語は涙が止まらない。") is True


def test_detect_sentimentality_natural_text_not_detected() -> None:
    """自然な共感文は誤検出しない（正の具体として機能する）。"""
    text = "高齢者の孤立は地域の見守りで支えられる。介護の現場では変化が起きている。"
    assert _detect_sentimentality(text) is False


# ---- 具体性保存指数（evaluation/specificity.py） ----

def test_preservation_rate_counts_surviving_concrete_tokens() -> None:
    """発散草案の具体トークン（カタカナ・数字・英単語）が昇華にどれだけ残るか。"""
    from evaluation.specificity import compute_preservation_rate

    drafts = [
        Draft(agent="strategist", content="ゾンビ知識を0件にするナレッジAIを設計する。"),
        Draft(agent="humanist", content="見捨てられた73歳の祖父をAIが見守る。"),
    ]
    # elevated: カタカナ語（ゾンビ・ナレッジ・AI）、数字（0・73）は一部残る
    elevated = "ナレッジAIでゾンビ知識を0件にし、高齢者を見守る昇華案である。"
    result = compute_preservation_rate(drafts, elevated)
    assert result["preservation_rate"] is not None
    assert 0.0 < result["preservation_rate"] < 1.0
    assert "ゾンビ" in result["matched"]
    assert "ナレッジ" in result["matched"]
    assert "0" in result["matched"]
    # per_draft はエージェント名ごとに集計される
    assert "strategist" in result["per_draft"]
    assert "humanist" in result["per_draft"]


def test_preservation_rate_empty_source_resilient() -> None:
    """具体トークンが無い草案では preservation_rate が None（評価不能）になる。"""
    from evaluation.specificity import compute_preservation_rate

    drafts = [Draft(agent="designer", content="おはようございます。")]  # カタカナ・数字・英単語なし
    result = compute_preservation_rate(drafts, "昇華成果物。")
    assert result["preservation_rate"] is None
    assert result["source_tokens"] == []


def test_preservation_rate_external_get_content() -> None:
    """Draft 以外のオブジェクトにも get_content で対応できる。"""
    from evaluation.specificity import compute_preservation_rate

    class _X:
        def __init__(self, agent: str, body: str) -> None:
            self.agent = agent
            self.body = body

    xs = [_X("a", "ゲームAIの設計。"), _X("b", "APIの設計。")]
    result = compute_preservation_rate(xs, "ゲームAIとAPIを統合した。", get_content=lambda x: x.body)
    assert result["preservation_rate"] == 1.0
