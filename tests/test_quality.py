"""品質評価（定番さ・独自性）の単体テスト（モッククライアント使用）。

検証対象: evaluation/quality.py（新奇度・独自性・意外性）と main.py の統合。
品質評価は evaluation/evaluator.py の EvaluationEngine に統合され、
overall = 5軸overall × (QUALITY_ALPHA + (1−QUALITY_ALPHA) × 品質スコア) で算出される。
品質評価を渡さない従来の EvaluationEngine（5軸のみ）は後方互換。

全観点「高いほど良い」で統一しており、評価者もそのまま測る（反転する二段構えは
取らない。用語も新奇度で一貫する）。
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.quality import (
    QualityEvaluator,
    QualityResult,
    _clamp,
    _extract_json,
    format_quality_line,
)


class MockClient:
    """評価用Claudeのモック。決まったJSONを返す。"""

    def __init__(self, response: str):
        self.response = response
        self.calls = []

    def evaluate(self, system: str, user: str) -> str:
        self.calls.append({"system": system, "user": user})
        return self.response


# ---- QualityEvaluator 単体 ----

def test_extract_json_last_block_wins():
    # D2: 品質評価JSONは英語キー（novelty / originality / surprise / rationale）に一本化
    text = '解説文。\n{"novelty": 0.2, "originality": 0.9, "surprise": 0.8, "rationale": "独自"}'
    assert _extract_json(text) == {"novelty": 0.2, "originality": 0.9, "surprise": 0.8, "rationale": "独自"}


def test_all_quality_high_is_good():
    """全観点「高いほど良い」。評価者が新奇度を直接測り、反転はしない。"""
    client = MockClient(
        '{"novelty": 0.8, "originality": 0.9, "surprise": 0.7, "rationale": ""}'
    )
    result = QualityEvaluator(client).evaluate("a", "t")
    assert result.novelty == pytest.approx(0.8)   # 新奇度はそのまま（高いほど良い）
    assert result.originality == pytest.approx(0.9)
    assert result.surprise == pytest.approx(0.7)


def test_quality_average():
    """average = (新奇度+独自性+意外性)/3。overall の掛け算係数の元。"""
    generic = QualityResult(novelty=0.2, originality=0.3, surprise=0.1, rationale="")
    assert generic.average == pytest.approx(0.2)
    original = QualityResult(novelty=0.7, originality=0.9, surprise=0.8, rationale="")
    assert original.average == pytest.approx(0.8)


def test_extract_json_empty_when_missing():
    assert _extract_json("説明のみ。スコアなし。") == {}


def test_clamp_out_of_range():
    assert _clamp(1.5) == 1.0
    assert _clamp(-0.3) == 0.0
    assert _clamp(0.7) == 0.7


def test_evaluate_parses_quality_and_injects_rubric():
    client = MockClient(
        '{"novelty": 0.2, "originality": 0.3, "surprise": 0.1, "rationale": "定番レパートリーに収まる"}'
    )
    ev = QualityEvaluator(client)
    result = ev.evaluate("成果物テキスト", "タスク文")
    assert result.novelty == pytest.approx(0.2)
    assert result.originality == pytest.approx(0.3)
    assert result.surprise == pytest.approx(0.1)
    assert "定番" in result.rationale
    # ルーブリックはシステムプロンプトに注入される（全観点高いほど良いを直接測らせる）
    assert "新奇度" in client.calls[0]["system"]
    assert "独自性" in client.calls[0]["system"]
    # タスクと成果物はユーザープロンプトに渡される
    assert "タスク文" in client.calls[0]["user"]
    assert "成果物テキスト" in client.calls[0]["user"]


def test_evaluate_clamps_score():
    client = MockClient(
        '{"novelty": 1.5, "originality": -0.2, "surprise": 0.7, "rationale": ""}'
    )
    result = QualityEvaluator(client).evaluate("a", "t")
    # 新奇度 1.5 → クランプ 1.0、独自性 -0.2 → 0.0
    assert result.novelty == 1.0
    assert result.originality == 0.0


def test_evaluate_raises_on_unparseable():
    """崩れた評価者JSONは再生成し、それでも失敗したら ValueError（再生成方針）。"""
    ev = QualityEvaluator(MockClient("スコアなしの応答"))
    with pytest.raises(ValueError):
        ev.evaluate("a", "t")


def test_is_generic_detects_generic_answer():
    # 新奇度が低く独自性も低い → 定番回答
    generic = QualityResult(novelty=0.2, originality=0.3, surprise=0.1, rationale="")
    assert generic.is_generic
    original = QualityResult(novelty=0.8, originality=0.9, surprise=0.8, rationale="")
    assert not original.is_generic
    # 新奇度が 0.3 を超えるなら定番と見なさない（境界）
    borderline = QualityResult(novelty=0.4, originality=0.3, surprise=0.1, rationale="")
    assert not borderline.is_generic
    # 独自性が高ければ新奇度が低くても定番と見なさない（境界）
    hybrid = QualityResult(novelty=0.2, originality=0.6, surprise=0.4, rationale="")
    assert not hybrid.is_generic


def test_format_quality_line_flags_generic():
    line = format_quality_line(QualityResult(0.2, 0.3, 0.1, ""))
    assert "新奇度=0.20" in line
    assert "独自性=0.30" in line
    assert "⚠定番" in line
    plain = format_quality_line(QualityResult(0.8, 0.9, 0.8, ""))
    assert "⚠定番" not in plain


# ---- EvaluationEngine 統合（overall = 5軸 × 掛け算） ----

_FIVE_AXIS = '{"diversity": 0.7, "synthesis": 0.7, "elevation": 0.7, "honesty": 0.7, "utility": 0.7}'


def _dispatch_client(quality_response: str) -> MockClient:
    """5軸評価（system に RUBRIC）と品質評価（system に「新奇度」）を振り分けるクライアント。"""

    class Dispatch(MockClient):
        def __init__(self):
            super().__init__("")
            self.quality_response = quality_response

        def evaluate(self, system, user):
            self.calls.append({"system": system, "user": user})
            return _FIVE_AXIS if "新奇度" not in system else self.quality_response

    return Dispatch()


def test_engine_overall_multiplication():
    """品質評価が統合されると overall = 5軸overall × (α + (1−α)×品質スコア)。"""
    from evaluation.evaluator import QUALITY_ALPHA, EvaluationEngine

    client = _dispatch_client('{"novelty": 0.8, "originality": 0.8, "surprise": 0.8, "rationale": "独自"}')
    engine = EvaluationEngine(client, quality_evaluator=QualityEvaluator(client))
    result = engine.evaluate("成果物", "タスク")
    q_avg = (0.8 + 0.8 + 0.8) / 3.0
    expected = 0.7 * (QUALITY_ALPHA + (1.0 - QUALITY_ALPHA) * q_avg)
    assert result.overall == pytest.approx(expected)
    assert result.quality is not None
    assert result.quality.average == pytest.approx(q_avg)


def test_engine_without_quality_keeps_five_axis():
    """quality_evaluator なしなら従来どおり5軸のみ（後方互換）。"""
    from evaluation.evaluator import EvaluationEngine

    client = MockClient(_FIVE_AXIS)
    engine = EvaluationEngine(client)
    result = engine.evaluate("成果物", "タスク")
    assert result.overall == pytest.approx(0.7)
    assert result.quality is None


def test_engine_generic_answer_punished():
    """定番回答（品質スコア低）は overall が大きく下がり、独自回答は下がらない（掛け算の狙い）。"""
    from evaluation.evaluator import EvaluationEngine

    generic_client = _dispatch_client('{"novelty": 0.2, "originality": 0.3, "surprise": 0.1, "rationale": "定番"}')
    generic = EvaluationEngine(
        generic_client, quality_evaluator=QualityEvaluator(generic_client)
    ).evaluate("成果物", "タスク").overall

    original_client = _dispatch_client('{"novelty": 0.8, "originality": 0.9, "surprise": 0.8, "rationale": "独自"}')
    original = EvaluationEngine(
        original_client, quality_evaluator=QualityEvaluator(original_client)
    ).evaluate("成果物", "タスク").overall

    assert generic < 0.7       # 5軸 0.7 から掛け算で下がる（定番は ×0.40 相当）
    assert original > generic  # 定番回答は品質評価で大きく減点される
    # 実測方針（素の生成 0.288 vs 昇華 0.604、差 +0.316）と同じ方向になる
    assert original - generic > 0.3


# ---- main.py 統合（_evaluate_and_report） ----

def _mock_evaluator_with_quality(quality):
    class MockEvaluator:
        def evaluate(self, artifact, task):
            return SimpleNamespace(
                overall=0.75,
                scores={"diversity": 0.8, "synthesis": 0.7, "elevation": 0.6,
                        "honesty": 0.8, "utility": 0.7},
                rationale="",
                quality=quality,
            )

        def score_judgment(self, overall):
            return "普通"

    return MockEvaluator()


def test_evaluate_and_report_includes_quality(tmp_path, capsys):
    """main._evaluate_and_report が result.quality を表示・保存する。"""
    from main import _evaluate_and_report

    evaluator = _mock_evaluator_with_quality(
        QualityResult(0.2, 0.3, 0.1, "定番レパートリーに収まる")
    )
    result = _evaluate_and_report(
        "TEST", "artifact", "task", evaluator,
        save_to=tmp_path / "eval.md",
    )
    assert result.overall == pytest.approx(0.75)
    out = capsys.readouterr().out
    assert "品質評価: 新奇度=0.20" in out
    saved = (tmp_path / "eval.md").read_text(encoding="utf-8")
    assert "品質評価" in saved
    assert "新奇度: 0.20" in saved


def test_evaluate_and_report_without_quality_skips(tmp_path, capsys):
    """quality=None なら従来どおり5軸のみ（後方互換）。"""
    from main import _evaluate_and_report

    evaluator = _mock_evaluator_with_quality(None)
    _evaluate_and_report("TEST", "artifact", "task", evaluator,
                         save_to=tmp_path / "eval.md")
    out = capsys.readouterr().out
    assert "新奇度" not in out
    saved = (tmp_path / "eval.md").read_text(encoding="utf-8")
    assert "品質評価" not in saved
