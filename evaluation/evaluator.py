"""Evaluation Engine — 評価5軸による採点（品質評価に統合）。

数値定義（重み・ルーブリック・overall式）は本ファイル内の DEFAULT_WEIGHTS /
RUBRIC / compute_overall() に集約する。

**品質評価** = 5軸評価（多様性・統合性・超越性・誠実性・実用性）+
定番さ・独自性の3観点（新奇度・独自性・意外性、evaluation/quality.py）。
overall は掛け算方式で統合する:

    overall = 5軸overall × (α + (1−α) × 品質スコア)     （α = QUALITY_ALPHA = 0.25）

5軸評価は「定番さ・独自性」を測らないため、素の生成（指示のみ）が定番タスクで
無難な回答を出しても5軸 overall が高止まりし、独自性の差が反映されない。品質評価の
掛け算で、定番回答（品質スコア低）ほど overall が下がる。

評価者は**独立評価系統**（生成とは別モデル）を使う。盲検化のため評価プロンプトに
条件ラベルは渡さない（ブラインド化は呼び出し側の責務）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from elevate import i18n

# 評価5軸の重み（均等 0.20。ポリシー密着の5軸＝このエンジンが何をする機械かを測る）
DEFAULT_WEIGHTS: dict[str, float] = {
    "diversity": 0.20,  # 多様性（視点の横断・分野の広さ）— 発散
    "synthesis": 0.20,  # 統合性（矛盾解決・価値観の連結）— 統合（併記・平均化を弾く）
    "elevation": 0.20,  # 超越性（第3の位置・新観点）— 単一視点を超える解
    "honesty": 0.20,    # 誠実性（確信と不確実の区別）— 誠実さ（未実証の明記）
    "utility": 0.20,    # 実用性（具体・実行可能・誰がどう使うか）— 実行性
}

# 品質評価（定番さ・独自性）の統合係数。
# overall = 5軸overall × (α + (1−α) × 品質スコア)、α=0.25（品質評価強め）。
# 品質スコア = (新奇度 + 独自性 + 意外性) / 3（QualityResult.average）。
# 定番回答（品質スコア≈0.20）は ×0.40、独自回答（≈0.80）は ×0.85 になる。
QUALITY_ALPHA = 0.25

# Pass 判定のしきい値。品質評価の掛け算で overall の絶対値が5軸単独時より下がるため、
# 5軸単独時代の 0.70 を新スケールに合わせて 0.60 に再調整した（実測 2026-08-09:
# 優秀な昇華版 0.666 が Pass になる水準。5軸「確かに良い」+ 品質良 ≈ 0.64 前後）。
DEFAULT_PASS_THRESHOLD = 0.60

# 評価スコア抽出の再生成リトライ最大回数（崩れたら再生成）
MAX_EVALUATION_RETRIES = 3

# 採点ルーブリック（行動的定義）を評価プロンプトに埋め込む
# 2026-08-08 再調整(1): 旧ルーブリックは「明確・一貫・使用可能」を 0.8-1.0（最上位帯域）に
# 置いており、凡庸な単発生成でも 0.75-0.8 に張り付いて「向上が可視化できない」問題が
# あった。0.5 を「普通」の基準に再アンカーし、凡庸な出力は 0.5-0.6、良い出力は 0.7-0.8、
# 卓越した出力のみ 0.9 以上として、改善の余地（ヘッドルーム）を作る。
# 2026-08-08 再調整(2): 「0.5=普通」と 0.7-0.8 帯の記述「平凡」が同義で矛盾していたこと、
# 0.9+ の「卓越」が抽象的で評価者に使われないことを解消。0.7-0.8 を「無難でなく確かに良い」、
# 0.9+ を「凡庸な生成にはない固有の枠組み・見方の転換」という行動的マーカーに再定義した
# （評価が「無難さ」でなく「確かな良さ」を測るようにする。帯域は変えず記述のみ変更）。
# 2026-08-08 再調整(3)（ゼロベースで5軸を再考）: Risk（リスク認識）軸は「正直なリスク開示
# ほど評価が下がる」構造的バイアスが確認され、廃止した。代わりに本エンジンのポリシー
# （複数の独立した視点を統合して単一視点を超える成果物を生む）を測る5軸へ再設計:
# 多様性（発散）・統合性（統合。併記・平均化を弾く）・超越性（第3の位置）・
# 誠実性（未実証の明記）・実用性（具体的・整合的・実行可能）。重みは均等 0.20 で
# 特定軸を特別扱いしない。全軸「高いほど良い」（Risk 時代の反転 (1−risk) は廃止）。
RUBRIC = """各軸を0.0〜1.0で採点する。5軸は本エンジンのポリシー（複数の独立した視点を統合して、
単一視点を超える成果物を生む）を測る。

採点基準（全帯域を使うこと）: 0.5 を「無難」の基準とする。無難にまとまった凡庸な出力は 0.5〜0.6、
確かに良い出力は 0.7〜0.8、卓越した出力のみ 0.9 以上とする。凡庸な出力を 0.7 以上にしないこと。
0.7 以上は「無難にできている」だけでは足りず「確かに良い」ものに限る。0.9 以上は凡庸な生成では
決して出ない固有の枠組み・見方の転換があるものに限る。

多様性（視点の横断）: 0.9-1.0=単一視点では出ない複数の独立した視点・価値観を横断し、関係分野を広く賄う（無難でなく確かに良い） / 0.7-0.8=複数の視点・価値観を明確に横断している / 0.5-0.6=一部の視点に偏り、横断が限定的 / 0.0-0.4=単一の視点・価値観に閉じている
統合性（矛盾解決・連結）: 0.9-1.0=視点間の矛盾を解消し、相互に連結した一つの高次構造になっている / 0.7-0.8=視点が矛盾なく連結され、一貫した統合になっている / 0.5-0.6=併記・羅列に近く、視点間の矛盾が解消されていない / 0.0-0.4=視点が噛み合わず断片の寄せ集め
超越性（第3の位置）: 0.9-1.0=どの単一視点にもない固有の枠組み・見方の転換が創出されている / 0.7-0.8=統合を経て初めて得られる新たな視点が明確にある / 0.5-0.6=既存の視点の組み合わせに留まり、新観点が薄い / 0.0-0.4=焼き直し・寄せ集めのみ
誠実性（確信と不確実の区別）: 0.9-1.0=確信と不確実を明確に区別し、根拠が検証可能・欠落がない / 0.7-0.8=断定と推測が区別され、不確実な点は条件付き・前提として明示（過度な断定がない） / 0.5-0.6=断定と推測が混ざり、根拠が弱い / 0.0-0.4=不確実なことを断定・根拠のない飛躍
実用性（具体・実行可能）: 0.9-1.0=誰がどう使うかが具体的に描け、実行の筋道が検証可能 / 0.7-0.8=具体的で実行可能な筋道と利用者が明確 / 0.5-0.6=抽象度が高く、実行の見通しが不確か / 0.0-0.4=抽象的で、実行可能性が確認できない

最終行にJSON形式でスコアを出力すること。例:
{"diversity": 0.7, "synthesis": 0.6, "elevation": 0.5, "honesty": 0.75, "utility": 0.7}"""


@dataclass
class EvaluationResult:
    """評価結果。

    quality（QualityResult）は品質評価（定番さ・独自性）が統合されているときだけ
    セットされる。overall はその場合 5軸overall × (QUALITY_ALPHA + (1−QUALITY_ALPHA)×
    品質スコア) になっている。統合されていないとき（quality=None）は従来どおり5軸のみ。
    """

    scores: dict[str, float]  # diversity, synthesis, elevation, honesty, utility (0-1)
    overall: float
    pass_threshold: float = DEFAULT_PASS_THRESHOLD
    rationale: str = ""
    raw: str = ""
    quality: Any | None = None  # QualityResult | None（品質評価が統合されたとき）

    @property
    def passed(self) -> bool:
        return self.overall >= self.pass_threshold


def compute_overall(scores: dict[str, float], weights: dict[str, float] | None = None) -> float:
    """overall スコア算出。

    overall = diversity×0.20 + synthesis×0.20 + elevation×0.20 + honesty×0.20 + utility×0.20
    （全軸「高いほど良い」。Risk 時代の反転 (1−risk) は廃止）
    """
    w = weights or DEFAULT_WEIGHTS
    return sum(scores.get(k, 0.0) * w[k] for k in DEFAULT_WEIGHTS)


class EvaluationClient(Protocol):
    def evaluate(self, system: str, user: str) -> str: ...


def parse_scores(text: str) -> dict[str, float]:
    """Claude の応答から5軸スコアを抽出する。JSONブロック優先、失敗時は正規表現。"""
    # JSON ブロック抽出（```json ... ``` または先頭の {...}）
    json_candidates = re.findall(r"\{[^{}]*\"(?:diversity|synthesis|elevation|honesty|utility)\"[^{}]*\}", text)
    for cand in json_candidates:
        try:
            data = json.loads(cand)
            scores = {k: _clamp(float(data[k])) for k in ("diversity", "synthesis", "elevation", "honesty", "utility") if k in data}
            if len(scores) == 5:
                return scores
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
    # 正規表現フォールバック: "key": value 形式（引用符有無どちらも許容）
    scores = {}
    for key in ("diversity", "synthesis", "elevation", "honesty", "utility"):
        m = re.search(rf'"?{key}"?\s*[:＝]\s*([0-9]*\.?[0-9]+)', text)
        if m:
            scores[key] = _clamp(float(m.group(1)))
    if len(scores) == 5:
        return scores
    raise ValueError(f"5軸スコアを抽出できませんでした: {text[:200]}")


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


class EvaluationEngine:
    """品質評価エンジン。5軸評価 + 品質評価（定番さ・独自性）を overall に統合する。

    評価系Claude（独立系統）を使用する。quality_evaluator（QualityEvaluator）が渡されると、
    overall = 5軸overall × (QUALITY_ALPHA + (1−QUALITY_ALPHA) × 品質スコア) で統合する。
    渡されない（None）ときは従来どおり5軸のみ（後方互換）。
    """

    def __init__(
        self,
        client: EvaluationClient,
        *,
        weights: dict[str, float] | None = None,
        pass_threshold: float = DEFAULT_PASS_THRESHOLD,
        quality_evaluator=None,
        lang: str | None = None,
    ):
        self.client = client
        self.weights = weights or DEFAULT_WEIGHTS
        self.pass_threshold = pass_threshold
        self.quality_evaluator = quality_evaluator  # QualityEvaluator | None
        self.lang = i18n.resolve_lang(lang)
        self.prompts: dict = i18n.load_prompts(self.lang)

    def evaluate(self, artifact: str, task_prompt: str = "") -> EvaluationResult:
        """成果物を品質評価（5軸 + 定番さ・独自性）で採点する。

        盲検化のため task_prompt に条件情報を含めないこと。
        5軸スコアJSONの抽出に失敗した場合、形式エラーのフィードバックを付けて
        再生成する（最大3回。崩れたら再生成）。品質評価が統合されているときは、
        5軸評価に加えて品質評価（新奇度・独自性・意外性）を呼び、overall を掛け算する。
        プロンプトは prompts/{lang}.json の evaluator 節（無ければ ja 定数）。
        """
        ev = self.prompts.get("evaluator", {})
        rubric = ev.get("RUBRIC", RUBRIC)
        system = ev.get(
            "SYSTEM",
            "あなたは成果物の評価者です。提示された成果物を、所定のルーブリックに従い"
            "5軸（Diversity / Synthesis / Elevation / Honesty / Utility）で公平に採点してください。"
            "成果物の出所・生成方法は知らされていません。",
        ) + "\n\n" + rubric
        base_user = ev.get(
            "BASE_USER",
            "【評価対象の成果物】\n{artifact}\n\n"
            "【元のタスク】\n{task}\n\n"
            "上記の成果物を5軸で採点し、最終行にJSONでスコアを出力してください。",
        ).format(artifact=artifact, task=task_prompt)
        example = '{"diversity": 0.5, "synthesis": 0.5, "elevation": 0.5, "honesty": 0.5, "utility": 0.5}'
        feedback_tmpl = ev.get(
            "FEEDBACK",
            "\n\n前回の応答からスコアJSONを抽出できませんでした（{error}）。"
            "説明文はそのままでも構いませんが、必ず最終行に {example} 形式のJSONを出力してください。",
        )
        last_err = ""
        raw = ""
        for attempt in range(MAX_EVALUATION_RETRIES):
            feedback = ""
            if attempt > 0:
                feedback = feedback_tmpl.format(error=last_err, example=example)
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
        quality_result = None
        if self.quality_evaluator is not None:
            quality_result = self.quality_evaluator.evaluate(artifact, task_prompt)
            overall *= QUALITY_ALPHA + (1.0 - QUALITY_ALPHA) * quality_result.average
        return EvaluationResult(
            scores=scores,
            overall=overall,
            pass_threshold=self.pass_threshold,
            rationale=raw,
            raw=raw,
            quality=quality_result,
        )

    def score_judgment(self, overall: float) -> str:
        """Pass / Revise / Regenerate の判定"""
        if overall >= self.pass_threshold:
            return "Pass"
        if overall >= 0.50:
            return "Revise"
        return "Regenerate"
