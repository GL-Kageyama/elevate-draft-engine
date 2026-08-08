"""render_comparison.py のテスト。

compare 出力（raw.md / elevated.md / measurement.md / run_NN/）から
「素AI生成 vs 統合版」の比較ドキュメントを生成する機能を検証する。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import render_comparison  # noqa: E402


def _make_flat(out: Path, task: str = "サンプルタスク") -> Path:
    """--runs 1 の比較出力（平置き）を再現する。"""
    out.mkdir(parents=True, exist_ok=True)
    (out / "input.md").write_text(f"# タスク\n\n{task}\n")
    (out / "raw.md").write_text("素AI生成の出力です。")
    (out / "elevated.md").write_text("統合版の出力です。")
    return out


def _make_runs(out: Path) -> Path:
    """--runs>1 の比較出力（run_NN/ サブフォルダ）を再現する。"""
    out.mkdir(parents=True, exist_ok=True)
    (out / "input.md").write_text("# タスク\n\n複数runのタスク\n")
    (out / "measurement.md").write_text(
        "# 比較計測（--runs 2）\n\n- 勝率（ELEVATE > ベースライン）: 1/2 = 50.0%\n"
        "  - 勝率 95%CI（Wilson）: 9.5%〜90.5%\n"
        "  - 効果量（Cohen's d）: +1.50\n"
    )
    for n in ("01", "02"):
        run = out / f"run_{n}"
        run.mkdir(parents=True, exist_ok=True)
        (run / "raw.md").write_text(f"run{n} の素AI生成。")
        (run / "elevated.md").write_text(f"run{n} の統合版。")
        (run / "evaluation_baseline.md").write_text(f"baseline overall=0.7{n}（Pass）")
        (run / "evaluation_elevated.md").write_text(f"elevated overall=0.8{n}（Pass）")
    return out


def test_find_runs_flat_dir_returns_itself(tmp_path) -> None:
    out = _make_flat(tmp_path)
    assert render_comparison._find_runs(out) == [out]


def test_find_runs_sorted_subdirs(tmp_path) -> None:
    out = _make_runs(tmp_path)
    runs = render_comparison._find_runs(out)
    assert [r.name for r in runs] == ["run_01", "run_02"]


def test_render_flat_includes_both_texts(tmp_path) -> None:
    out = _make_flat(tmp_path)
    md = render_comparison.render(out)
    assert "サンプルタスク" in md
    assert "素AI生成" in md and "素AI生成の出力です。" in md
    assert "統合版" in md and "統合版の出力です。" in md


def test_render_runs_includes_measurement_and_each_run(tmp_path) -> None:
    out = _make_runs(tmp_path)
    md = render_comparison.render(out)
    assert "run 1" in md and "run 2" in md
    assert "run01 の素AI生成。" in md and "run02 の素AI生成。" in md
    assert "勝率 95%CI（Wilson）" in md
    assert "評価" in md  # evaluation_*.md が読み込まれる


def test_render_missing_files_graceful(tmp_path) -> None:
    """raw/elevated が無い run ディレクトリでも落ちない。"""
    out = tmp_path / "empty"
    out.mkdir()
    (out / "input.md").write_text("# タスク\n\n空のディレクトリ\n")
    md = render_comparison.render(out)
    assert "空のディレクトリ" in md
    # 全成果物が無い run のブロックは生成されない（クラッシュしない）


def test_html_output_wraps_both_columns(tmp_path) -> None:
    out = _make_flat(tmp_path)
    md = render_comparison.render(out)
    html = render_comparison._html_of(md)
    assert "素AI生成" in html and "統合版" in html
    assert "flex" in html  # 横並び表示
