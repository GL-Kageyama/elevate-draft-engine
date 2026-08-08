"""Evaluation Engine の単体テスト（モッククライアント使用）。

検証対象: evaluation/evaluator.py（overall式・合格しきい値）
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
    """overall = Q×0.25 + L×0.20 + C×0.20 + V×0.25 + (1−R)×0.10（evaluator.py の compute_overall と同一）"""
    scores = {"quality": 1.0, "logic": 1.0, "creativity": 1.0, "value": 1.0, "risk": 0.0}
    assert compute_overall(scores) == pytest.approx(1.0)
    scores2 = {"quality": 0.0, "logic": 0.0, "creativity": 0.0, "value": 0.0, "risk": 1.0}
    assert compute_overall(scores2) == pytest.approx(0.0)
    # risk は反転: risk=1.0 → (1-1.0)×0.10 = 0
    scores3 = {"quality": 0.8, "logic": 0.7, "creativity": 0.9, "value": 0.85, "risk": 0.3}
    expected = 0.8 * 0.25 + 0.7 * 0.20 + 0.9 * 0.20 + 0.85 * 0.25 + (1 - 0.3) * 0.10
    assert compute_overall(scores3) == pytest.approx(expected)


def test_parse_scores_from_json_block():
    text = '解説文。\n\n```json\n{"quality": 0.7, "logic": 0.6, "creativity": 0.8, "value": 0.75, "risk": 0.4}\n```'
    scores = parse_scores(text)
    assert scores == pytest.approx({"quality": 0.7, "logic": 0.6, "creativity": 0.8, "value": 0.75, "risk": 0.4})


def test_parse_scores_regex_fallback():
    text = 'quality: 0.9 logic: 0.8 creativity: 0.7 value: 0.6 risk: 0.2'
    scores = parse_scores(text)
    assert scores == pytest.approx({"quality": 0.9, "logic": 0.8, "creativity": 0.7, "value": 0.6, "risk": 0.2})


def test_parse_scores_clamps_out_of_range():
    text = '{"quality": 1.5, "logic": -0.3, "creativity": 0.8, "value": 0.75, "risk": 0.4}'
    scores = parse_scores(text)
    assert scores["quality"] == 1.0
    assert scores["logic"] == 0.0


def test_parse_scores_invalid_raises():
    with pytest.raises(ValueError):
        parse_scores("スコアはありませんでした。")


def test_engine_passes_with_mock():
    """overall >= 0.70 → Pass。モック応答から正しく採点される。"""
    client = MockClient('{"quality": 0.9, "logic": 0.9, "creativity": 0.8, "value": 0.9, "risk": 0.1}')
    engine = EvaluationEngine(client)
    result = engine.evaluate("成果物テキスト", "タスク")
    assert result.passed is True
    assert result.overall > 0.7


def test_engine_revise_with_mock():
    client = MockClient('{"quality": 0.5, "logic": 0.5, "creativity": 0.5, "value": 0.5, "risk": 0.5}')
    engine = EvaluationEngine(client)
    result = engine.evaluate("成果物")
    assert result.passed is False
    assert engine.score_judgment(result.overall) == "Revise"


# ---- ルーブリック改訂（2026-08-08）----

def test_rubric_risk_axis_redefined():
    """Risk 軸が「リスク認識の適切さ」に再定義されていること（Step 2）。"""
    from evaluation.evaluator import RUBRIC

    # 旧定義「低いほど良い」が消えている
    assert "低いほど良い" not in RUBRIC
    # 新定義: リスクを認識し対策を提示することを高評価
    assert "リスクを特定" in RUBRIC
    assert "対策" in RUBRIC
    # 楽観的過ぎることを低評価とする記述がある
    assert "楽観的" in RUBRIC


def test_rubric_quality_rewards_honesty():
    """Quality 軸に不確実性の区別（知的誠実さ）の基準が追加されていること。"""
    from evaluation.evaluator import RUBRIC

    assert "不確実性を適切に区別" in RUBRIC
    assert "不確実なことを断定" in RUBRIC


def test_rubric_value_allows_conditional():
    """Value 軸に条件付き価値の許容が追加されていること。"""
    from evaluation.evaluator import RUBRIC

    assert "条件付き価値" in RUBRIC
