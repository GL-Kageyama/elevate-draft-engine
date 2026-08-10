"""check_matrix_progress.py の多言語ラベル対応と走査範囲の回帰テスト。

2026-08-11 の行列再登録（en/ja/zh の morning-routine ドメイン統合）に伴い、
measurement.md のラベルが言語別（ja/en/zh）で書かれてもパースできること、
examples/i18n/ 配下も走査対象になることを保証する。
"""

import sys
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
sys.path.insert(0, str(EXAMPLES_DIR))

import check_matrix_progress as mcp  # noqa: E402


def _write_measurement(base: Path, rel: str, lang: str, mean_diff: float, wins: int, runs: int) -> Path:
    """指定言語のラベルで measurement.md を書く（_save_measurement 相当の形式）。"""
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if lang == "ja":
        diff, win = "差（ELEVATE−ベースライン）", "勝率（ELEVATE > ベースライン）"
    elif lang == "en":
        diff, win = "Difference (ELEVATE − baseline)", "Win rate (ELEVATE > baseline)"
    else:
        diff, win = "差值（ELEVATE−基线）", "胜率（ELEVATE > 基线）"
    path.write_text(
        f"# 比較計測（--runs {runs}）\n\n"
        f"- {diff}: mean={mean_diff:+.3f} sd=0.000（n={runs}）\n"
        f"- {win}: {wins}/{runs} = {wins / runs:.1%}\n"
    )
    return path


def test_parse_measurement_multilingual(tmp_path) -> None:
    """ja/en/zh のラベルで書かれた measurement.md をパースできる。"""
    cases = [
        ("a/measurement.md", "ja", +0.241, 1, 1),
        ("b/measurement.md", "en", +0.247, 1, 1),
        ("c/measurement.md", "zh", +0.305, 1, 1),
    ]
    for rel, lang, d, w, r in cases:
        _write_measurement(tmp_path, rel, lang, d, w, r)
    for rel, lang, d, w, r in cases:
        row = mcp._parse_measurement(tmp_path / rel)
        assert row is not None, f"{lang} のラベルをパースできない: {rel}"
        assert row["mean_diff"] == pytest.approx(d)
        assert row["wins"] == w
        assert row["runs"] == r


def test_collect_scans_top_level_and_i18n(tmp_path, monkeypatch) -> None:
    """collect は examples/*/ と examples/i18n/*/ の両方を走査する。"""
    _write_measurement(tmp_path, "ledger-2agents/measurement.md", "ja", -0.1, 0, 1)
    _write_measurement(tmp_path, "i18n/morning-compare-en/measurement.md", "en", +0.2, 1, 1)
    _write_measurement(tmp_path, "i18n/morning-compare-zh/measurement.md", "zh", +0.3, 1, 1)
    monkeypatch.setattr(mcp, "EXAMPLES", tmp_path)
    rows = mcp.collect()
    domains = {r["domain"] for r in rows}
    assert domains == {"ledger-2agents", "morning-compare-en", "morning-compare-zh"}


def test_decide_continues_on_winning_domains() -> None:
    """全ドメインで ELEVATE が勝っているなら継続（打ち切りにならない）。"""
    rows = [
        {"domain": "ja", "mean_diff": +0.241, "wins": 1, "runs": 1},
        {"domain": "en", "mean_diff": +0.247, "wins": 1, "runs": 1},
        {"domain": "zh", "mean_diff": +0.305, "wins": 1, "runs": 1},
    ]
    s = mcp.decide(rows)
    assert s["win_rate"] == pytest.approx(1.0)
    assert s["mean_diff"] == pytest.approx(+0.264, abs=0.001)
    assert s["stop"] is False
    assert "継続" in s["reason"]
