"""出力フォーマット認識（LLM動的抽出）のテスト。

パイプラインは従来「分析レポート（テーゼ草案 → TVRO 最終化）」に形式を固定していた。
キャッチコピー・歌詞・設計書など分野ごとに形式が異なる（実測: 「キャッチコピーを開発せよ」
というタスクが Target/Value/Risk/Opportunity の分析レポートになった）ため、タスクから
LLM が期待される出力形式を動的に抽出し、diverge → aufheben → finalize の全段階に注入する。

検証対象: elevate/engine.py（OutputFormat / extract_format / フォーマット認識完全性ガード）
- 抽出: 成功（JSON→OutputFormat）/ 失敗（不正JSON・不正範囲 → FORMAT_ANALYTICAL）/ キャッシュ
- 注入: draft_guidance / finalize_guidance（TVRO 置換）/ aufheben の deliverable_type ヒント
- 完全性: fmt の {min,max}_output_length で判定（5字のタグラインが不合格にならない）
- 伝播: diverge / synthesize / elevate / generate
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from elevate import FORMAT_ANALYTICAL, Draft, DraftEngine, OutputFormat, extract_format  # noqa: E402
from elevate.engine import (  # noqa: E402
    DRAFT_MAX_LENGTH,
    DRAFT_MAX_LENGTH_CREATIVE,
    ELEVATED_MAX_LENGTH,
    ELEVATED_MIN_LENGTH,
    FINALIZE_INSTRUCTION,
    EXTRACT_FORMAT_PROMPT,
    EXTRACT_FORMAT_SYSTEM,
    _build_aufheben_prompt,
    _build_finalize_prompt,
    _elevated_is_complete,
)


# ---- 定数 ----


@pytest.fixture(autouse=True)
def _clear_format_cache():
    """抽出キャッシュ（_format_cache）をテスト間で初期化する。

    キャッシュはタスク文字列のハッシュでメモ化されるため、同一タスクを使うテストが
    並ぶと前のテストの結果がキャッシュヒットしてしまう。テストは独立に検証する。
    """
    from elevate.engine import _format_cache

    _format_cache.clear()
    yield
    _format_cache.clear()


def _tagline_format() -> OutputFormat:
    """キャッチコピー相当のフォーマット（短い成果物・直接出力）。"""
    return OutputFormat(
        deliverable_type="キャッチコピー",
        description="履く人に届く短いコピー。",
        draft_guidance="候補を複数書く形式で草案を書け。",
        finalize_guidance="3案のキャッチコピーを提示し、各1行で根拠を添えよ。",
        min_output_length=2,
        max_output_length=300,
        output_is_direct=True,
    )


def test_format_analytical_reproduces_existing_behavior() -> None:
    """フォールバック（FORMAT_ANALYTICAL）は既存の固定値と一致する。

    抽出失敗時は従来パイプラインと完全に同一の挙動になる（安全側への退避）。
    """
    assert FORMAT_ANALYTICAL.deliverable_type == "分析レポート"
    assert FORMAT_ANALYTICAL.draft_guidance == ""  # 空 → 既存のテーゼ形式
    assert FORMAT_ANALYTICAL.finalize_guidance == FINALIZE_INSTRUCTION  # TVRO
    assert FORMAT_ANALYTICAL.min_output_length == ELEVATED_MIN_LENGTH
    assert FORMAT_ANALYTICAL.max_output_length == ELEVATED_MAX_LENGTH
    assert FORMAT_ANALYTICAL.output_is_direct is False


def test_output_format_is_exported_from_package() -> None:
    """OutputFormat / FORMAT_ANALYTICAL / extract_format が elevate から export される。"""
    assert OutputFormat is not None
    assert callable(extract_format)


# ---- extract_format（LLM による動的抽出） ----

class _FormatStub:
    """extract_format の検証用スタブ。

    指定の JSON を EXTRACT_FORMAT_SYSTEM への応答として返し、呼び出しを記録する。
    """

    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, user: str, *, temperature=None, idea_level=None, on_chunk=None) -> str:
        self.calls.append((system, user))
        assert system == EXTRACT_FORMAT_SYSTEM  # 軽量な形式分析者のみに抽出させる
        assert temperature == 0.0  # 抽出は決定性（温度 0.0）
        assert "{task}" not in user  # プロンプトはタスクでフォーマット済み
        return self.payload


def test_extract_format_parses_valid_json() -> None:
    """有効な JSON → 各フィールドが OutputFormat に反映される。"""
    stub = _FormatStub(
        '{"deliverable_type":"キャッチコピー","description":"短いコピー",'
        '"draft_guidance":"候補形式で","finalize_guidance":"3案を提示",'
        '"min_output_length":2,"max_output_length":300,"output_is_direct":true}'
    )
    fmt = extract_format(stub, "スニーカーのキャッチコピーを開発せよ")
    assert fmt.deliverable_type == "キャッチコピー"
    assert fmt.draft_guidance == "候補形式で"
    assert fmt.finalize_guidance == "3案を提示"
    assert fmt.min_output_length == 2
    assert fmt.max_output_length == 300
    assert fmt.output_is_direct is True
    assert stub.calls  # 抽出 LLM コールが1回だけ行われた


def test_extract_format_caches_by_task_hash() -> None:
    """同一タスクはキャッシュされ、再抽出の LLM コールをしない。"""
    stub = _FormatStub(
        '{"deliverable_type":"キャッチコピー","min_output_length":2,'
        '"max_output_length":300,"output_is_direct":true}'
    )
    fmt1 = extract_format(stub, "同じタスク")
    fmt2 = extract_format(stub, "同じタスク")
    assert fmt1 == fmt2
    assert len(stub.calls) == 1, "キャッシュにより再抽出しない"


def test_extract_format_falls_back_on_invalid_json() -> None:
    """JSON パース失敗 → FORMAT_ANALYTICAL（既存挙動）にフォールバック。"""
    stub = _FormatStub("これはJSONではない")
    fmt = extract_format(stub, "タスク")
    assert fmt == FORMAT_ANALYTICAL


def test_extract_format_falls_back_on_bad_lengths() -> None:
    """不正な長さ範囲（min>max 等）→ FORMAT_ANALYTICAL にフォールバック。"""
    stub = _FormatStub(
        '{"deliverable_type":"変な形式","min_output_length":500,"max_output_length":10,'
        '"output_is_direct":true}'
    )
    fmt = extract_format(stub, "タスク")
    assert fmt == FORMAT_ANALYTICAL


def test_extract_format_falls_back_on_missing_fields() -> None:
    """欠損フィールドは既存の固定値で補完される（min/max 以外はデフォルト）。"""
    stub = _FormatStub('{"deliverable_type":"戦略"}')
    fmt = extract_format(stub, "タスク")
    assert fmt.deliverable_type == "戦略"
    assert fmt.min_output_length == ELEVATED_MIN_LENGTH  # 既定値で補完
    assert fmt.max_output_length == ELEVATED_MAX_LENGTH
    assert fmt.finalize_guidance == FINALIZE_INSTRUCTION


def test_extract_format_accepts_string_boolean() -> None:
    """output_is_direct が "true" 文字列でも正しく読める。"""
    stub = _FormatStub(
        '{"deliverable_type":"歌詞","min_output_length":30,"max_output_length":8000,'
        '"output_is_direct":"true"}'
    )
    fmt = extract_format(stub, "歌詞を書け")
    assert fmt.output_is_direct is True


# ---- 完全性ガード（フォーマット認識） ----

def test_elevated_is_complete_uses_format_bounds() -> None:
    """fmt 指定時はその {min,max}_output_length で判定する。

    根本原因の解決: 5字のタグラインが固定の ELEVATED_MIN_LENGTH=300 で
    「分量不足」として再生成され続ける、という誤作動を防ぐ。
    """
    fmt = _tagline_format()
    tagline = "新しい一歩。"
    assert len(tagline) < ELEVATED_MIN_LENGTH  # 固定下限では不合格な短さ
    assert _elevated_is_complete(tagline, fmt)  # fmt では合格（min=2）
    assert not _elevated_is_complete(tagline)  # fmt なし＝固定値では不合格（後方互換）

    # fmt の上限も尊重する
    too_long = "あ" * (fmt.max_output_length + 1) + "。"
    assert not _elevated_is_complete(too_long, fmt)
    # fmt の下限未満も不合格
    assert not _elevated_is_complete("。", fmt)
    # 分析系（output_is_direct=False）は文終端を要求する（従来どおり）
    analysis_fmt = OutputFormat(
        deliverable_type="分析", description="", draft_guidance="", finalize_guidance="",
        min_output_length=300, max_output_length=1500, output_is_direct=False,
    )
    no_terminal = "あ" * 400
    assert not _elevated_is_complete(no_terminal, analysis_fmt)


def test_elevated_is_complete_relaxes_terminal_for_direct_output() -> None:
    """直接成果物（タグライン・詩・歌詞）は文末記号なしでも完成とみなす。

    コピーや詩は文末記号で終わらないのが普通（"Time to Move"）。これを要求すると
    完成形を不完全扱いにして再生成ループに落とす（実測のタグライン問題の一部）。
    """
    fmt = _tagline_format()
    assert _elevated_is_complete("新しい一歩", fmt)  # 文末記号なしでも合格
    assert _elevated_is_complete("Time to Move", fmt)  # 英字のみでも合格
    assert not _elevated_is_complete("", fmt)  # 空は不合格


# ---- プロンプト注入（diverge → aufheben → finalize） ----

class _RecordingGenerator:
    """diverge / synthesize / elevate の fmt 伝播を検証する記録モック。

    草案・止揚・最終化・抽出の各 system に対して完全性ガードを通過する文を返し、
    呼び出し（system, user）を記録する。
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, user: str, *, temperature=None, idea_level=None, on_chunk=None) -> str:
        self.calls.append((system, user))
        if system == EXTRACT_FORMAT_SYSTEM:
            return (
                '{"deliverable_type":"キャッチコピー","draft_guidance":"候補形式で草案を書け",'
                '"finalize_guidance":"3案を提示し各1行で根拠を添えよ",'
                '"min_output_length":2,"max_output_length":300,"output_is_direct":true}'
            )
        if "草案の作り方" in system:
            return "【核心的主張】これは草案である。\n- 根拠1: 最重要論点。\n【前提】テスト用。"
        if "Aufheben" in system:
            return (
                "草案間の対立は価値の最大化と実現性の担保という軸に集約されるが、"
                "弁証法的止揚により両者は一段高い次元で統合される。否定・保存・高次化を経て、"
                "この昇華は単一観点の草案にはない解を構成する。"
            )
        return (
            "これはモックの最終成果物である。フォーマットの形式で結論を提示する。"
            "第一に、価値の最大化と実現可能性の担保は両立しうる。"
            "第二に、共感と独自性は対立ではなく、相互に補強する。"
            "以上を踏まえ、実行への手がかりを伴う結論を提示した。"
        )


def test_build_finalize_prompt_uses_format_guidance() -> None:
    """finalize は fmt.finalize_guidance で TVRO を置き換える。"""
    fmt = _tagline_format()
    prompt = _build_finalize_prompt("タスク", "止揚の基盤", fmt)
    assert fmt.finalize_guidance in prompt
    assert FINALIZE_INSTRUCTION not in prompt  # TVRO は使われない


def test_build_finalize_prompt_defaults_to_tvro_without_fmt() -> None:
    """fmt なし（または空 guidance）なら従来どおり TVRO。"""
    prompt = _build_finalize_prompt("タスク", "止揚の基盤")
    assert FINALIZE_INSTRUCTION in prompt
    prompt2 = _build_finalize_prompt("タスク", "止揚の基盤", FORMAT_ANALYTICAL)
    assert FINALIZE_INSTRUCTION in prompt2


def test_build_aufheben_prompt_hints_deliverable_type() -> None:
    """aufheben は最終成果物の種別を意識させる指示を追記する（弁証法自体は不変）。"""
    fmt = _tagline_format()
    drafts = [Draft(agent="strategist", content="草案A。")]
    prompt = _build_aufheben_prompt("タスク", drafts, fmt)
    assert "「キャッチコピー」" in prompt  # deliverable_type が注入される


def test_diverge_enriches_task_with_draft_guidance() -> None:
    """diverge は fmt.draft_guidance をタスクに追記してエージェントに渡す。"""
    fmt = _tagline_format()
    client = _RecordingGenerator()
    engine = DraftEngine(client)
    drafts = engine.diverge("タスク", agents=["strategist"], fmt=fmt)
    assert [d.agent for d in drafts] == ["strategist"]
    draft_call = client.calls[0]
    assert "草案の作り方" in draft_call[0]  # エージェントのペルソナ
    assert "【このタスクの草案形式】" in draft_call[1]
    assert fmt.draft_guidance in draft_call[1]


def test_diverge_without_fmt_keeps_original_task() -> None:
    """fmt なし（フォールバック）は従来どおりタスクをそのまま渡す。"""
    client = _RecordingGenerator()
    engine = DraftEngine(client)
    engine.diverge("タスク", agents=["strategist"])
    assert client.calls[0][1] == "タスク"  # 草案形式の追記なし


def test_diverge_output_is_direct_relaxes_draft_cap() -> None:
    """fmt.output_is_direct=True は草案上限を創作系上限に緩める（キーワード判定を上書き）。"""
    from elevate.engine import _draft_is_complete

    class _LongDirectDraft:
        """1116字の草案を返す（散文上限1000超・創作系上限3000未満）。"""

        def generate(self, system: str, user: str, *, temperature=None, idea_level=None, on_chunk=None) -> str:
            text = "あ" * 1116 + "。"
            return text

    fmt_direct = OutputFormat(
        deliverable_type="詩", description="", draft_guidance="", finalize_guidance="",
        min_output_length=2, max_output_length=2000, output_is_direct=True,
    )
    engine = DraftEngine(_LongDirectDraft())
    drafts = engine.diverge("詩を書け", agents=["strategist"], fmt=fmt_direct)
    assert len(drafts) == 1, "直接成果物（詩）は1000字超の草案でも上限緩和で成功する"

    # 直接成果物でない fmt（分析）は従来の1000字上限のまま → 失敗
    fmt_analysis = OutputFormat(
        deliverable_type="分析", description="", draft_guidance="", finalize_guidance="",
        min_output_length=300, max_output_length=1500, output_is_direct=False,
    )
    engine2 = DraftEngine(_LongDirectDraft())
    failures: list[str] = []
    drafts2 = engine2.diverge("分析タスク", agents=["strategist"], fmt=fmt_analysis,
                              on_error=lambda name, exc: failures.append(name))
    assert drafts2 == []
    assert failures == ["strategist"]


def test_diverge_draft_guidance_relaxes_draft_cap() -> None:
    """fmt.draft_guidance（タスク固有の草案形式）は草案上限をフォーマット上限まで緩める。

    テーゼ集中形式（500〜800字）は draft_guidance が非空のときタスク固有の形式に
    置き換えられる（企画案の複数節＋実行例などは1000字を自然に超える）。この場合の
    草案上限はフォーマット自身の宣言上限（クリエイティブ上限で頭打ち）に従う。
    """
    class _LongDraft:
        """1116字の草案を返す（散文上限1000超・フォーマット上限2000未満）。"""

        def generate(self, system: str, user: str, *, temperature=None, idea_level=None, on_chunk=None) -> str:
            return "あ" * 1116 + "。"

    fmt_proposal = OutputFormat(
        deliverable_type="企画案", description="",
        draft_guidance="①ツール名②コアコンセプト③課題④ユーザー⑤理由⑥実行例⑦差別化の7節で書け。",
        finalize_guidance="", min_output_length=300, max_output_length=2000, output_is_direct=False,
    )
    engine = DraftEngine(_LongDraft())
    drafts = engine.diverge("企画案を考えよ", agents=["strategist"], fmt=fmt_proposal)
    assert len(drafts) == 1, "タスク固有の草案形式（draft_guidance）は1000字超の草案でも成功する"

    # 比較: draft_guidance が空の分析 fmt は従来どおり1000字上限のまま → 失敗
    fmt_analysis = OutputFormat(
        deliverable_type="分析", description="", draft_guidance="", finalize_guidance="",
        min_output_length=300, max_output_length=2000, output_is_direct=False,
    )
    engine2 = DraftEngine(_LongDraft())
    failures: list[str] = []
    drafts2 = engine2.diverge("分析タスク", agents=["strategist"], fmt=fmt_analysis,
                              on_error=lambda name, exc: failures.append(name))
    assert drafts2 == []
    assert failures == ["strategist"]


def test_synthesize_propagates_format_to_finalize() -> None:
    """synthesize_with_reconciliation は fmt を最終化・完全性ガードに伝播する。"""
    fmt = _tagline_format()
    client = _RecordingGenerator()
    engine = DraftEngine(client)
    reconciliation, artifact = engine.synthesize_with_reconciliation(
        [Draft(agent="strategist", content="草案A。")], task="タスク", fmt=fmt,
    )
    assert reconciliation
    assert artifact
    finalize_users = [u for (s, u) in client.calls if "最終化指示" in u]
    assert finalize_users, "最終化コールが存在する"
    assert fmt.finalize_guidance in finalize_users[0]
    # aufheben コールにも deliverable_type ヒントが入る
    aufheben_users = [u for (s, u) in client.calls if "昇華指示" in u]
    assert any("「キャッチコピー」" in u for u in aufheben_users)


def test_elevate_propagates_format() -> None:
    """elevate は fmt を diverge と synthesize の両方に伝播する。"""
    fmt = _tagline_format()
    client = _RecordingGenerator()
    engine = DraftEngine(client)
    out = engine.elevate("タスク", agents=["strategist"], fmt=fmt)
    assert out
    draft_user = client.calls[0][1]
    assert "【このタスクの草案形式】" in draft_user


def test_single_pass_synthesis_gets_format_guidance() -> None:
    """単発昇華（single-pass）も fmt の最終化指示と完全性判定を受ける（短いタグラインが合格）。"""
    fmt = _tagline_format()
    client = _RecordingGenerator()
    engine = DraftEngine(client)
    reconciliation, artifact = engine.synthesize_with_reconciliation(
        [Draft(agent="strategist", content="草案A。")], task="タスク",
        method="single-pass", fmt=fmt,
    )
    assert reconciliation == ""  # single-pass は止揚を持たない
    assert artifact
    synthesis_users = [u for (s, u) in client.calls if "昇華指示" in u]
    assert synthesis_users
    assert fmt.finalize_guidance in synthesis_users[0]  # 単発昇華にも最終化指示が注入される
    assert "「キャッチコピー」" in synthesis_users[0]


def test_format_spec_conflict_degrades_gracefully(capsys) -> None:
    """フォーマット仕様の自己矛盾（要求構造 > max_output_length）でパイプラインが落ちない。

    LLM 抽出の finalize_guidance が5節を要求するのに max=800 を返す等、仕様が達成不能な
    とき、構造的に完成した最後の試行（文終端あり）を受け入れて続行する——健全な成果物を
    仕様不整合だけで捨てない（実測 2026-08-09: Maru タグラインの最終化が1027字で
    max=800 超過のため3回再生成され、exit 1 で落ちた）。
    """

    class _OverMaxFinalize:
        """固定上限超過（1000字）だが文終端で終わる構造的に完成した出力を返す。"""

        def __init__(self) -> None:
            self.calls = 0

        def generate(self, system: str, user: str, *, temperature=None, idea_level=None, on_chunk=None) -> str:
            self.calls += 1
            if "草案の作り方" in system:
                return "【核心的主張】これは草案である。\n【前提】テスト用。"
            if "Aufheben" in system:
                return (
                    "草案間の対立は価値の最大化と実現性の担保という軸に集約されるが、"
                    "弁証法的止揚により両者は一段高い次元で統合される。否定・保存・高次化を経て、"
                    "この昇華は単一観点の草案にはない解を構成する。"
                )
            return "あ" * 1000 + "。"  # fmt.max=800 を超過、文終端あり

    # 自己矛盾するフォーマット: 構造はあるが max が厳しすぎる
    conflicting_fmt = OutputFormat(
        deliverable_type="キャッチコピー", description="",
        draft_guidance="", finalize_guidance="5つの節で構成せよ。",
        min_output_length=2, max_output_length=800, output_is_direct=True,
    )
    client = _OverMaxFinalize()
    engine = DraftEngine(client)
    artifact = engine.synthesize(
        [Draft(agent="strategist", content="草案A。")], task="タスク", fmt=conflicting_fmt,
    )
    assert artifact.endswith("。")  # 構造的に完成した出力が返る
    assert client.calls > 1  # 再生成は試みられた
    assert "受け入れて続行" in capsys.readouterr().err  # 安全弁の警告が出る


def test_completeness_guard_still_raises_without_fmt() -> None:
    """fmt なし（既存の固定値判定）は従来どおり明示的失敗する（緩和しない）。"""
    from elevate.engine import AUFHEBEN_MAX_ATTEMPTS

    class _AlwaysOverMax:
        """固定上限（1500字）を超えるが文終端で終わる出力を返す。"""

        def __init__(self) -> None:
            self.calls = 0

        def generate(self, system: str, user: str, *, temperature=None, idea_level=None, on_chunk=None) -> str:
            self.calls += 1
            return "あ" * 1600 + "。"

    client = _AlwaysOverMax()
    engine = DraftEngine(client)
    with pytest.raises(RuntimeError, match="打ち切り/不完全"):
        engine.synthesize([Draft(agent="strategist", content="草案A。")])
    # 止揚(1回, 成功) + 最終化(上限回数だけ失敗) = AUFHEBEN_MAX_ATTEMPTS + 1
    assert client.calls == AUFHEBEN_MAX_ATTEMPTS + 1


def test_single_pass_completeness_uses_format_bounds() -> None:
    """single-pass の完全性ガードが fmt の長さ範囲で判定される。

    短い直接成果物（タグライン）を固定下限300で再生成ループに落とさない。
    """

    class _ShortDirectFinalize:
        """10字のタグラインを返す（固定下限300では不完全・fmtでは完全）。"""

        def generate(self, system: str, user: str, *, temperature=None, idea_level=None, on_chunk=None) -> str:
            return "新しい一歩。"

    fmt = _tagline_format()
    engine = DraftEngine(_ShortDirectFinalize())
    artifact = engine.synthesize(
        [Draft(agent="strategist", content="草案A。")], method="single-pass", fmt=fmt,
    )
    assert artifact == "新しい一歩。"  # 再生成ループに入らず合格する


def test_generate_baseline_gets_format_guidance() -> None:
    """素の生成（compare のベースライン）にも同じフォーマット指示を与える（公平な比較）。"""
    fmt = _tagline_format()
    client = _RecordingGenerator()
    engine = DraftEngine(client)
    out = engine.generate("タスク", fmt=fmt)
    assert out
    assert "【このタスクの最終成果物形式】" in client.calls[0][1]
    assert fmt.finalize_guidance in client.calls[0][1]


def test_generate_without_fmt_keeps_baseline_unchanged() -> None:
    """fmt なしの素の生成は従来どおりタスクをそのまま渡す（後方互換）。"""
    client = _RecordingGenerator()
    engine = DraftEngine(client)
    engine.generate("タスク")
    assert client.calls[0][1] == "タスク"


def test_generate_baseline_safety_valve_accepts_overmax_complete(capsys) -> None:
    """素の生成（compare のベースライン）も fmt 自己矛盾では安全弁で受け入れる。

    昇華側には fallback_is_complete があるが素の生成側には無く、抽出フォーマットの
    max（例: 2500）を超える過長出力が temperature 0.0 で決定論的に3回再現すると
    RuntimeError で落ちていた（en compare 実測: "素の生成が3回連続で打ち切り/不完全"）。
    自己矛盾仕様（過長要求の finalize_guidance）では、構造的に完成した最後の試行を
    安全弁で受け入れて続行する。汚染出力は安全弁でも弾く。
    """

    class _OverMaxBaseline:
        """fmt.max を超えるが文終端で終わる素の生成を返す（決定論的・3回とも同一）。"""

        def __init__(self) -> None:
            self.calls = 0

        def generate(self, system: str, user: str, *, temperature=None, idea_level=None, on_chunk=None) -> str:
            self.calls += 1
            return "詳細な分析の節が続く。" * 250 + "まとめ。"  # max 2500 超過、文終端あり

    class _ContaminatedOverMaxBaseline:
        """過長かつファサード汚染の素の生成を返す（安全弁で受け入れない確認用）。"""

        def generate(self, system: str, user: str, *, temperature=None, idea_level=None, on_chunk=None) -> str:
            return "詳細な分析の節が続く。" * 250 + "まとめ。\n了解しました。**Elevate-Draft-Engine** を起動します。"

    fmt = OutputFormat(
        deliverable_type="分析レポート", description="",
        draft_guidance="", finalize_guidance="5つの節で詳細に構成せよ。",
        min_output_length=10, max_output_length=2500, output_is_direct=False,
    )

    # 過長だが構造的完成 → 安全弁で受け入れ、RuntimeError にしない
    client = _OverMaxBaseline()
    engine = DraftEngine(client)
    out = engine.generate("タスク", fmt=fmt)
    assert out.endswith("。")
    assert client.calls == 3  # 再生成は上限まで試みられた
    assert "受け入れて続行" in capsys.readouterr().err

    # 汚染した過長出力は安全弁でも弾いて明示的失敗する（汚染保護を弱めない）
    with pytest.raises(RuntimeError, match="打ち切り/不完全"):
        DraftEngine(_ContaminatedOverMaxBaseline()).generate("タスク", fmt=fmt)


# ---- CLI 結合（--output-format で抽出を明示指定） ----
#
# mock は抽出をスキップする（決定的な挙動を保つ）ため、CLI 統合テストでは
# --output-format <JSON> でフォーマットを明示指定して経路を検証する。

_TAGLINE_FORMAT_JSON = (
    '{"deliverable_type":"キャッチコピー","description":"履く人に届く短いコピー",'
    '"draft_guidance":"候補を複数書く形式で草案を書け",'
    '"finalize_guidance":"3案のキャッチコピーを提示し、各1行で根拠を添えよ",'
    '"min_output_length":2,"max_output_length":3000,"output_is_direct":true}'
)


def _run_cli(argv: list[str]) -> tuple[int, str]:
    """main.main() を実行し、(exit_code, stdout+stderr) を返す（cwd を汚さない）。"""
    import contextlib
    import io
    import os

    import main

    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main.main(argv)
    return code, out.getvalue() + err.getvalue()


def test_cli_output_format_override_injects_guidance(tmp_path, monkeypatch) -> None:
    """--output-format 指定で、草案・最終化にそのフォーマット指示が注入される。"""
    import main

    gen = main.MockGenerator()
    monkeypatch.setattr(main, "MockGenerator", lambda lang=None: gen)

    code, _ = _run_cli(
        ["improve", "Maruのキャッチコピー", "--mock", "--rounds", "1", "--out", str(tmp_path),
         "--output-format", _TAGLINE_FORMAT_JSON]
    )
    assert code == 0

    draft_users = [u for (s, u, _) in gen.calls if "草案の作り方" in s]
    assert draft_users
    assert "【このタスクの草案形式】" in draft_users[0]
    assert "候補を複数書く形式で草案を書け" in draft_users[0]

    finalize_users = [u for (s, u, _) in gen.calls if "最終化指示" in u]
    assert finalize_users
    assert "3案のキャッチコピーを提示し" in finalize_users[0]
    assert "Target" not in finalize_users[0]  # TVRO は置き換えられる

    # format.md に仕様が保存される（透明性）
    assert (tmp_path / "format.md").exists()
    assert "キャッチコピー" in (tmp_path / "format.md").read_text()


def test_cli_mock_without_override_skips_extraction(tmp_path, monkeypatch) -> None:
    """mock は --output-format なしなら抽出をスキップする（従来挙動・決定性）。"""
    import main

    gen = main.MockGenerator()
    monkeypatch.setattr(main, "MockGenerator", lambda lang=None: gen)

    code, _ = _run_cli(
        ["improve", "タスク", "--mock", "--rounds", "1", "--out", str(tmp_path)]
    )
    assert code == 0
    # 抽出コール（EXTRACT_FORMAT_SYSTEM）は一切行われない
    assert not any("形式分析者" in s or "format analyst" in s for (s, u, _) in gen.calls)
    assert not (tmp_path / "format.md").exists(), "mock は抽出しないため format.md を作らない"


def test_cli_invalid_output_format_warns_and_continues(tmp_path) -> None:
    """不正な --output-format は警告してフォーマット認識を無効化して続行する。"""
    code, out = _run_cli(
        ["improve", "タスク", "--mock", "--rounds", "1", "--out", str(tmp_path),
         "--output-format", "これはJSONではない"]
    )
    assert code == 0
    assert "解釈できません" in out
    # フォーマット非認識で完走する（従来挙動）
    assert (tmp_path / "artifacts" / "elevated.md").exists()
    assert not (tmp_path / "format.md").exists()


def test_cli_compare_and_elevate_accept_output_format(tmp_path) -> None:
    """compare / elevate にも --output-format を渡せる。"""
    code, _ = _run_cli(
        ["elevate", "Maruのキャッチコピー", "--mock", "--out", str(tmp_path),
         "--output-format", _TAGLINE_FORMAT_JSON]
    )
    assert code == 0
    assert (tmp_path / "artifacts" / "elevated.md").exists()
    assert (tmp_path / "format.md").exists()

    code, _ = _run_cli(
        ["compare", "Maruのキャッチコピー", "--mock", "--out", str(tmp_path / "cmp"),
         "--output-format", _TAGLINE_FORMAT_JSON]
    )
    assert code == 0
    assert (tmp_path / "cmp" / "artifacts" / "elevated.md").exists()
    assert (tmp_path / "cmp" / "artifacts" / "raw.md").exists()
