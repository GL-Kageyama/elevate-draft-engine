"""improve（昇華版 → 改修の草案(複数) → 昇華 の反復改善ループ）のテスト。

検証対象: main.py（cmd_improve / _revision_task / _save_progress）
- ループ配線: round 2 以降は前回の昇華版を改修対象に改修草案を作り、それを昇華する
- round_NN/ ごとの成果物保存
- --evaluate の頭打ち早期停止。mock はポリシー密着5軸（2026-08-08 再調整(3)）後、
  素の生成相当（round 1）0.600 → 昇華版 0.720 と向上が可視化され、改修度3で頭打ち → 決定的に停止する
モックのみで決定的に動作することを確認する。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402


def _run_improve(argv: list[str], *, cwd: Path | None = None) -> tuple[int, str]:
    """main.main() を実行し、(exit_code, stdout+stderr の結合) を返す。

    cwd を渡すと、そのディレクトリで実行する（デフォルト保存先 outputs/ が実プロジェクトを
    汚さないように、--out 未指定のテストは tmp_path を渡す）。
    """
    import contextlib
    import io
    import os

    old = os.getcwd()
    if cwd is not None:
        os.chdir(cwd)
    try:
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main.main(argv)
        return code, out.getvalue() + err.getvalue()
    finally:
        os.chdir(old)


# ---- _revision_task（改修草案のタスク組み立て） ----

def test_revision_task_embeds_previous_elevated() -> None:
    """改修草案タスクに前回の昇華版と改修指示が埋め込まれる。"""
    task = "健康AIの企画"
    elevated = "これは前回の昇華版の中身である。独自の核を持つ。"
    rev = main._revision_task(task, elevated)
    assert task in rev
    assert elevated in rev
    assert "改修対象: 前回の昇華版" in rev
    assert "改修した草案" in rev


def test_revision_task_keeps_original_good_parts_instructed() -> None:
    """改修指示は「良い部分を残し、弱点を補強」することを明示する。"""
    rev = main._revision_task("タスク", "前回の昇華版")
    assert "良い部分" in rev
    assert "弱点" in rev


# ---- ループ配線（round 2 以降の相続） ----

def test_improve_second_round_inherits_previous_elevated(tmp_path, monkeypatch) -> None:
    """round 2 の改修草案タスクに round 1 の昇華版が埋め込まれる。

    MockGenerator の草案はタスク非依存の固定文を返すため、生成物ではなく
    生成コールの user プロンプト（改修対象タスク）を検査する。
    """
    gen = main.MockGenerator()
    monkeypatch.setattr(main, "MockGenerator", lambda: gen)

    code, _ = _run_improve(
        ["improve", "タスク", "--mock", "--rounds", "2", "--out", str(tmp_path)]
    )
    assert code == 0

    elevated_1 = (tmp_path / "round_01" / "elevated.md").read_text()
    assert elevated_1.strip()
    # round 2 の改修草案コールに「改修対象: 前回の昇華版」と round 1 の昇華版が入る
    draft_users = [user for (system, user, _) in gen.calls if "草案の作り方" in system]
    assert any("改修対象: 前回の昇華版" in u for u in draft_users)
    assert any(elevated_1.strip() in u for u in draft_users)


def test_improve_first_round_uses_original_task(tmp_path, monkeypatch) -> None:
    """round 1 は改修対象を持たない（オリジナルタスクから発散する）。"""
    gen = main.MockGenerator()
    monkeypatch.setattr(main, "MockGenerator", lambda: gen)

    code, _ = _run_improve(
        ["improve", "オリジナルのタスク", "--mock", "--rounds", "2", "--out", str(tmp_path)]
    )
    assert code == 0
    draft_users = [user for (system, user, _) in gen.calls if "草案の作り方" in system]
    # 前半（round 1）の草案コールには改修対象マーカーが無い
    assert not any("改修対象: 前回の昇華版" in u for u in draft_users[:8])
    # 後半（round 2）の草案コールにはある
    assert any("改修対象: 前回の昇華版" in u for u in draft_users[8:])


# ---- round ごとの成果物保存 ----

def test_improve_rounds_save_each_round(tmp_path) -> None:
    """rounds>1 なら round_NN/ ごとに発散・推理・昇華・進捗が保存される。"""
    code, _ = _run_improve(
        ["improve", "タスク", "--mock", "--rounds", "3", "--out", str(tmp_path)]
    )
    assert code == 0
    for n in ("01", "02", "03"):
        rd = tmp_path / f"round_{n}"
        assert rd.is_dir(), f"{rd} が存在しない"
        assert (rd / "elevated.md").exists()
        assert (rd / "reconciliation.md").exists()
        assert any(rd.glob("draft_*.md")), f"{rd} に草案がない"
    assert (tmp_path / "progress.md").exists()


def test_improve_single_round_flat(tmp_path) -> None:
    """rounds=1 なら round_NN/ を作らず平置きで保存する（compare --runs 1 と同様）。"""
    code, _ = _run_improve(
        ["improve", "タスク", "--mock", "--rounds", "1", "--out", str(tmp_path)]
    )
    assert code == 0
    assert (tmp_path / "elevated.md").exists()
    assert not list(tmp_path.glob("round_*")), "rounds=1 で round_NN/ を作らない"


def test_improve_progress_marks_loop(tmp_path) -> None:
    """progress.md にループの説明（改修草案 → 昇華）が記録される。"""
    code, _ = _run_improve(
        ["improve", "タスク", "--mock", "--rounds", "2", "--out", str(tmp_path)]
    )
    assert code == 0
    text = (tmp_path / "progress.md").read_text()
    assert "round 2 以降" in text
    assert "改修の草案" in text
    assert "相続" in text


# ---- 頭打ち早期停止（--evaluate / --min-improve） ----

def test_improve_visible_improvement_then_plateau(tmp_path) -> None:
    """mock で素の生成相当（round 1）0.600 → round 2 昇華版 0.720 と向上が可視化され、頭打ちで早期停止する。

    ポリシー密着5軸（2026-08-08 再調整(3)）の下でも、素の生成相当は天井（0.79）でなく
    0.600 になり、昇華版を磨くごとに overall が上昇する（向上が可視化できる）。
    改修度3で 0.720 に頭打ち → 停止。
    """
    code, out = _run_improve(
        [
            "improve", "タスク", "--mock", "--rounds", "5",
            "--evaluate", "--min-improve", "0.01", "--out", str(tmp_path),
        ]
    )
    assert code == 0
    text = (tmp_path / "progress.md").read_text()
    assert "overall" in text  # 評価ありの進捗は overall 列を持つ
    assert "0.600" in text  # 素の生成相当（round 1）は天井でない（向上の余地）
    assert "0.720" in text  # round 2 の昇華版で Pass（0.720）に上昇
    assert "+0.120" in text  # 前回からの改善が数値で可視化される
    assert "頭打ち" in out
    assert (tmp_path / "round_03").exists(), "頭打ちラウンドは保存される"
    assert not (tmp_path / "round_04").exists(), "改善が頭打ちなら round 4 を作らない"


def test_improve_no_early_stop_without_evaluate(tmp_path) -> None:
    """--evaluate なしなら頭打ち停止しない（全ラウンド実行）。"""
    code, out = _run_improve(
        ["improve", "タスク", "--mock", "--rounds", "3", "--out", str(tmp_path)]
    )
    assert code == 0
    assert "頭打ち" not in out
    assert (tmp_path / "round_03").exists()
