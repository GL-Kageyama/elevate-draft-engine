"""Evaluation Engine の単体テスト（モッククライアント使用）。

検証対象: evaluation/evaluator.py（overall式・合格しきい値）
5軸: diversity（多様性）/ synthesis（統合性）/ elevation（超越性）/ honesty（誠実性）/ utility（実用性）
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.evaluator import (
    EvaluationEngine,
    compute_overall,
    parse_scores,
)


class MockClient:
    """評価用Claudeのモック。決まったJSONを返す。"""

    def __init__(self, response: str):
        self.response = response
        self.calls = []

    def evaluate(self, system: str, user: str) -> str:
        self.calls.append({"system": system, "user": user})
        return self.response


def test_compute_overall_formula():
    """overall = Σ 各軸×0.20（均等重み。全軸「高いほど良い」。Risk 時代の反転は廃止）"""
    scores = {"diversity": 1.0, "synthesis": 1.0, "elevation": 1.0, "honesty": 1.0, "utility": 1.0}
    assert compute_overall(scores) == pytest.approx(1.0)
    scores2 = {"diversity": 0.0, "synthesis": 0.0, "elevation": 0.0, "honesty": 0.0, "utility": 0.0}
    assert compute_overall(scores2) == pytest.approx(0.0)
    scores3 = {"diversity": 0.8, "synthesis": 0.7, "elevation": 0.9, "honesty": 0.85, "utility": 0.75}
    expected = 0.8 * 0.20 + 0.7 * 0.20 + 0.9 * 0.20 + 0.85 * 0.20 + 0.75 * 0.20
    assert compute_overall(scores3) == pytest.approx(expected)


def test_parse_scores_from_json_block():
    text = '解説文。\n\n```json\n{"diversity": 0.7, "synthesis": 0.6, "elevation": 0.5, "honesty": 0.75, "utility": 0.7}\n```'
    scores = parse_scores(text)
    assert scores == pytest.approx({"diversity": 0.7, "synthesis": 0.6, "elevation": 0.5, "honesty": 0.75, "utility": 0.7})


def test_parse_scores_regex_fallback():
    text = 'diversity: 0.9 synthesis: 0.8 elevation: 0.7 honesty: 0.6 utility: 0.5'
    scores = parse_scores(text)
    assert scores == pytest.approx({"diversity": 0.9, "synthesis": 0.8, "elevation": 0.7, "honesty": 0.6, "utility": 0.5})


def test_parse_scores_clamps_out_of_range():
    text = '{"diversity": 1.5, "synthesis": -0.3, "elevation": 0.8, "honesty": 0.75, "utility": 0.4}'
    scores = parse_scores(text)
    assert scores["diversity"] == 1.0
    assert scores["synthesis"] == 0.0


def test_parse_scores_invalid_raises():
    with pytest.raises(ValueError):
        parse_scores("スコアはありませんでした。")


def test_engine_passes_with_mock():
    """overall >= 0.70 → Pass。モック応答から正しく採点される。"""
    client = MockClient('{"diversity": 0.8, "synthesis": 0.8, "elevation": 0.8, "honesty": 0.8, "utility": 0.8}')
    engine = EvaluationEngine(client)
    result = engine.evaluate("成果物テキスト", "タスク")
    assert result.passed is True
    assert result.overall > 0.7


def test_engine_revise_with_mock():
    client = MockClient('{"diversity": 0.5, "synthesis": 0.5, "elevation": 0.5, "honesty": 0.5, "utility": 0.5}')
    engine = EvaluationEngine(client)
    result = engine.evaluate("成果物")
    assert result.passed is False
    assert engine.score_judgment(result.overall) == "Revise"


# ---- ルーブリック改訂（2026-08-08）----

def test_rubric_policy_axes():
    """5軸がポリシー密着（多様性/統合性/超越性/誠実性/実用性）で、Risk 軸が廃止されていること。

    再調整(3): ゼロベースで5軸を再考。Risk（リスク認識）軸は「正直なリスク開示ほど評価が
    下がる」構造的バイアスのため廃止し、本エンジンのポリシー（複数の独立した視点を統合して
    単一視点を超える成果物を生む）を測る5軸に置き換えた。
    """
    from evaluation.evaluator import RUBRIC

    # 旧 Risk 軸（リスク認識）が消えている
    assert "リスク認識" not in RUBRIC
    # ポリシー密着の5軸が定義されている
    assert "多様性（視点の横断）" in RUBRIC
    assert "統合性（矛盾解決・連結）" in RUBRIC
    assert "超越性（第3の位置）" in RUBRIC
    assert "誠実性（確信と不確実の区別）" in RUBRIC
    assert "実用性（具体・実行可能）" in RUBRIC
    # ポリシー（統合エンジンの価値）を測る旨が明示されている
    assert "ポリシー" in RUBRIC


def test_rubric_synthesis_rejects_enumeration():
    """統合性軸が「併記・平均化」を不合格にする（エンジンのポリシー）こと。"""
    from evaluation.evaluator import RUBRIC

    assert "併記・羅列" in RUBRIC
    assert "断片の寄せ集め" in RUBRIC


def test_rubric_honesty_axis():
    """誠実性軸（確信と不確実の区別）が定義されていること。"""
    from evaluation.evaluator import RUBRIC

    assert "確信と不確実" in RUBRIC
    assert "不確実なことを断定" in RUBRIC


def test_rubric_honesty_allows_conditional():
    """誠実性軸は不確実な点を条件付き・前提として明示することを高評価する
    （旧 Value の「条件付き価値」の行き先）。"""
    from evaluation.evaluator import RUBRIC

    assert "条件付き" in RUBRIC


def test_rubric_good_band_is_not_mediocre():
    """0.7-0.8帯が「平凡」ではなく「確かに良い」に再定義され、0.9+に行動的卓越マーカーがあること。

    再調整(2): 「0.5=普通」と0.7-0.8=「平凡」の矛盾を解消し、評価が「無難さ」でなく
    「確かな良さ」を測るようにした。凡庸な出力を 0.7 以上にしない指示が残っていること。
    """
    from evaluation.evaluator import RUBRIC

    # 0.5 アンカーは「無難」、0.7-0.8 は「確かに良い」
    assert "0.5 を「無難」の基準" in RUBRIC
    assert "確かに良い" in RUBRIC
    # 0.9+ の卓越は行動的マーカーを持つ（凡庸な生成にはない固有の枠組み・見方の転換）
    assert "固有の枠組み" in RUBRIC
    assert "見方の転換" in RUBRIC
    # 凡庸な出力を 0.7 以上にしない指示が残っている
    assert "凡庸な出力を 0.7 以上にしない" in RUBRIC
