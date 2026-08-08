"""前提知識（knowledge）注入のテスト。

パイプラインの入力は従来 `task` 文字列のみで、素材・制約・背景情報（前提知識）を
形式化して注入する仕組みがなかった。本機能により `--knowledge` / `--knowledge-file` /
`--ask-knowledge` で起動時に前提知識を指定でき、生成の全段階（草案・止揚・最終化・
単発生成）に注入される。

設計: 前提知識は「形」ではなく「内容」の制約。出力フォーマット（形、fmt）とは直交する。
よって extract_format には注入せず、内容を生成する全段階に注入する。
プロンプト構造: タスク → 【前提知識】 → 【このタスクの草案形式/最終成果物形式】。
fmt の形式指示より常に前（タスク直後）に置く。

検証対象: elevate/engine.py（knowledge パラメータ注入）/ main.py（CLI フラグ・保存）
- 注入: diverge / aufheben / finalize / synthesis / generate
- 順序: タスク直後・fmt の形式指示より前
- CLI: --knowledge / --knowledge-file で完走し knowledge.md が保存される
- 後方互換: 知識なしでは従来挙動のまま（注入なし）
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from elevate import Draft, DraftEngine, OutputFormat  # noqa: E402
from elevate.engine import (  # noqa: E402
    EXTRACT_FORMAT_SYSTEM,
    _build_aufheben_prompt,
    _build_finalize_prompt,
    _build_synthesis_prompt,
    _knowledge_block,
)

KNOWLEDGE = "材料: 再生PET。ターゲット: 20〜30代。価格帯: 12,000円。"


# ---- プロンプトビルダー ----

def test_knowledge_block_empty_when_none() -> None:
    """知識なしは空リスト（既存プロンプトを一切汚さない）。"""
    assert _knowledge_block(None) == []
    assert _knowledge_block("") == []


def test_knowledge_block_formats_section() -> None:
    """知識は【前提知識】セクションに整形される。"""
    assert _knowledge_block(KNOWLEDGE) == [f"【前提知識】\n{KNOWLEDGE}"]


def test_build_aufheben_prompt_injects_knowledge_after_task() -> None:
    """止揚はタスク直後に知識を注入する（fmt のヒントより前）。"""
    drafts = [Draft(agent="strategist", content="草案A。")]
    prompt = _build_aufheben_prompt("タスク", drafts, fmt=None, knowledge=KNOWLEDGE)
    assert prompt.index("【タスク】") < prompt.index("【前提知識】") < prompt.index("【草案（観点: strategist）】")
    assert KNOWLEDGE in prompt


def test_build_synthesis_prompt_injects_knowledge_after_task() -> None:
    """単発昇華もタスク直後に知識を注入する。"""
    drafts = [Draft(agent="strategist", content="草案A。")]
    prompt = _build_synthesis_prompt("タスク", drafts, fmt=None, knowledge=KNOWLEDGE)
    assert prompt.index("【タスク】") < prompt.index("【前提知識】") < prompt.index("【草案（観点: strategist）】")
    assert KNOWLEDGE in prompt


def test_build_finalize_prompt_injects_knowledge_after_task() -> None:
    """最終化もタスク直後に知識を注入する（成果物が知識と矛盾しない）。"""
    prompt = _build_finalize_prompt("タスク", "止揚の基盤", fmt=None, knowledge=KNOWLEDGE)
    assert prompt.index("【タスク】") < prompt.index("【前提知識】") < prompt.index("【止揚の基盤】")
    assert KNOWLEDGE in prompt


# ---- エンジン伝播（記録モック） ----


class _RecordingGenerator:
    """diverge / synthesize / generate の knowledge 伝播を検証する記録モック。

    完全性ガードを通過する文を返し、呼び出し（system, user）を記録する。
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, user: str, *, temperature=None, on_chunk=None) -> str:
        self.calls.append((system, user))
        if "草案の作り方" in system:
            return "【核心的主張】これは草案である。\n- 根拠1: 最重要論点。\n【前提】テスト用。"
        if "Aufheben" in system:
            return (
                "草案間の対立は弁証法的止揚により一段高い次元で統合される。"
                "否定・保存・高次化を経て、この昇華は単一観点の草案にはない解を構成する。"
            )
        return (
            "これはモックの最終成果物である。前提知識を土台に結論を提示する。"
            "第一に、価値の最大化と実現可能性の担保は両立しうる。"
            "第二に、共感と独自性は対立ではなく、相互に補強する。"
            "第三に、実装上のリスクは具体的な対策により管理可能である。"
            "第四に、この統合的視座は元のどの草案にも存在しなかった超越的な解であり、"
            "各観点の固有の真理を保存しながらその一面性だけを否定する。"
            "第五に、この止揚は単なる折衷ではなく、各観点の極端さを起点に一段高い次元を開く。"
            "第六に、実行への手がかりは前提知識の制約の範囲内で具体的に定められ、"
            "第七に、この結論は素材・ターゲット・価格帯という与えられた制約を踏まえた、"
            "以上を踏まえ、実行への手がかりを伴う結論を提示した。"
        )


def test_diverge_injects_knowledge_into_draft_task() -> None:
    """diverge は各エージェントの草案タスクに知識を注入する。"""
    client = _RecordingGenerator()
    engine = DraftEngine(client)
    drafts = engine.diverge("タスク", agents=["strategist"], knowledge=KNOWLEDGE)
    assert [d.agent for d in drafts] == ["strategist"]
    user = client.calls[0][1]
    assert user.index("タスク") < user.index("【前提知識】")
    assert KNOWLEDGE in user


def test_diverge_knowledge_before_format_guidance() -> None:
    """知識は fmt の草案形式指示より前に置かれる（内容が形に先立つ）。"""
    fmt = OutputFormat(
        deliverable_type="キャッチコピー", description="",
        draft_guidance="候補を複数書く形式で草案を書け。", finalize_guidance="",
        min_output_length=2, max_output_length=300, output_is_direct=True,
    )
    client = _RecordingGenerator()
    engine = DraftEngine(client)
    engine.diverge("タスク", agents=["strategist"], fmt=fmt, knowledge=KNOWLEDGE)
    user = client.calls[0][1]
    assert user.index("【前提知識】") < user.index("【このタスクの草案形式】")
    assert fmt.draft_guidance in user


def test_generate_injects_knowledge_into_task() -> None:
    """単発生成（compare ベースライン等）も知識を注入する。"""
    client = _RecordingGenerator()
    engine = DraftEngine(client)
    engine.generate("タスク", knowledge=KNOWLEDGE)
    user = client.calls[0][1]
    assert user.index("タスク") < user.index("【前提知識】")
    assert KNOWLEDGE in user


def test_synthesize_with_reconciliation_propagates_knowledge() -> None:
    """synthesize_with_reconciliation は止揚・最終化の両方に知識を伝播する。"""
    client = _RecordingGenerator()
    engine = DraftEngine(client)
    engine.synthesize_with_reconciliation(
        [Draft(agent="strategist", content="草案A。")], task="タスク", knowledge=KNOWLEDGE,
    )
    users = [u for (_s, u) in client.calls]
    assert len(users) >= 2  # 止揚 + 最終化
    for u in users:
        assert "【前提知識】" in u, "止揚・最終化の全段階に知識が入る"
        assert KNOWLEDGE in u


def test_synthesize_propagates_knowledge() -> None:
    """synthesize（ラッパー）も knowledge を synthesize_with_reconciliation に伝播する。"""
    client = _RecordingGenerator()
    engine = DraftEngine(client)
    engine.synthesize(
        [Draft(agent="strategist", content="草案A。")], task="タスク", knowledge=KNOWLEDGE,
    )
    users = [u for (_s, u) in client.calls]
    assert users and all("【前提知識】" in u for u in users)


def test_elevate_propagates_knowledge() -> None:
    """elevate（diverge → synthesize の一気ラッパー）も知識を全段階に伝播する。"""
    client = _RecordingGenerator()
    engine = DraftEngine(client)
    elevated = engine.elevate("タスク", agents=["strategist"], knowledge=KNOWLEDGE)
    assert elevated
    users = [u for (_s, u) in client.calls]
    assert users
    assert all("【前提知識】" in u for u in users), "草案・止揚・最終化の全 user に知識が入る"


def test_no_knowledge_is_backward_compatible() -> None:
    """知識なし（従来挙動）は注入しない。抽出にも混ぜない。"""
    client = _RecordingGenerator()
    engine = DraftEngine(client)
    engine.diverge("タスク", agents=["strategist"])
    user = client.calls[0][1]
    assert "【前提知識】" not in user
    assert user == "タスク"  # fmt も知識もないのでタスクのまま


# ---- CLI 統合 ----


def _run_cli(argv: list[str]) -> tuple[int, str]:
    """main.main() を実行し、(exit_code, stdout+stderr) を返す（cwd を汚さない）。"""
    import contextlib
    import io

    import main

    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main.main(argv)
    return code, out.getvalue() + err.getvalue()


def test_cli_knowledge_flag_injects_and_saves(tmp_path, monkeypatch) -> None:
    """--knowledge で完走し、草案・最終化に注入・knowledge.md が保存される。"""
    import main

    gen = main.MockGenerator()
    monkeypatch.setattr(main, "MockGenerator", lambda: gen)

    code, out = _run_cli(
        ["elevate", "再生PETのスニーカーのキャッチコピー", "--mock", "--out", str(tmp_path),
         "--knowledge", KNOWLEDGE]
    )
    assert code == 0
    assert "前提知識" in out  # 保存メッセージ

    # 注入: 草案・最終化の user に知識が現れる
    draft_users = [u for (s, u, _) in gen.calls if "草案の作り方" in s]
    assert draft_users and "【前提知識】" in draft_users[0]
    finalize_users = [u for (s, u, _) in gen.calls if "最終化指示" in u]
    assert finalize_users and "【前提知識】" in finalize_users[0]

    # 保存: knowledge.md が input.md / format.md と並列（トップレベル）に出力される
    assert (tmp_path / "knowledge.md").exists()
    assert "再生PET" in (tmp_path / "knowledge.md").read_text()
    assert (tmp_path / "input.md").exists(), "input.md と並列に置かれる"


def test_cli_knowledge_file_flag_reads_and_injects(tmp_path, monkeypatch) -> None:
    """--knowledge-file でファイルの内容を読み込んで注入する。"""
    import main

    kfile = tmp_path / "materials.md"
    kfile.write_text("# 材料仕様\n\n再生PET 100%。\n", encoding="utf-8")

    gen = main.MockGenerator()
    monkeypatch.setattr(main, "MockGenerator", lambda: gen)

    code, out = _run_cli(
        ["elevate", "タスク", "--mock", "--out", str(tmp_path / "out"),
         "--knowledge-file", str(kfile)]
    )
    assert code == 0
    assert "前提知識" in out  # 保存メッセージ
    assert (tmp_path / "out" / "knowledge.md").exists()
    assert "再生PET 100%" in (tmp_path / "out" / "knowledge.md").read_text()

    draft_users = [u for (s, u, _) in gen.calls if "草案の作り方" in s]
    assert draft_users and "再生PET 100%" in draft_users[0]


def test_cli_knowledge_file_missing_fails(tmp_path) -> None:
    """存在しない --knowledge-file は FileNotFoundError で明確に失敗する。"""
    with pytest.raises(FileNotFoundError):
        _run_cli(
            ["elevate", "タスク", "--mock", "--out", str(tmp_path / "out"),
             "--knowledge-file", str(tmp_path / "nope.md")]
        )


def test_cli_ask_knowledge_prompts_interactively(tmp_path, monkeypatch) -> None:
    """--ask-knowledge は起動時に入力を求めて knowledge.md に保存する。"""
    import main

    monkeypatch.setattr("builtins.input", lambda _prompt="": "材料: 質問応答で入力。")
    gen = main.MockGenerator()
    monkeypatch.setattr(main, "MockGenerator", lambda: gen)

    code, out = _run_cli(
        ["elevate", "タスク", "--mock", "--out", str(tmp_path), "--ask-knowledge"]
    )
    assert code == 0
    assert (tmp_path / "knowledge.md").exists()
    assert "質問応答で入力" in (tmp_path / "knowledge.md").read_text()
    draft_users = [u for (s, u, _) in gen.calls if "草案の作り方" in s]
    assert draft_users and "質問応答で入力" in draft_users[0]


def test_cli_knowledge_absent_is_backward_compatible(tmp_path) -> None:
    """知識なし（従来挙動）は knowledge.md を出力しない。"""
    code, _ = _run_cli(
        ["elevate", "タスク", "--mock", "--out", str(tmp_path)]
    )
    assert code == 0
    assert not (tmp_path / "knowledge.md").exists(), "知識なしでは保存しない"
    assert (tmp_path / "input.md").exists()


def test_cli_knowledge_mutually_exclusive(tmp_path) -> None:
    """--knowledge と --knowledge-file は同時に指定できない。"""
    kfile = tmp_path / "materials.md"
    kfile.write_text("素材。", encoding="utf-8")
    # argparse の相互排他は SystemExit(2) で退出する（_run_cli では補足されない）
    with pytest.raises(SystemExit) as exc:
        _run_cli(
            ["elevate", "タスク", "--mock", "--out", str(tmp_path / "out"),
             "--knowledge", "直接", "--knowledge-file", str(kfile)]
        )
    assert exc.value.code == 2  # argparse の usage エラー


def test_cli_compare_and_improve_accept_knowledge(tmp_path, monkeypatch) -> None:
    """compare / improve にも --knowledge を渡せる（公平比較・改修ラウンド永続）。"""
    import main

    gen = main.MockGenerator()
    monkeypatch.setattr(main, "MockGenerator", lambda: gen)

    code, _ = _run_cli(
        ["compare", "タスク", "--mock", "--out", str(tmp_path / "cmp"), "--knowledge", KNOWLEDGE]
    )
    assert code == 0
    assert (tmp_path / "cmp" / "knowledge.md").exists()
    assert (tmp_path / "cmp" / "artifacts" / "elevated.md").exists()

    code, _ = _run_cli(
        ["improve", "タスク", "--mock", "--rounds", "1", "--out", str(tmp_path / "imp"),
         "--knowledge", KNOWLEDGE]
    )
    assert code == 0
    assert (tmp_path / "imp" / "knowledge.md").exists()
    # 全ラウンド（草案）で知識が入る
    draft_users = [u for (s, u, _) in gen.calls if "草案の作り方" in s]
    assert draft_users and all("【前提知識】" in u for u in draft_users)
