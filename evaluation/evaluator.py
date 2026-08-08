"""Evaluation Engine — 評価5軸による採点。

数値定義（重み・ルーブリック・overall式）は本ファイル内の DEFAULT_WEIGHTS /
RUBRIC / compute_overall() に集約する。

評価者は**独立評価系統**（生成とは別モデル）を使う。盲検化のため評価プロンプトに
条件ラベルは渡さない（ブラインド化は呼び出し側の責務）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

# 評価5軸の重み
DEFAULT_WEIGHTS: dict[str, float] = {
    "quality": 0.25,
    "logic": 0.20,
    "creativity": 0.20,
    "value": 0.25,
    "risk": 0.10,
}

# 評価スコア抽出の再生成リトライ最大回数（崩れたら再生成）
MAX_EVALUATION_RETRIES = 3

# 採点ルーブリック（行動的定義）を評価プロンプトに埋め込む
# Risk 軸は「リスク認識の適切さ」として定義する。
# 「正直なリスク開示ほど高リスク評価 → overall が下がる」構造的バイアスが
# 確認されたため、軸の方向を修正した。
RUBRIC = """各軸を0.0〜1.0で採点する。Risk は「リスクの認識と対処が適切か」を測る。

Quality（完成度）: 0.8-1.0=明確・一貫・使用可能・不確実性を適切に区別 / 0.5-0.7=構造はあるが欠落 / 0.0-0.4=不明瞭・不確実なことを断定
Logic（論理性）: 0.8-1.0=矛盾なし・根拠あり / 0.5-0.7=根拠不足・飛躍 / 0.0-0.4=矛盾
Creativity（新規性）: 0.8-1.0=既存と明確に異なる / 0.5-0.7=組み合わせだが新観点 / 0.0-0.4=焼き直し
Value（価値）: 0.8-1.0=必要性・影響力・継続性が高い・条件付き価値が現実的 / 0.5-0.7=必要だが不確か / 0.0-0.4=確認できない
Risk（リスク認識）: 0.8-1.0=主要リスクを特定し具体的対策を提示 / 0.5-0.7=主要リスクを特定するが対策が不十分 / 0.0-0.4=リスクの特定が不十分・楽観的過ぎる

最終行にJSON形式でスコアを出力すること。例:
{"quality": 0.7, "logic": 0.6, "creativity": 0.8, "value": 0.75, "risk": 0.4}"""


@dataclass
class EvaluationResult:
    """評価結果。"""

    scores: dict[str, float]  # quality, logic, creativity, value, risk (0-1)
    overall: float
    pass_threshold: float = 0.70
    rationale: str = ""
    raw: str = ""

    @property
    def passed(self) -> bool:
        return self.overall >= self.pass_threshold


def compute_overall(scores: dict[str, float], weights: dict[str, float] | None = None) -> float:
    """overall スコア算出。

    overall = quality×0.25 + logic×0.20 + creativity×0.20 + value×0.25 + (1−risk)×0.10
    """
    w = weights or DEFAULT_WEIGHTS
    risk_inverted = 1.0 - scores.get("risk", 0.0)
    return (
        scores.get("quality", 0.0) * w["quality"]
        + scores.get("logic", 0.0) * w["logic"]
        + scores.get("creativity", 0.0) * w["creativity"]
        + scores.get("value", 0.0) * w["value"]
        + risk_inverted * w["risk"]
    )


class EvaluationClient(Protocol):
    def evaluate(self, system: str, user: str) -> str: ...


def parse_scores(text: str) -> dict[str, float]:
    """Claude の応答から5軸スコアを抽出する。JSONブロック優先、失敗時は正規表現。"""
    # JSON ブロック抽出（```json ... ``` または先頭の {...}）
    json_candidates = re.findall(r"\{[^{}]*\"(?:quality|logic|creativity|value|risk)\"[^{}]*\}", text)
    for cand in json_candidates:
        try:
            data = json.loads(cand)
            scores = {k: _clamp(float(data[k])) for k in ("quality", "logic", "creativity", "value", "risk") if k in data}
            if len(scores) == 5:
                return scores
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
    # 正規表現フォールバック: "key": value 形式（引用符有無どちらも許容）
    scores = {}
    for key in ("quality", "logic", "creativity", "value", "risk"):
        m = re.search(rf'"?{key}"?\s*[:＝]\s*([0-9]*\.?[0-9]+)', text)
        if m:
            scores[key] = _clamp(float(m.group(1)))
    if len(scores) == 5:
        return scores
    raise ValueError(f"5軸スコアを抽出できませんでした: {text[:200]}")


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


class EvaluationEngine:
    """5軸評価エンジン。評価系Claude（独立系統）を使用する。"""

    def __init__(
        self,
        client: EvaluationClient,
        *,
        weights: dict[str, float] | None = None,
        pass_threshold: float = 0.70,
    ):
        self.client = client
        self.weights = weights or DEFAULT_WEIGHTS
        self.pass_threshold = pass_threshold

    def evaluate(self, artifact: str, task_prompt: str = "") -> EvaluationResult:
        """成果物を5軸で採点する。盲検化のため task_prompt に条件情報を含めないこと。

        スコアJSONの抽出に失敗した場合、形式エラーのフィードバックを付けて
        再生成する（最大3回。崩れたら再生成）。
        """
        system = (
            "あなたは成果物の評価者です。提示された成果物を、所定のルーブリックに従い"
            "5軸（Quality / Logic / Creativity / Value / Risk）で公平に採点してください。"
            "成果物の出所・生成方法は知らされていません。\n\n" + RUBRIC
        )
        base_user = (
            f"【評価対象の成果物】\n{artifact}\n\n"
            f"【元のタスク】\n{task_prompt}\n\n"
            "上記の成果物を5軸で採点し、最終行にJSONでスコアを出力してください。"
        )
        last_err = ""
        raw = ""
        for attempt in range(MAX_EVALUATION_RETRIES):
            feedback = ""
            if attempt > 0:
                feedback = (
                    "\n\n前回の応答からスコアJSONを抽出できませんでした（"
                    f"{last_err}）。説明文はそのままでも構いませんが、"
                    '必ず最終行に {"quality": 0.5, "logic": 0.5, "creativity": 0.5, '
                    '"value": 0.5, "risk": 0.5} 形式のJSONを出力してください。'
                )
            raw = self.client.evaluate(system=system, user=base_user + feedback)
            try:
                scores = parse_scores(raw)
                break
            except ValueError as e:
                last_err = str(e)
        else:
            raise ValueError(
                f"5軸スコアの抽出が{MAX_EVALUATION_RETRIES}回連続で失敗（再生成済み）: {last_err}"
            )
        overall = compute_overall(scores, self.weights)
        return EvaluationResult(
            scores=scores,
            overall=overall,
            pass_threshold=self.pass_threshold,
            rationale=raw,
            raw=raw,
        )

    def score_judgment(self, overall: float) -> str:
        """Pass / Revise / Regenerate の判定"""
        if overall >= self.pass_threshold:
            return "Pass"
        if overall >= 0.50:
            return "Revise"
        return "Regenerate"
