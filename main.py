"""elevate-draft-engine 薄い CLI。

使い方:
    python main.py generate "タスク"                 # 素のAI（単発生成）, 1 call
    python main.py diverge "タスク"                  # 8エージェントで草案生成・一覧出力
    python main.py synthesize draft1.md draft2.md  # 外部草案を統合（核心）
    python main.py elevate "タスク"                  # diverge → synthesize 一気
    python main.py compare "タスク"                  # generate vs elevate 両方出力
    python main.py compare "タスク" --evaluate       # + 5軸評価でスコア比較

共通オプション:
    --mock                API 不要のモックで実行（パイプライン確認用）
    --method two-stage|single-pass      統合方式（既定 two-stage: 矛盾解決推理→最終化）
    --agents 名前...      使用するエージェントを限定（既定: 全8エージェント）
    --out DIR             成果物をファイル保存（省略時は outputs/{タスク名}/ にデフォルト保存）
                          elevate/compare は各草案 draft_{agent}.md も保存
                          compare --runs>1 は各 run を run_NN/ サブフォルダに分離保存（履歴）

認証: ANTHROPIC_API_KEY（通常）または ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL（ゲートウェイ）。
スロットル（空応答対策）は既定 2 秒（CLAUDE_MIN_INTERVAL_SECONDS で変更可）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from elevate import Draft, DraftEngine


def _build_parser() -> argparse.ArgumentParser:
    # 共通オプションは各サブコマンドの後に置く（親パーサーとして全サブコマンドに共有）。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--mock", action="store_true", help="API を使わずモックで実行")
    common.add_argument("--engine", default="sdk", choices=["sdk", "claude-code"], help="生成エンジン（既定 sdk。claude-code は claude -p 起動で安定）")
    common.add_argument("--method", default="two-stage", choices=["two-stage", "single-pass"], help="統合方式（既定 two-stage）")
    common.add_argument("--agents", nargs="+", default=None, help="使用するエージェント（既定: 全エージェント）")
    common.add_argument("--out", type=Path, default=None, help="成果物を保存するディレクトリ（省略時は outputs/{タスク名}/ にデフォルト保存）")
    common.add_argument("--no-strong-claim", action="store_true", help="エージェントから「最強の主張」断言枠を除去（アブレーション: 枠あり/なしの統合品質差を測定）")
    common.add_argument("--runs", type=int, default=1, help="compare の比較を N 回反復して統計集計（平均・勝率・標準偏差）を出力（既定 1）")
    common.add_argument("--baseline", default="single", choices=["single", "best-of-n"], help="compare の比較対象ベースライン（既定 single: 素の単発生成 / best-of-n: 統合なし最良草案選択＝帰無仮説）")

    p = argparse.ArgumentParser(
        prog="elevate-draft-engine",
        description="複数の独立した草案を統合して一段高い成果物を生むエンジン",
    )
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", parents=[common], help="素のAI（単発生成）で1回生成")
    g.add_argument("task", help="タスク")
    g.set_defaults(func=cmd_generate)

    d = sub.add_parser("diverge", parents=[common], help="エージェントで独立草案を生成")
    d.add_argument("task", help="タスク")
    d.set_defaults(func=cmd_diverge)

    s = sub.add_parser("synthesize", parents=[common], help="外部草案ファイル群を統合（核心）")
    s.add_argument("draft_files", nargs="+", type=Path, help="草案テキストファイル（エージェント名=ファイル名の拡張子なし）")
    s.add_argument("--task", default="", help="元のタスク（任意。統合文脈として使う）")
    s.set_defaults(func=cmd_synthesize)

    e = sub.add_parser("elevate", parents=[common], help="diverge → synthesize を一気に")
    e.add_argument("task", help="タスク")
    e.set_defaults(func=cmd_elevate)

    c = sub.add_parser("compare", parents=[common], help="generate vs elevate の両方を出力・比較")
    c.add_argument("task", help="タスク")
    c.add_argument("--evaluate", action="store_true", help="5軸評価でスコア比較")
    c.add_argument("--verbose", action="store_true", help="--runs>1 のとき各runの詳細と草案評価スコアも表示")
    c.set_defaults(func=cmd_compare)

    return p


# ---- モック（API 不要・パイプライン確認用） ----

_PERSONA_NAME_RE = re.compile(r"You are the \*\*([A-Za-z]+)\*\*")


class MockGenerator:
    """決定的なモック応答を返す。完全性ガードを通過する文形にしている。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, float | None]] = []

    def generate(
        self,
        system: str,
        user: str,
        *,
        temperature: float | None = None,
        on_chunk=None,
    ) -> str:
        self.calls.append((system, user, temperature))
        # エージェント草案: 観点名を込めたモック草案を返す
        # 「草案の作り方」で検出する（--no-strong-claim で「最強の主張」枠を剥がしても
        # このマーカーとペルソナ名（You are the **Name**）は残るため、安定に識別できる）。
        if "草案の作り方" in system:
            m = _PERSONA_NAME_RE.search(system)
            name = m.group(1).lower() if m else "unknown"
            text = f"これはエージェント「{name}」からのモック草案である。{name}らしい観点で描かれている。"
        # 矛盾解決推理: 長さ基準（最小30字）を満たす推理らしい文を返す
        elif "矛盾解決推理" in system:
            text = (
                "草案間の対立は「価値の最大化と実現性の担保」という軸に集約される。"
                "解決仮説として、まず最小の実現単位で制度に埋め込み、蓄積された実証データで"
                "価値の主張を順次強化する。この統合は単一観点の草案にはない解を構成する。"
            )
        # それ以外（素の生成・単発統合・最終化）: 文終端記号で終わる完全な文を返す
        else:
            text = (
                "これは与えられたタスクに対するモックの完全な分析である。"
                "Target は明確であり、Value は実現可能、Risk は具体的な対策とともに示され、"
                "Opportunity は拡張性を持つ。以上が統合された結論である。"
            )
        # ストリーム追記用: 全文が揃った時点で1回だけ流す（SDK クライアントと同じ動作）
        if on_chunk is not None:
            on_chunk(text)
        return text


class MockEvaluator:
    """評価用のモック。EvaluationEngine と同じプロトコル（EvaluationResult を返す）。

    best-of-n ベースラインが意味を持つよう、成果物テキストごとに決定的に異なるスコアを
    返す（同じテキストなら常に同じ overall）。「モック草案」を含むテキストは、
    エージェント名（全文に現れる）のハッシュで 0.5〜0.9 に分布させる。それ以外の
    （素の生成・統合成果物）は 0.8 で返す。統合成果物（ELEVATE）が最高になる想定。
    """

    def __init__(self) -> None:
        self.calls: list[int] = []

    def evaluate(self, system: str, user: str) -> "EvaluationResult":
        from evaluation.evaluator import EvaluationResult, compute_overall

        self.calls.append(1)
        if "モック草案" in system:
            # エージェント草案: 名前に応じた決定的なスコア（0.5〜0.9）
            # 「モック草案」の直後の「エージェント「{name}」」から name を取り出す
            m = re.search(r"エージェント「([^」]+)」", system)
            name = m.group(1) if m else "?"
            base = 0.5 + (sum(ord(c) for c in name) % 40) / 100.0  # 0.50〜0.89
            scores = {"quality": base, "logic": base, "creativity": base, "value": base, "risk": 0.3}
        else:
            scores = {"quality": 0.8, "logic": 0.8, "creativity": 0.8, "value": 0.8, "risk": 0.3}
        return EvaluationResult(
            scores=scores,
            overall=compute_overall(scores),
            pass_threshold=0.70,
            rationale="モック評価",
            raw="モック評価",
        )

    def score_judgment(self, overall: float) -> str:
        if overall >= 0.70:
            return "Pass"
        if overall >= 0.50:
            return "Revise"
        return "Regenerate"


def _make_engine(args: argparse.Namespace) -> DraftEngine:
    engine_args = {"strong_claim_frame": not args.no_strong_claim}
    if args.mock:
        return DraftEngine(MockGenerator(), **engine_args)
    if args.engine == "claude-code":
        # claude -p 経由（独立プロセス起動）。ゲートウェイ空応答に強い。
        from adapters.claude_code_client import ClaudeCodeClient

        return DraftEngine(ClaudeCodeClient(), **engine_args)
    from adapters.claude_client import ClaudeClient

    return DraftEngine(ClaudeClient(), **engine_args)


def _make_evaluator(args: argparse.Namespace):
    if args.mock:
        return MockEvaluator()
    from adapters.claude_client import ClaudeClient
    from evaluation.evaluator import EvaluationEngine

    return EvaluationEngine(ClaudeClient())


def _agent_of(path: Path) -> str:
    """草案ファイルのエージェント名（拡張子なしのファイル名）。"""
    return path.stem


def _load_draft_files(paths: list[Path]) -> list[Draft]:
    drafts = []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(f"草案ファイルがありません: {path}")
        drafts.append(Draft(agent=_agent_of(path), content=path.read_text().strip()))
    return drafts


def _print_artifact(title: str, text: str) -> None:
    print(f"=== {title} ===")
    print(text)
    print()


def _task_dirname(task: str, max_len: int = 60) -> str:
    """タスク名からデフォルト出力ディレクトリ名を作る。

    フォルダ名に使えない文字（/\\:*?"<>| と制御文字）を除去し、日本語はそのまま使う。
    長すぎる場合は切り詰める（ファイル名上限 255 バイト未満に収める）。
    """
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", task).strip().rstrip(". ")
    return cleaned[:max_len] or "task"


def _resolve_out(args: argparse.Namespace, task: str) -> argparse.Namespace:
    """--out 未指定時のデフォルト保存先を args.out に設定する。

    「生成時にファイルの逐次作成をデフォルトにする」ため、--out が無くても
    outputs/{タスク名}/ に全成果物（草案・推理・統合成果物・素の生成）を保存する。
    --out 指定時は従来どおりその場所へ。
    """
    if args.out is None:
        args.out = Path("outputs") / _task_dirname(task)
    return args


def _save(args: argparse.Namespace, name: str, text: str) -> None:
    if args.out is None:
        return
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{name}.md"
    path.write_text(text)
    print(f"→ 保存: {path}")


def _save_input(args: argparse.Namespace, task: str) -> None:
    """タスクを input.md として保存（examples/ の体裁）。"""
    if args.out is None:
        return
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "input.md"
    path.write_text(f"# タスク\n\n{task}\n")
    print(f"→ 保存: {path}")


def cmd_generate(args: argparse.Namespace) -> None:
    engine = _make_engine(args)
    _print_artifact("素の生成（単発）", engine.generate(args.task))


def _report_draft(args: argparse.Namespace, draft: Draft) -> None:
    """草案の完了通知（ファイル自体は engine の draft_dir が生成中に逐次追記している）。

    --out 未指定時は何も保存しないため、通知も出さない。
    """
    if args.out is not None:
        print(f"→ 保存: {args.out / f'draft_{draft.agent}.md'}")


def cmd_diverge(args: argparse.Namespace) -> None:
    _resolve_out(args, args.task)
    engine = _make_engine(args)
    drafts = engine.diverge(
        args.task, agents=args.agents,
        draft_dir=args.out,
        on_draft=lambda d: _report_draft(args, d),
    )
    for draft in drafts:
        _print_artifact(f"草案: {draft.agent}", draft.content)


def cmd_synthesize(args: argparse.Namespace) -> None:
    engine = _make_engine(args)
    drafts = _load_draft_files(args.draft_files)
    reconciliation, elevated = engine.synthesize_with_reconciliation(
        drafts, method=args.method, task=args.task
    )
    if reconciliation:
        _save(args, "reconciliation", reconciliation)
    _print_artifact(f"統合成果物（{args.method}）", elevated)
    _save(args, "elevated", elevated)


def cmd_elevate(args: argparse.Namespace) -> None:
    _resolve_out(args, args.task)
    engine = _make_engine(args)
    _save_input(args, args.task)
    drafts = engine.diverge(
        args.task, agents=args.agents,
        draft_dir=args.out,
        on_draft=lambda d: _report_draft(args, d),
    )
    reconciliation, elevated = engine.synthesize_with_reconciliation(
        drafts, method=args.method, task=args.task
    )
    if reconciliation:
        _save(args, "reconciliation", reconciliation)
    _print_artifact(f"エレベート成果物（{args.method}）", elevated)
    _save(args, "elevated", elevated)


def _evaluate_and_report(label: str, artifact: str, task: str, evaluator, *, save_to: Path | None = None):
    """単回評価して報告し、結果オブジェクトを返す（統計集計は .overall で使う）。

    save_to 指定時は、その run の評価記録（overall・各次元・根拠）を Markdown で保存する。
    """
    result = evaluator.evaluate(artifact, task)
    print(f"[{label}] overall={result.overall:.3f}（{evaluator.score_judgment(result.overall)}）")
    for k, v in result.scores.items():
        print(f"    {k}: {v:.2f}")
    print()
    if save_to is not None:
        _save_evaluation_record(save_to, label, result, evaluator)
    return result


def _save_evaluation_record(path: Path, label: str, result, evaluator) -> None:
    """単一評価の記録（overall・各次元・根拠）を Markdown で保存する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"## {label}",
        f"- overall: {result.overall:.3f}（{evaluator.score_judgment(result.overall)}）",
        "- スコア:",
    ]
    for k, v in result.scores.items():
        lines.append(f"  - {k}: {v:.2f}")
    rationale = getattr(result, "rationale", None)
    if rationale:
        lines.append(f"- 根拠: {rationale}")
    path.write_text("\n".join(lines) + "\n")
    print(f"→ 保存: {path}")


def _best_of_n(evaluator, drafts: list[Draft], task: str, *, verbose: bool = False) -> tuple[Draft, float]:
    """帰無仮説ベースライン: 統合せず全草案を評価し、最高 overall の草案を選ぶ。

    統合（reconcile → finalize）の付加価値を分離して測るための比較対象。
    各草案の評価スコアがそのまま best-of-N の実現値になる（選ばれた草案のスコアを
    報告する。選択時の評価を再評価で上書きしない——評価は盲検化されているため）。
    """
    best_draft = drafts[0]
    best_score = -1.0
    for draft in drafts:
        result = evaluator.evaluate(draft.content, task)
        if verbose:
            print(f"    [草案: {draft.agent}] overall={result.overall:.3f}")
        if result.overall > best_score:
            best_draft, best_score = draft, result.overall
    if verbose:
        print(f"    → 最良草案: {best_draft.agent}（overall={best_score:.3f}）")
    return best_draft, best_score


def _stat_summary(scores: list[float]) -> str:
    """平均・標準偏差・件数の集計文字列。"""
    n = len(scores)
    mean = sum(scores) / n
    var = sum((x - mean) ** 2 for x in scores) / n
    sd = var ** 0.5
    return f"mean={mean:.3f} sd={sd:.3f}（n={n}）"


def cmd_compare(args: argparse.Namespace) -> None:
    task = args.task
    if args.baseline == "best-of-n" and not args.evaluate:
        raise RuntimeError("--baseline best-of-n は草案を評価して最良を選ぶため、--evaluate が必要です")
    _resolve_out(args, task)
    engine = _make_engine(args)
    _save_input(args, task)

    runs = max(1, args.runs)
    baseline_scores: list[float] = []
    elevated_scores: list[float] = []
    wins = 0
    baseline_label = "素の生成（単発）" if args.baseline == "single" else "ベースライン（best-of-n）"
    show_artifacts = runs == 1 or args.verbose

    for run_idx in range(runs):
        run_num = run_idx + 1
        # --runs > 1 のとき、各 run の成果物を run_NN/ サブフォルダに分離して保存する
        # （runごとに上書きしない履歴として残す）。--runs 1 は従来どおり --out 直下へ。
        run_dir = None
        if args.runs > 1 and args.out is not None:
            run_dir = args.out / f"run_{run_num:02d}"
        if run_dir is not None:
            run_args = argparse.Namespace(**vars(args))
            run_args.out = run_dir
        else:
            run_args = args

        drafts = engine.diverge(
            task, agents=run_args.agents,
            draft_dir=run_args.out,
            on_draft=lambda d: _report_draft(run_args, d),
        )
        reconciliation, elevated = engine.synthesize_with_reconciliation(
            drafts, method=run_args.method, task=task
        )
        if reconciliation:
            _save(run_args, "reconciliation", reconciliation)

        if run_args.baseline == "best-of-n":
            evaluator = _make_evaluator(run_args)
            best_draft, baseline_score = _best_of_n(
                evaluator, drafts, task, verbose=run_args.verbose
            )
            baseline = best_draft.content
        else:
            baseline = engine.generate(task)
            baseline_score = None

        _save(run_args, "raw" if run_args.baseline == "single" else "best_single", baseline)
        _save(run_args, "elevated", elevated)

        if show_artifacts:
            _print_artifact(baseline_label, baseline)
            _print_artifact(f"エレベート成果物（{run_args.method}）", elevated)

        if run_args.evaluate:
            evaluator = _make_evaluator(run_args)
            if baseline_score is None:  # single ベースラインはここで初めて評価
                baseline_result = _evaluate_and_report(
                    baseline_label, baseline, task, evaluator,
                    save_to=run_dir / "evaluation_baseline.md" if run_dir else None,
                )
                baseline_score = baseline_result.overall
            else:  # best-of-n は選択時のスコアを報告（再評価しない）
                print(f"[{baseline_label}] overall={baseline_score:.3f}（{evaluator.score_judgment(baseline_score)}）")
                print()
                if run_dir is not None:
                    _save_baseline_score_record(
                        run_dir / "evaluation_baseline.md", baseline_label, baseline_score, evaluator
                    )
            elevated_result = _evaluate_and_report(
                "ELEVATE", elevated, task, evaluator,
                save_to=run_dir / "evaluation_elevated.md" if run_dir else None,
            )
            elevated_score = elevated_result.overall
            baseline_scores.append(baseline_score)
            elevated_scores.append(elevated_score)
            if elevated_score > baseline_score:
                wins += 1

    if args.evaluate and runs > 1:
        diffs = [e - b for b, e in zip(baseline_scores, elevated_scores)]
        summary_lines = [
            "=== 比較集計 ===",
            f"{baseline_label}: {_stat_summary(baseline_scores)}",
            f"ELEVATE:            {_stat_summary(elevated_scores)}",
            f"差（ELEVATE−ベースライン）: {_stat_summary(diffs)}",
            f"勝率（ELEVATE > ベースライン）: {wins}/{runs} = {wins / runs:.1%}",
        ]
        for line in summary_lines:
            print(line)
        if args.out is not None:
            _save_measurement(args.out, baseline_label, baseline_scores, elevated_scores, wins, runs)


def _save_baseline_score_record(path: Path, label: str, overall: float, evaluator) -> None:
    """best-of-n ベースラインの選択時スコア記録（再評価はしない）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"## {label}\n"
        f"- overall: {overall:.3f}（{evaluator.score_judgment(overall)}）\n"
        "- スコア: 最良草案の選択時評価をそのまま使用（選択を再評価で上書きしない）\n"
    )
    print(f"→ 保存: {path}")


def _save_measurement(
    out: Path, baseline_label: str, baseline_scores: list[float],
    elevated_scores: list[float], wins: int, runs: int,
) -> None:
    """比較の統計集計（measurement.md）を --out 直下に保存する。"""
    out.mkdir(parents=True, exist_ok=True)
    diffs = [e - b for b, e in zip(baseline_scores, elevated_scores)]
    text = (
        f"# 比較計測（--runs {runs}）\n\n"
        f"- {baseline_label}: {_stat_summary(baseline_scores)}\n"
        f"- ELEVATE:            {_stat_summary(elevated_scores)}\n"
        f"- 差（ELEVATE−ベースライン）: {_stat_summary(diffs)}\n"
        f"- 勝率（ELEVATE > ベースライン）: {wins}/{runs} = {wins / runs:.1%}\n"
        "- 各 run の成果物・評価記録は `run_NN/` に保存。\n"
    )
    path = out / "measurement.md"
    path.write_text(text)
    print(f"→ 保存: {path}")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except RuntimeError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
