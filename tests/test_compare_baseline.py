"""compare の定量集計・best-of-N 帰無仮説ベースラインのテスト。

検証対象: main.py（cmd_compare の --runs / --baseline / --no-strong-claim と、
_best_of_n / _stat_summary / MockEvaluator）
モックのみで決定的に動作することを確認する。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402


# ---- _stat_summary ----

def test_stat_summary_mean_sd_n() -> None:
    """平均・標準偏差・件数が正しく集計される。"""
    s = main._stat_summary([0.8, 0.9, 0.7])
    assert "mean=0.800" in s
    assert "n=3" in s
    assert "sd=" in s


def test_stat_summary_single_value_zero_sd() -> None:
    s = main._stat_summary([0.5])
    assert "mean=0.500" in s
    assert "sd=0.000" in s


def test_stat_summary_uses_sample_variance() -> None:
    """標準偏差は標本分散（n-1）で計算される（小標本での不偏推定）。"""
    # 値: 0.6, 0.8 → mean 0.7、標本分散 (0.01+0.01)/(2-1)=0.02 → sd=0.1414
    s = main._stat_summary([0.6, 0.8])
    assert "sd=0.141" in s


# ---- 統計量（信頼区間・効果量） ----

def test_mean_confidence_interval_single_value_degenerate() -> None:
    """n=1 では平均の信頼区間が一点に潰れる（開かない）。"""
    lo, hi = main._mean_confidence_interval([0.8])
    assert lo == hi == 0.8


def test_mean_confidence_interval_brackets_mean() -> None:
    """n>1 では区間が標本平均を挟む（小標本は t 分布で広く開く）。"""
    vals = [0.8, 0.9, 0.7, 0.85, 0.75]
    lo, hi = main._mean_confidence_interval(vals)
    mean = sum(vals) / len(vals)
    assert lo < mean < hi


def test_wilson_interval_wins_all_brackets_high() -> None:
    """全勝でも 95%CI の下側は 0 でない（Wilson 区間は p=1 で潰れない）。"""
    lo, hi = main._wilson_interval(3, 3)
    assert hi == 1.0
    assert 0.0 < lo < 1.0


def test_cohens_d_computes_effect_size() -> None:
    """統合がベースラインを上回るとき正の効果量になる。"""
    d = main._cohens_d([0.7, 0.72, 0.71], [0.85, 0.87, 0.86])
    assert d > 0
    assert d > 1.0  # 明確に分離している場合は大きな効果量


# ---- _best_of_n ----

def test_best_of_n_selects_highest_overall_draft() -> None:
    """全草案を評価し、最高 overall の草案とそのスコアを返す。"""
    evaluator = main.MockEvaluator()
    drafts = [
        main.Draft(agent="designer", content="これはエージェント「designer」からのモック草案である。designerらしい観点で描かれている。"),
        main.Draft(agent="humanist", content="これはエージェント「humanist」からのモック草案である。humanistらしい観点で描かれている。"),
        main.Draft(agent="strategist", content="これはエージェント「strategist」からのモック草案である。strategistらしい観点で描かれている。"),
    ]
    best, score = main._best_of_n(evaluator, drafts, "タスク")
    # MockEvaluator: designer 0.601 / strategist 0.682 / humanist 0.817 → humanist が最良
    assert best.agent == "humanist"
    assert score > 0.8


# ---- MockEvaluator（best-of-N が意味を持つため名前別スコア） ----

def test_mock_evaluator_scores_drafts_by_name() -> None:
    """草案はエージェント名に応じて決定的に異なるスコアになる（best が選べる）。"""
    ev = main.MockEvaluator()
    # MockEvaluator.evaluate(system, user) の system に成果物テキストが渡る
    low = ev.evaluate("これはエージェント「designer」からのモック草案である。designerらしい観点で描かれている。", "タスク")
    high = ev.evaluate("これはエージェント「humanist」からのモック草案である。humanistらしい観点で描かれている。", "タスク")
    assert low.overall != high.overall
    assert low.overall < high.overall


def test_mock_evaluator_constant_for_non_draft() -> None:
    """草案以外（素の生成・統合成果物）は一定のスコア（0.6）になる。

    ルーブリック再調整（2026-08-08）で「普通」は 0.6（旧 0.8 は天井で向上が可視化できない）。
    ポリシー密着5軸（2026-08-08 再調整(3)）の下では全軸が base のため overall = base。
    """
    ev = main.MockEvaluator()
    a = ev.evaluate("普通の成果物テキスト。", "タスク")
    b = ev.evaluate("別の普通の成果物テキスト。", "タスク")
    assert a.overall == b.overall
    assert a.overall == pytest.approx(0.6)  # 均等重み0.20×5軸のため overall = base（反転なし）


# ---- MockGenerator（--no-strong-claim でもエージェント草案を識別） ----

def test_mock_generator_identifies_agents_after_strip() -> None:
    """枠を剥がしたプロンプトでも「草案の作り方」とペルソナ名で識別できる。"""
    from elevate.engine import _strip_strong_claim, load_agents

    gen = main.MockGenerator()
    full_prompt = load_agents()["humanist"]
    stripped = _strip_strong_claim(full_prompt)
    out = gen.generate(stripped, "タスク")
    assert "エージェント「humanist」" in out


# ---- cmd_compare（統合動作: --runs と --baseline） ----

def _run_compare(argv: list[str], *, cwd: Path | None = None) -> tuple[int, str]:
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


def test_compare_single_runs_no_summary(tmp_path) -> None:
    """既定（--runs 1）は統計集計セクションを出さない。"""
    code, out = _run_compare(["compare", "タスク", "--mock", "--evaluate"], cwd=tmp_path)
    assert code == 0
    assert "=== 比較集計 ===" not in out
    assert "[素の生成（単発）]" in out
    assert "[ELEVATE]" in out


def test_compare_runs_aggregates_statistics(tmp_path) -> None:
    """--runs N で統計集計（平均・勝率）が出力される。"""
    code, out = _run_compare(
        ["compare", "タスク", "--mock", "--evaluate", "--runs", "3"], cwd=tmp_path
    )
    assert code == 0
    assert "=== 比較集計 ===" in out
    assert "mean=" in out
    assert "勝率" in out


def test_compare_best_of_n_requires_evaluate(tmp_path) -> None:
    """best-of-n は草案を評価するため --evaluate が必須（なければ明示的エラー）。"""
    code, out = _run_compare(["compare", "タスク", "--mock", "--baseline", "best-of-n"], cwd=tmp_path)
    assert code == 1
    assert "best-of-n" in out


def test_compare_best_of_n_reports_best_draft(tmp_path) -> None:
    """best-of-n ベースラインは最良草案を選択して比較する。"""
    code, out = _run_compare(
        ["compare", "タスク", "--mock", "--evaluate", "--baseline", "best-of-n", "--verbose"],
        cwd=tmp_path,
    )
    assert code == 0
    assert "最良草案: visionary" in out  # 全8エージェントで MockEvaluator の最良は visionary（0.844）
    assert "ベースライン（best-of-n）" in out
    assert "ELEVATE" in out


def test_compare_no_strong_claim_combines_with_baseline(tmp_path) -> None:
    """--no-strong-claim と --baseline best-of-n / --runs を組み合わせて動作する。"""
    code, out = _run_compare(
        ["compare", "タスク", "--mock", "--evaluate", "--no-strong-claim",
         "--baseline", "best-of-n", "--runs", "2"],
        cwd=tmp_path,
    )
    assert code == 0
    assert "=== 比較集計 ===" in out
    assert "勝率" in out


def test_compare_without_out_saves_to_outputs_task_dir(tmp_path) -> None:
    """--out 未指定でも outputs/{タスク名}/ にデフォルト保存される（全成果物・草案は逐次保存）。"""
    code, _ = _run_compare(
        ["compare", "タスク", "--mock", "--evaluate"], cwd=tmp_path
    )
    assert code == 0
    out_dir = tmp_path / "outputs" / "タスク"
    assert (out_dir / "input.md").exists()
    assert (out_dir / "elevated.md").exists()
    assert (out_dir / "raw.md").exists()
    assert (out_dir / "reconciliation.md").exists()
    assert list(out_dir.glob("draft_*.md")), "デフォルトで草案が保存されていない"


# ---- per-run フォルダ分離（--runs > 1 の履歴保存） ----

def test_compare_runs_saves_each_run_in_own_folder(tmp_path) -> None:
    """--runs > 1 かつ --out 指定時、各 run の成果物・評価記録が run_NN/ に分離保存される。"""
    code, _ = _run_compare(
        ["compare", "タスク", "--mock", "--evaluate", "--runs", "2", "--out", str(tmp_path)]
    )
    assert code == 0
    # 共有物: 入力と統計集計は --out 直下
    assert (tmp_path / "input.md").exists()
    assert (tmp_path / "measurement.md").exists()
    assert "勝率" in (tmp_path / "measurement.md").read_text()
    for n in ("01", "02"):
        run_dir = tmp_path / f"run_{n}"
        assert (run_dir / "elevated.md").exists(), f"{run_dir}/elevated.md が無い"
        assert (run_dir / "raw.md").exists(), f"{run_dir}/raw.md が無い"
        assert (run_dir / "reconciliation.md").exists(), f"{run_dir}/reconciliation.md が無い"
        assert (run_dir / "evaluation_baseline.md").exists(), f"{run_dir}/evaluation_baseline.md が無い"
        assert (run_dir / "evaluation_elevated.md").exists(), f"{run_dir}/evaluation_elevated.md が無い"
        assert list(run_dir.glob("draft_*.md")), f"{run_dir} に草案が保存されていない"


def test_compare_single_run_out_flat(tmp_path) -> None:
    """--runs 1 は従来どおり --out 直下へ保存（run_NN/ を作らない）。"""
    code, _ = _run_compare(
        ["compare", "タスク", "--mock", "--evaluate", "--runs", "1", "--out", str(tmp_path)]
    )
    assert code == 0
    assert (tmp_path / "elevated.md").exists()
    assert not list(tmp_path.glob("run_*")), "--runs 1 で run_* フォルダを作らない"


# ---- 統計報告の強化（信頼区間・効果量・保存率） ----

def test_compare_runs_reports_confidence_intervals(tmp_path) -> None:
    """--runs N の集計に Wilson 勝率CI・差のtCI・Cohen's d が含まれる。"""
    code, out = _run_compare(
        ["compare", "タスク", "--mock", "--evaluate", "--runs", "3"], cwd=tmp_path
    )
    assert code == 0
    assert "95%CI" in out
    assert "Cohen's d" in out
    assert "Wilson" in out


def test_compare_measurement_md_includes_cis(tmp_path) -> None:
    """measurement.md に信頼区間・効果量が保存される。"""
    code, _ = _run_compare(
        ["compare", "タスク", "--mock", "--evaluate", "--runs", "3", "--out", str(tmp_path)]
    )
    assert code == 0
    text = (tmp_path / "measurement.md").read_text()
    assert "勝率 95%CI（Wilson）" in text
    assert "差の 95%CI（t, 両側）" in text
    assert "効果量（Cohen's d）" in text
    assert "具体性保存率" in text  # --evaluate で自動計算される


# ---- 温度近似の誤差定量（calibrate） ----

def test_calibrate_mock_writes_calibration_md(tmp_path) -> None:
    """calibrate はモックで動作し、calibration.md を保存する。"""
    code, out = _run_compare(
        ["calibrate", "タスク", "--mock", "--runs", "3", "--out", str(tmp_path)]
    )
    assert code == 0
    assert "完了（n=3）" in out
    path = tmp_path / "calibration.md"
    assert path.exists()
    text = path.read_text()
    assert "温度近似の誤差定量" in text
    assert "| sdk |" in text
    assert "| claude-code |" in text
    assert "type-token比" in text


def test_calibrate_engines_restriction(tmp_path) -> None:
    """--engines で比較するエンジンを指定できる。"""
    code, out = _run_compare(
        ["calibrate", "タスク", "--mock", "--runs", "2", "--engines", "sdk", "--out", str(tmp_path)]
    )
    assert code == 0
    text = (tmp_path / "calibration.md").read_text()
    assert "| claude-code |" not in text  # テーブル行に含まれない
    assert "| sdk |" in text


def test_text_features_measures_ttr_and_headings() -> None:
    """_text_features は長さ・type-token比・見出し数を返す。"""
    f = main._text_features("# 見出し\n\nこれはテスト文です。これはテスト文です。")
    assert f["length"] > 0
    assert f["heading_count"] == 1
    assert 0.0 < f["type_token_ratio"] <= 1.0
