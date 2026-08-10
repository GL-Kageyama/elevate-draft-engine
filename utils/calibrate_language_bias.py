#!/usr/bin/env python3
"""言語間の評価較正ドリフトのランタイム計測（計画フェーズ8.2 の後半）。

**同一成果物**を en / ja / zh の評価プロンプト（5軸 + 品質評価）で採点し、
スコア分布を言語間で比較する。wisdom-council（ver1）では英語が系統的 +8〜9 点・
originality 反転が観測された。elevate はこのスコアで compare（昇華優位性）と
improve（quality-ceiling・PASS）を判定するため、**言語が違うと閾値の意味が変わる**。

このスクリプトは en を主基準（D1: 既定 en）に、en のスコア分布が ja/zh から
どれだけ離れているかを測る。ずれが大きければ en 値への閾値調整を検討する
（帯域・重み・ルーブリックの意味は変えない）。

Usage:
    python utils/calibrate_language_bias.py --artifact examples/i18n/morning-routine-en/artifacts/elevated.md
    python utils/calibrate_language_bias.py --artifact PATH [--task TEXT] [--repeats 3] [--out DIR]

Exit codes:
    0  完了（バイアスの有無とは無関係。計測は常に実施）
    1  計測失敗（API エラー等）
"""

import argparse
import json
import os
import statistics
import sys
from dataclasses import asdict, dataclass, field

# リポジトリ root を import パスに追加
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from adapters.claude_client import ClaudeClient  # noqa: E402
from elevate import i18n  # noqa: E402
from evaluation.evaluator import EvaluationEngine  # noqa: E402
from evaluation.quality import QualityEvaluator  # noqa: E402

LANGS = ("en", "ja", "zh")

# overall の統合式（evaluation/quality.py と同じ。α = 0.25）
QUALITY_ALPHA = 0.25

# 既定 en の閾値（ja 較正時代の値。en バイアスが大きければ再取得の要否判断に使う）
DEFAULT_PASS_THRESHOLD = 0.60


@dataclass
class LangResult:
    lang: str
    axis_means: dict = field(default_factory=dict)   # 5軸の各平均
    axis_sds: dict = field(default_factory=dict)     # 5軸の各標準偏差
    five_axis_mean: float = 0.0
    quality_novelty: float = 0.0
    quality_originality: float = 0.0
    quality_surprise: float = 0.0
    quality_mean: float = 0.0
    overall: float = 0.0                               # 5軸平均 × (α + (1−α)×品質平均)
    quality_sds: dict = field(default_factory=dict)


def _mean(vals: list[float]) -> float:
    return statistics.mean(vals) if vals else 0.0


def _sd(vals: list[float]) -> float:
    return statistics.stdev(vals) if len(vals) > 1 else 0.0


def run(lang: str, artifact: str, task: str, repeats: int) -> LangResult:
    """ある言語で artifact を repeats 回評価し集計する。"""
    client = ClaudeClient()
    engine = EvaluationEngine(client, lang=lang)
    qeval = QualityEvaluator(client, lang=lang)

    axes: dict[str, list[float]] = {}
    novel, orig, surp = [], [], []

    for _ in range(repeats):
        er = engine.evaluate(artifact, task)
        for key, value in er.scores.items():
            axes.setdefault(key, []).append(value)
        qr = qeval.evaluate(artifact, task)
        novel.append(qr.novelty)
        orig.append(qr.originality)
        surp.append(qr.surprise)

    axis_means = {k: _mean(v) for k, v in axes.items()}
    axis_sds = {k: _sd(v) for k, v in axes.items()}
    five_axis_mean = _mean(list(axis_means.values()))
    qm = _mean(novel) / 1.0
    q_mean = (_mean(novel) + _mean(orig) + _mean(surp)) / 3.0
    overall = five_axis_mean * (QUALITY_ALPHA + (1.0 - QUALITY_ALPHA) * q_mean)

    return LangResult(
        lang=lang,
        axis_means=axis_means,
        axis_sds=axis_sds,
        five_axis_mean=five_axis_mean,
        quality_novelty=_mean(novel),
        quality_originality=_mean(orig),
        quality_surprise=_mean(surp),
        quality_mean=q_mean,
        overall=overall,
        quality_sds={"novelty": _sd(novel), "originality": _sd(orig), "surprise": _sd(surp)},
    )


def _fmt(x: float) -> str:
    return f"{x:.3f}"


def main() -> int:
    ap = argparse.ArgumentParser(description="言語間の評価較正ドリフト計測")
    ap.add_argument("--artifact", required=True, help="評価する成果物ファイル（同一物を全言語で採点）")
    ap.add_argument("--task", default="", help="タスク文言（成果物の評価コンテキスト）")
    ap.add_argument("--repeats", type=int, default=3, help="各言語での評価回数（既定3）")
    ap.add_argument("--langs", default=",".join(LANGS), help="対象言語（カンマ区切り。既定 en,ja,zh）")
    ap.add_argument("--out", default=None, help="結果の保存先ディレクトリ（省略時は標準出力のみ）")
    args = ap.parse_args()

    if not os.path.isfile(args.artifact):
        print(f"error: artifact not found: {args.artifact}", file=sys.stderr)
        return 1

    with open(args.artifact, encoding="utf-8") as fh:
        artifact = fh.read().strip()

    langs = [s.strip() for s in args.langs.split(",") if s.strip()]
    results = []
    for lang in langs:
        print(f"--- measuring {lang} (repeats={args.repeats}) ---", file=sys.stderr)
        results.append(run(lang, artifact, args.task, args.repeats))

    # ---- レポート ----
    lines: list[str] = []
    lines.append("# 言語間の評価較正ドリフト（同一成果物を en/ja/zh で採点）")
    lines.append("")
    lines.append(f"- 成果物: `{args.artifact}`")
    lines.append(f"- タスク: `{args.task or '(未指定)'}`")
    lines.append(f"- 各言語の評価回数: {args.repeats}")
    lines.append("")

    lines.append("## 5軸評価（各軸の平均）")
    headers = ["言語"] + list(results[0].axis_means.keys()) + ["5軸平均"]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "---|" * len(headers))
    for r in results:
        row = [r.lang] + [_fmt(v) for v in r.axis_means.values()] + [_fmt(r.five_axis_mean)]
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    lines.append("## 品質評価（各観点の平均）")
    headers = ["言語", "新奇度", "独自性", "意外性", "品質平均"]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "---|" * len(headers))
    for r in results:
        row = [r.lang, _fmt(r.quality_novelty), _fmt(r.quality_originality),
               _fmt(r.quality_surprise), _fmt(r.quality_mean)]
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    lines.append("## overall（5軸平均 × (α + (1−α)×品質平均)。PASS 閾値は既定 en で 0.60）")
    lines.append("")
    for r in results:
        flag = "PASS" if r.overall >= DEFAULT_PASS_THRESHOLD else "below"
        lines.append(f"- **{r.lang}**: overall = {_fmt(r.overall)} ({flag})")
    lines.append("")

    # バイアス（en を主基準）
    base = next((r for r in results if r.lang == "en"), results[0])
    lines.append("## en からのずれ（D1: 既定 en が主基準）")
    lines.append("")
    for r in results:
        if r is base:
            continue
        d_axis = r.five_axis_mean - base.five_axis_mean
        d_qual = r.quality_mean - base.quality_mean
        d_over = r.overall - base.overall
        lines.append(
            f"- {r.lang} vs en: 5軸平均 {d_axis:+.3f} / 品質平均 {d_qual:+.3f} / "
            f"overall {d_over:+.3f}"
        )
    lines.append("")
    lines.append("> 注: この数値は同一成果物・同一評価モデルでの言語間差。+ はその言語の方が")
    lines.append("> 高く出やすい（= 緩く評価しやすい）ことを示す。ver1 実測では en が系統的に")
    lines.append("> +8〜9 点（0.08〜0.09）出た。差が 0.05 を超える場合は en を主基準に")
    lines.append("> 閾値（DEFAULT_PASS_THRESHOLD / quality-ceiling）の再取得を検討する。")
    lines.append("")

    report = "\n".join(lines)

    if args.out:
        os.makedirs(args.out, exist_ok=True)
        name = os.path.splitext(os.path.basename(args.artifact))[0]
        with open(os.path.join(args.out, f"calibration_{name}.md"), "w", encoding="utf-8") as fh:
            fh.write(report)
        with open(os.path.join(args.out, f"calibration_{name}.json"), "w", encoding="utf-8") as fh:
            json.dump(
                {"artifact": args.artifact, "task": args.task, "repeats": args.repeats,
                 "langs": [asdict(r) for r in results]},
                fh, ensure_ascii=False, indent=2,
            )
        print(f"saved report -> {args.out}")
    else:
        print(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
