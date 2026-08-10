"""品質評価（定番さ・独自性）— 5軸評価の死角を測る評価。

5軸評価（多様性・統合性・超越性・誠実性・実用性）は「定番さ・独自性」を測らない。
素の生成（指示のみ）が定番タスクで無難な回答を出しても、枠組みの多様さ・誠実さ・実用性で
高得点になり、独自性の差が overall に反映されない（実測 2026-08-09: 定番回答
（新奇度0.10 / 独自性0.30）の素の生成が5軸 overall 0.72 を獲得。独自性 0.90 の昇華版との
5軸差は 0.01 に留まった）。

本モジュールはこの死角を、3つの観点（新奇度・独自性・意外性）で測る**品質評価**を提供する。
5軸評価と合わせて「品質評価」体系を構成する。overall は掛け算方式で統合される:

    overall = 5軸平均 × (α + (1−α) × 品質スコア)      α = 0.25（QUALITY_ALPHA）
    品質スコア = (新奇度 + 独自性 + 意外性) / 3

0.75 は (1−α) の展開形。品質スコアが1.0なら係数1.0、0なら0.25（定番回答でも5軸の25%は残す）。

定番回答ほど品質スコアが低く、係数が下がって overall が減る。全観点「高いほど良い」に
統一しており、評価者にもそのまま測らせる（定番さは「新奇度の低さ」として現れる。
反転する二段構えは取らない）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from elevate import i18n

# 品質評価ルーブリック（評価者プロンプトに埋め込む）
# 全観点「高いほど良い」で統一し、評価者にもそのまま測らせる（公開される新奇度と
# 内部の測り方が同じ。反転する二段構えは使わない）。
# 下記の日本語定数（_QUALITY_RUBRIC / BASE_USER / FEEDBACK の既定）は**安全弁
# （フォールバック）**——正本は prompts/{lang}.json の quality 節。QualityEvaluator は
# 常に言語別ストアを読むため、通常は使われない。ストア欠損時に ja へ退行しない安全網。
# 注: 品質スコアJSONキーは D2 により英語（novelty/originality/surprise/rationale）に一本化
# 済み。この定数の最終行に残る日本語キーは旧形式の既定（ja 後方互換）。
_QUALITY_RUBRIC = """あなたは成果物の「定番さ・独自性」の検証者です。提示された成果物を、所定の観点で評価してください。

【観点】（各 0.0〜1.0）
- 新奇度: そのタスクで「多くのAI・多くの人が書く典型的な回答」からどの程度逸脱しているか。
  典型的なレパートリー（朝のルーティーンなら「朝の光・運動・朝食・前夜の準備・スマホ制限」など）に
  収まっているほど低い。定番レパートリーにない目新しさがあるほど高い。
- 独自性: 定番レパートリーにない固有の視点・概念枠組み・造語・哲学が含まれているか。
  含まれるほど高い。
- 意外性: 読み手の予想を裏切る要素があるか。あるほど高い。

必ず最終行に JSON 形式でスコアを出力してください（フォーマット厳守）:
{"新奇度": 0.2, "独自性": 0.3, "意外性": 0.2, "理由": "…"}"""

# スコアの最大値（純粋に1.0を超えて返す評価者への安全弁）
_MAX_SCORE = 1.0

# 品質評価スコアJSON抽出の再生成リトライ最大回数（崩れたら再生成）
MAX_QUALITY_RETRIES = 3


def _clamp(x: float) -> float:
    return max(0.0, min(_MAX_SCORE, x))


def _extract_json(text: str) -> dict:
    """最終行の品質評価JSON（英語キー: novelty/originality/surprise/rationale、D2確定）を抽出する。

    5軸評価（evaluator.py）が英語キーであることとの一貫性のため、品質評価も英語キーに
    一本化する（計画 D2）。日本語キーのみの評価者応答は旧形式として許容しない。
    """
    m = re.findall(r'\{[^{}]*"(?:novelty|originality|surprise)"[^{}]*\}', text)
    if not m:
        return {}
    return json.loads(m[-1])


@dataclass
class QualityResult:
    """品質評価（定番さ・独自性）のスコア。**全て「高いほど良い」**で統一している。

    novelty（新奇度）は評価者が直接測る（定番回答ほど低く出る）。
    overall の掛け算係数は average を使う。
    """

    novelty: float       # 新奇度（定番レパートリーからの目新しさ。高いほど良い）
    originality: float   # 独自性（高いほど良い）
    surprise: float      # 意外性（高いほど良い）
    rationale: str       # 判定理由

    @property
    def average(self) -> float:
        """3観点の平均。overall の掛け算係数に使う品質スコア（高いほど良い）。"""
        return (self.novelty + self.originality + self.surprise) / 3.0

    @property
    def is_generic(self) -> bool:
        """定番回答の目安: 新奇度が低く独自性も低い（既定 新奇度≤0.3 / 独自性≤0.5）。"""
        return self.novelty <= 0.3 and self.originality <= 0.5


class QualityEvaluator:
    """品質評価者。ClaudeClient 等の evaluate(system, user) プロトコルを使う。

    5軸評価（EvaluationEngine）と同じクライアントを使い、temperature 0 で決定的に評価する。
    """

    def __init__(self, client, lang: str | None = None):
        self.client = client
        self.lang = i18n.resolve_lang(lang)
        self.prompts: dict = i18n.load_prompts(self.lang)

    def evaluate(self, artifact: str, task: str = "") -> QualityResult:
        """成果物の定番さ・独自性を評価する。

        スコアJSONの抽出に失敗した場合、形式エラーのフィードバックを付けて
        再生成する（最大3回。崩れたら再生成——5軸評価と同じ方針）。
        プロンプト・JSONキーは prompts/{lang}.json の quality 節（英語キー、D2）。
        """
        q = self.prompts.get("quality", {})
        rubric = q.get("RUBRIC", _QUALITY_RUBRIC)
        base_user = q.get("BASE_USER", "【タスク】\n{task}\n\n【成果物】\n{artifact}").format(
            task=task, artifact=artifact
        )
        example = '{"novelty": 0.5, "originality": 0.5, "surprise": 0.5, "rationale": "…"}'
        feedback_tmpl = q.get(
            "FEEDBACK",
            "\n\n前回の応答から品質評価のJSONを抽出できませんでした（{error}）。"
            "説明文はそのままでも構いませんが、必ず最終行に {example} 形式のJSONを出力してください。",
        )
        last_err = ""
        for attempt in range(MAX_QUALITY_RETRIES):
            feedback = ""
            if attempt > 0:
                feedback = feedback_tmpl.format(error=last_err, example=example)
            text = self.client.evaluate(rubric, base_user + feedback)
            try:
                data = _extract_json(text)
                if not data:
                    raise ValueError("JSONを抽出できませんでした")
                return QualityResult(
                    novelty=_clamp(float(data.get("novelty", 0.5))),
                    originality=_clamp(float(data.get("originality", 0.5))),
                    surprise=_clamp(float(data.get("surprise", 0.5))),
                    rationale=str(data.get("rationale", "")).strip(),
                )
            except (ValueError, KeyError, TypeError) as exc:
                last_err = str(exc)
        raise ValueError(
            f"品質評価のJSONの抽出が{MAX_QUALITY_RETRIES}回連続で失敗（再生成済み）: {last_err}"
        )


def format_quality_line(result: QualityResult, lang: str | None = None) -> str:
    """品質評価を1行で整形する（CLI 表示用）。全観点高いほど良い。

    locales/{lang}.json の evaluation 節から言語別ラベル・定番フラグを取る
    （quality_line / generic_flag は evaluation 節配下に置く）。
    """
    resolved = i18n.resolve_lang(lang)
    locale = i18n.load_locale(resolved)
    ev = locale.get("evaluation", {})
    label = ev.get(
        "quality_line",
        "品質評価: 新奇度={novelty} / 独自性={originality} / 意外性={surprise}",
    )
    flag = ev.get("generic_flag", "⚠定番")
    flags = f" {flag}" if result.is_generic else ""
    return label.format(
        novelty=f"{result.novelty:.2f}",
        originality=f"{result.originality:.2f}",
        surprise=f"{result.surprise:.2f}",
    ) + flags
