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
            "これは与えられたタスクに対する完全な分析である。"
            "対象の本質は単一の観点では捉えきれず、複数の視点を弁証法的に止揚する"
            "統合的枠組みが必須であることを示す。"
            "第一に、価値の最大化と実現可能性の担保は両立しうる。"
            "第二に、共感と独自性は対立ではなく、相互に補強する。"
            "第三に、実装上のリスクは具体的な対策により管理可能である。"
            "第四に、この統合的視座は元のどの草案にも存在しなかった超越的な解であり、"
            "各観点の固有の真理を保存しながらその一面性だけを否定する。"
            "第五に、この止揚は単なる折衷ではなく、各観点の極端さを起点に一段高い次元を開く。"
            "なお、この結論は単一観点の草案には決して到達できない止揚の成果である。"
            "以上を踏まえ、実行への手がかりを伴う結論を提示した。"
        )


class FlakyGenerator:
    """最初の n_broken 回だけ不完全応答を返すモック（完全性ガードの検証用）。

    broken は「推理（長さ<60）にも最終化（終端記号なし）にも不合格」な文字列。
    complete は最終成果物のサイズ制約（ELEVATED_MIN_LENGTH=300〜MAX=1500）を
    満たす文である（最終化・単発昇華もこの文で合格する）。
    """

    def __init__(self, n_broken: int) -> None:
        self.n_broken = n_broken
        self.calls = 0

    def generate(self, system: str, user: str, *, temperature: float | None = None) -> str:
        self.calls += 1
        if self.calls <= self.n_broken:
            return "途中で打ち切られた不十分な応答"
        return (
            "これは与えられたタスクに対する完全な分析である。Target は明確、Value は実現可能、"
            "Risk は具体的な対策つき、Opportunity は拡張性を持つ。"
            "本結論は複数の観点を止揚する統合的枠組みであり、価値の最大化と実現可能性の担保、"
            "共感と独自性が相互に補強し合う構造を持つ。"
            "第一に、対立する観点は矛盾ではなく、一段高い次元で両立しうる。"
            "第二に、各観点の固有の真理を保存しながら、その一面性だけを否定するのが昇華の要諦である。"
            "第三に、この統合的視座は元のどの草案にも存在しなかった超越的な解を提示し、"
            "実行への手がかりを伴う具体的な結論を構成する。"
            "この結論は単一観点の草案には決して到達できない止揚の成果である。"
            "以上が到達した結論である。"
        )


def _draft_pair() -> list[Draft]:
    return [
        Draft(agent="strategist", content="草案Aの内容である。価値の最大化を狙う。"),
        Draft(agent="humanist", content="草案Bの内容である。共感を大切にする。"),
    ]


# ---- 素の生成 ----

def test_generate_is_instruction_only_with_no_system_prompt() -> None:
    """generate()（素の生成）は指示のみ——システムプロンプトを渡さず1回だけ呼ぶ。"""
    client = MockGenerator()
    engine = DraftEngine(client)
    out = engine.generate("タスク")
    assert len(client.calls) == 1
    assert client.calls[0]["system"] == ""
    assert client.calls[0]["user"] == "タスク"
    assert client.calls[0]["temperature"] is None
    assert out


def test_generate_regenerates_when_contaminated_by_facade_skill() -> None:
    """素の生成がグローバル skill（elevate-draft-engine ファサード）に汚染されたら再生成する。

    2026-08-09 実測: press-release の素の生成が「了解しました。**Elevate-Draft-Engine** を起動します。」
    というファサード skill の起動文言を出力した。完全性ガードの is_complete が汚染を不完全扱いして
    再生成し、汚染された出力を評価に渡さない。
    """

    class ContaminatedGenerator:
        def __init__(self) -> None:
            self.calls = 0

        def generate(self, system, user, *, temperature=None):
            self.calls += 1
            if self.calls == 1:
                return "了解しました。**Elevate-Draft-Engine** を起動します。まずエンジンの場所を特定します。。"
            return (
                "これは与えられたタスクに対する完全な分析である。"
                "対象の本質は単一の観点では捉えきれず、複数の視点を止揚する統合的枠組みが必須である。"
                "以上を踏まえ、実行への手がかりを伴う結論を提示した。"
            )

    client = ContaminatedGenerator()
    engine = DraftEngine(client)
    out = engine.generate("タスク")
    assert client.calls == 2  # 1回目は汚染で再生成
    assert "Elevate-Draft-Engine" not in out
    assert "起動します" not in out


def test_facade_contamination_detector() -> None:
    """汚染検出: ファサード skill の起動文言シグネチャを判定する。"""
    from elevate.engine import _is_facade_contamination

    assert _is_facade_contamination("了解しました。**Elevate-Draft-Engine** を起動します。。")
    assert _is_facade_contamination("まずエンジンの場所を特定します。。")
    assert not _is_facade_contamination("これはリサイクル素材スニーカーのプレスリリースである。")
    assert not _is_facade_contamination("")


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


class _DraftFailsFirstAgentGenerator:
    """最初のエージェントの草案だけを上限超過で失敗させるモック（後のエージェントは成功）。

    上限超過（DRAFT_MAX_LENGTH+1 字）を返し続けるため、完全性ガードが3回で諦めて
    RuntimeError を上げる——diverge の per-agent エラー捕捉を検証するためのモック。
    """

    def __init__(self, n_fail: int) -> None:
        self.n_fail = n_fail
        self.calls = 0

    def generate(self, system: str, user: str, *, temperature: float | None = None, on_chunk=None) -> str:
        from elevate.engine import DRAFT_MAX_LENGTH

        self.calls += 1
        if self.calls <= self.n_fail:
            return "あ" * (DRAFT_MAX_LENGTH + 1) + "。"  # 上限超過 → 不完全 → 再生成が続く
        text = "成功した草案である。"
        if on_chunk is not None:
            on_chunk(text)  # SDK アダプタ同様、全文を1回で流す（ストリーム保存用）
        return text


def test_diverge_skips_failed_agent_and_reports(tmp_path) -> None:
    """単一エージェントの草案が上限回数で失敗しても、残りで継続し失敗を報告する。

    実測 2026-08-09: 歌詞の草案が DRAFT_MAX_LENGTH 超過を繰り返し RuntimeError になり、
    行列（compare/improve）全体が落ちた。diverge は失敗エージェントだけスキップし、
    on_error で報告する（行列を落とさない「報告して継続」）。
    """
    client = _DraftFailsFirstAgentGenerator(n_fail=3)  # 最初の agent の3試行（AUFHEBEN_MAX_ATTEMPTS）
    engine = DraftEngine(client)
    failures: list[tuple[str, Exception]] = []
    drafts = engine.diverge(
        "タスク", agents=["strategist", "humanist"], draft_dir=tmp_path,
        on_error=lambda name, exc: failures.append((name, exc)),
    )
    # 失敗した strategist は含まれず、humanist だけで続行する
    assert [d.agent for d in drafts] == ["humanist"]
    assert len(failures) == 1
    assert failures[0][0] == "strategist"
    assert isinstance(failures[0][1], RuntimeError)
    # 失敗エージェントの部分草案ファイルは残さない（成功した分だけが残る）
    assert not (tmp_path / "draft_strategist.md").exists()
    assert (tmp_path / "draft_humanist.md").read_text() == "成功した草案である。"


def test_diverge_all_agents_failed_returns_empty(tmp_path) -> None:
    """全エージェントが失敗したら空リストを返す（synthesize 側が「草案がありません」で失敗）。"""
    client = _DraftFailsFirstAgentGenerator(n_fail=100)  # どの agent も失敗し続ける
    engine = DraftEngine(client)
    failures: list[tuple[str, Exception]] = []
    drafts = engine.diverge(
        "タスク", agents=["strategist", "humanist"], draft_dir=tmp_path,
        on_error=lambda name, exc: failures.append((name, exc)),
    )
    assert drafts == []
    assert [n for n, _ in failures] == ["strategist", "humanist"]


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


def test_synthesize_streams_reconciliation_and_artifact_to_sink(tmp_path) -> None:
    """昇華（reconciliation）と成果物（elevated）も、草案と同じ空ファイル先作成＋逐次追記で保存される。

    草案のストリーム保存を draft 以外の生成成果物へ横展開したもの。
    """
    # 昇華推理は長さ下限（AUFHEBEN_MIN_LENGTH=60）を、最終成果物（elevated）は
    # サイズ制約（ELEVATED_MIN_LENGTH=300〜MAX=1500）を満たす必要があるため長めの文を使う
    chunks = [
        "昇華推理の結論は「両草案の対立を否定・保存・高次化する一段高い枠組み」であり、"
        "単一観点では決して到達できない統合的視座を構成する。第一に、価値の最大化と"
        "実現可能性の担保は両立しうる。第二に、共感と独自性は対立ではなく相互に補強する。"
        "第三に、実装上のリスクは具体的な対策により管理可能である。第四に、この止揚は"
        "単なる折衷ではなく、各観点の極端さを起点に一段高い次元を開く。第五に、矛盾する"
        "真理を同時に成立させる枠組みは、元のどの草案にも存在しなかった超越的な解を提示し、"
        "各観点の固有の真理を保存しながらその一面性だけを否定する。"
        "この結論は単一観点の草案には決して到達できない止揚の成果であり、"
        "実行への手がかりを伴う統合的視座を示している。以上が到達した結論である。",
    ]
    client = _StreamingMockGenerator(chunks)
    client.first_chunk_sink = tmp_path / "reconciliation.md"
    engine = DraftEngine(client)
    reconciliation, artifact = engine.synthesize_with_reconciliation(
        _draft_pair(),
        reconciliation_sink=tmp_path / "reconciliation.md",
        artifact_sink=tmp_path / "elevated.md",
    )
    # 最初のチャンク到着時点で空ファイルが既に存在する（生成前に先作成）
    assert client.file_state_at_first_chunk == (True, 0)
    # モックは全コール同一文を返すため両ファイルとも同一内容で保存される
    expected = "".join(chunks)
    assert reconciliation == artifact == expected
    assert (tmp_path / "reconciliation.md").read_text() == expected
    assert (tmp_path / "elevated.md").read_text() == expected


def test_generate_streams_raw_to_sink(tmp_path) -> None:
    """素の生成（compare の raw ベースライン）も空ファイル先作成＋逐次追記で保存される。"""
    client = _StreamingMockGenerator(["完全な", "分析", "である。"])
    client.first_chunk_sink = tmp_path / "raw.md"
    engine = DraftEngine(client)
    out = engine.generate("タスク", sink=tmp_path / "raw.md")
    assert client.file_state_at_first_chunk == (True, 0)
    assert (tmp_path / "raw.md").read_text() == "完全な分析である。"
    assert out == "完全な分析である。"


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


def test_diverge_reports_failure_without_passing_broken_draft() -> None:
    """草案が上限回数で直らない場合、打ち切り草案を下流へ渡さない。

    2026-08-09 仕様変更: diverge は単一エージェントの失敗で RuntimeError を投げず、
    on_error に報告してスキップする（行列を落とさない「報告して継続」）。
    失敗した草案は戻り値に含めないので、昇華に打ち切り草案が渡らない。
    """
    client = FlakyGenerator(n_broken=100)
    engine = DraftEngine(client)
    failures: list[tuple[str, Exception]] = []
    drafts = engine.diverge(
        "タスク", agents=["strategist"],
        on_error=lambda name, exc: failures.append((name, exc)),
    )
    assert drafts == []  # 打ち切り草案は下流に渡らない
    assert len(failures) == 1
    assert failures[0][0] == "strategist"
    assert isinstance(failures[0][1], RuntimeError)


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


def test_is_creative_task_detection() -> None:
    """創作系タスク判定: 歌詞・小説・コピー等は真、散文の分析タスクは偽。"""
    from elevate.engine import _is_creative_task

    # 創作系（作品の完成形が長くなりうるジャンル）→ 上限緩和の対象
    assert _is_creative_task("「雨上がりの電話」というタイトルの歌謡曲の歌詞を書け")
    assert _is_creative_task("無人駅を舞台にした短編小説のプロットを構想せよ")
    assert _is_creative_task("リサイクル素材のスニーカー『Maru』のキャッチコピーを開発せよ")
    assert _is_creative_task("戦争のない世界についての詩を書け")
    assert _is_creative_task("亡霊と同居する物語の脚本を執筆せよ")

    # 非創作系（散文の分析・設計タスク）→ 既定の1000字上限のまま
    assert not _is_creative_task("ミニマリスト向け家計簿アプリ「Rei」の事業計画を設計せよ")
    assert not _is_creative_task("深層学習の解釈可能性に関する新しい科学仮説を提案せよ")
    assert not _is_creative_task("大学生向けの新しいアプリサービスのコンセプトを設計せよ")
    assert not _is_creative_task("資料のコピーを社内に配布する運用フローを策定せよ")


def test_draft_is_complete_respects_custom_max_length() -> None:
    """完全性判定の max_length を差し替えられる（創作系で上限を緩める経路）。"""
    from elevate import DRAFT_MAX_LENGTH_CREATIVE as _pkg_creative  # __init__ からの再輸出も確認
    from elevate.engine import DRAFT_MAX_LENGTH, DRAFT_MAX_LENGTH_CREATIVE, _draft_is_complete

    assert _pkg_creative == DRAFT_MAX_LENGTH_CREATIVE

    # 1000字を超えるが3000字未満の草案（実測の歌詞1116字に相当）
    over_default = "あ" * (DRAFT_MAX_LENGTH + 1) + "。"
    assert not _draft_is_complete(over_default)  # 既定上限では超過 → 不完全
    assert _draft_is_complete(over_default, max_length=DRAFT_MAX_LENGTH_CREATIVE)

    # 創作系上限すら超えたら、創作系でも不完全のまま
    at_creative_max = "あ" * (DRAFT_MAX_LENGTH_CREATIVE + 1) + "。"
    assert not _draft_is_complete(at_creative_max, max_length=DRAFT_MAX_LENGTH_CREATIVE)


class _LongDraftGenerator:
    """常に DRAFT_MAX_LENGTH 超・DRAFT_MAX_LENGTH_CREATIVE 未満の草案を返すモック。

    創作系タスクでは上限が緩むため成功するが、散文タスクでは上限超過で失敗する
    （diverge がタスク種別で max_length を切り替える経路の検証用）。
    """

    def __init__(self, length: int) -> None:
        self.text = "あ" * length + "。"

    def generate(self, system: str, user: str, *, temperature: float | None = None, on_chunk=None) -> str:
        if on_chunk is not None:
            on_chunk(self.text)  # SDK アダプタ同様、全文を1回で流す（ストリーム保存用）
        return self.text


def test_diverge_relaxes_cap_for_creative_task(tmp_path) -> None:
    """創作系タスク（歌詞等）は草案上限が DRAFT_MAX_LENGTH_CREATIVE に緩む。

    実測 2026-08-09: 歌詞の草案1116字が DRAFT_MAX_LENGTH=1000 を超えて3回失敗し行列が落ちた。
    同サイズの草案でも、歌詞タスクなら成功し、散文タスクなら失敗（スキップ）する。
    """
    from elevate.engine import DRAFT_MAX_LENGTH, DRAFT_MAX_LENGTH_CREATIVE, DraftEngine

    # 1000 字を超えるが 3000 字未満の草案（実測の1116字に相当）
    assert DRAFT_MAX_LENGTH < 1116 < DRAFT_MAX_LENGTH_CREATIVE

    # 歌詞（創作系）→ 上限緩和で成功する
    creative_client = _LongDraftGenerator(1116)
    creative_engine = DraftEngine(creative_client)
    creative_failures: list[str] = []
    creative_drafts = creative_engine.diverge(
        "「雨上がりの電話」というタイトルの歌謡曲の歌詞を書け",
        agents=["storyteller"],
        draft_dir=tmp_path / "creative",
        on_error=lambda name, exc: creative_failures.append(name),
    )
    assert [d.agent for d in creative_drafts] == ["storyteller"]
    assert creative_failures == []
    assert len(creative_drafts[0].content) == 1116 + 1  # 本体 + 終端記号
    assert (tmp_path / "creative" / "draft_storyteller.md").read_text() == creative_drafts[0].content

    # 散文（非創作系）→ 上限が1000のままなので失敗しスキップされる
    plain_client = _LongDraftGenerator(1116)
    plain_engine = DraftEngine(plain_client)
    plain_failures: list[str] = []
    plain_drafts = plain_engine.diverge(
        "ミニマリスト向け家計簿アプリ「Rei」の事業計画を設計せよ",
        agents=["strategist"],
        draft_dir=tmp_path / "plain",
        on_error=lambda name, exc: plain_failures.append(name),
    )
    assert plain_drafts == []
    assert plain_failures == ["strategist"]
    assert not (tmp_path / "plain" / "draft_strategist.md").exists()


def test_elevated_is_complete_bounds() -> None:
    """最終成果物（elevated）のサイズ制約: 上限（コンパクト）と下限（結論としての分量）。"""
    from elevate.engine import ELEVATED_MAX_LENGTH, ELEVATED_MIN_LENGTH, _elevated_is_complete

    # 下限以上・上限以下・終端記号で終わる → 完全
    valid = "これは結論として十分な分量を持つ文章である。" + "あ" * ELEVATED_MIN_LENGTH + "。"
    assert len(valid) >= ELEVATED_MIN_LENGTH
    assert _elevated_is_complete(valid)
    # 上限ちょうどまでなら完全
    exact_max = "あ" * (ELEVATED_MAX_LENGTH - 1) + "。"
    assert len(exact_max) == ELEVATED_MAX_LENGTH
    assert _elevated_is_complete(exact_max)

    # 下限未満は不完全（結論としての分量不足 → 再生成）
    too_short = "結論である。"
    assert len(too_short) < ELEVATED_MIN_LENGTH
    assert not _elevated_is_complete(too_short)
    # 上限超過は不完全（報告書化・過剰包摂 → 再生成）
    too_long = "あ" * ELEVATED_MAX_LENGTH + "。"
    assert not _elevated_is_complete(too_long)
    # 空は不完全
    assert not _elevated_is_complete("")
    # 分量は足りていても終端記号なしは不完全
    no_terminal = "あ" * (ELEVATED_MIN_LENGTH + 10)
    assert not _elevated_is_complete(no_terminal)


def test_reconciliation_regenerates_when_too_short() -> None:
    """推理が下限未満（推理放棄）なら再生成する。"""
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
