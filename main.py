"""elevate-draft-engine 薄い CLI。

使い方:
    python main.py generate "タスク"                 # 素のAI（B0相当）, 1 call
    python main.py diverge "タスク"                  # 8エージェントで草案生成・一覧出力
    python main.py synthesize draft1.txt draft2.txt  # 外部草案を統合（核心）
    python main.py elevate "タスク"                  # diverge → synthesize 一気
    python main.py compare "タスク"                  # generate vs elevate 両方出力
    python main.py compare "タスク" --evaluate       # + 5軸評価でスコア比較

共通オプション:
    --mock                API 不要のモックで実行（パイプライン確認用）
    --method m2v2|m2      統合方式（既定 m2v2: 矛盾解決推理→最終化）
    --agents 名前...      使用するエージェントを限定（既定: 全8エージェント）
    --out DIR             成果物をファイル保存（elevate/compare は各草案 draft_{agent}.txt も保存）

認証: ANTHROPIC_API_KEY（通常）または ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL（ゲートウェイ）。
スロットル（空応答対策）は既定 2 秒（CLAUDE_MIN_INTERVAL_SECONDS で変更可）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from elevate import Draft, DraftEngine
from elevate.engine import load_agents


def _build_parser() -> argparse.ArgumentParser:
    # 共通オプションは各サブコマンドの後に置く（親パーサーとして全サブコマンドに共有）。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--mock", action="store_true", help="API を使わずモックで実行")
    common.add_argument("--engine", default="sdk", choices=["sdk", "claude-code"], help="生成エンジン（既定 sdk。claude-code は claude -p 起動で安定）")
    common.add_argument("--method", default="m2v2", choices=["m2v2", "m2"], help="統合方式（既定 m2v2）")
    common.add_argument("--agents", nargs="+", default=None, help="使用するエージェント（既定: 全エージェント）")
    common.add_argument("--out", type=Path, default=None, help="成果物を保存するディレクトリ")

    p = argparse.ArgumentParser(
        prog="elevate-draft-engine",
        description="複数の独立した草案を統合して一段高い成果物を生むエンジン",
    )
    sub = p.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", parents=[common], help="素のAI（B0相当）で1回生成")
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
    c.set_defaults(func=cmd_compare)

    return p


# ---- モック（API 不要・パイプライン確認用） ----

# agents/*.md の本文をシステムプロンプトとして、エージェント草案を識別する
_AGENTS = load_agents()
_AGENT_BY_PROMPT = {prompt: name for name, prompt in _AGENTS.items()}


class MockGenerator:
    """決定的なモック応答を返す。完全性ガードを通過する文形にしている。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, float | None]] = []

    def generate(self, system: str, user: str, *, temperature: float | None = None) -> str:
        self.calls.append((system, user, temperature))
        # エージェント草案: 観点名を込めたモック草案を返す
        if system in _AGENT_BY_PROMPT:
            name = _AGENT_BY_PROMPT[system]
            return f"これはエージェント「{name}」からのモック草案である。{name}らしい観点で描かれている。"
        # 矛盾解決推理: 長さ基準（最小30字）を満たす推理らしい文を返す
        if "矛盾解決推理" in system:
            return (
                "草案間の対立は「価値の最大化と実現性の担保」という軸に集約される。"
                "解決仮説として、まず最小の実現単位で制度に埋め込み、蓄積された実証データで"
                "価値の主張を順次強化する。この統合を経て、単一観点では見えなかった"
                "第3の位置が得られる。"
            )
        # それ以外（素の生成・単発統合・最終化）: 文終端記号で終わる完全な文を返す
        return (
            "これは与えられたタスクに対するモックの完全な分析である。"
            "Target は明確であり、Value は実現可能、Risk は具体的な対策とともに示され、"
            "Opportunity は拡張性を持つ。以上が統合された結論である。"
        )


class MockEvaluator:
    """評価用のモック。EvaluationEngine と同じプロトコル（EvaluationResult を返す）。"""

    def __init__(self) -> None:
        self.calls: list[int] = []

    def evaluate(self, system: str, user: str) -> "EvaluationResult":
        from evaluation.evaluator import EvaluationResult, compute_overall

        self.calls.append(1)
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
    if args.mock:
        return DraftEngine(MockGenerator())
    if args.engine == "claude-code":
        # claude -p 経由（wisdom-council 方式の独立起動）。ゲートウェイ空応答に強い。
        from adapters.claude_code_client import ClaudeCodeClient

        return DraftEngine(ClaudeCodeClient())
    from adapters.claude_client import ClaudeClient

    return DraftEngine(ClaudeClient())


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


def _save(args: argparse.Namespace, name: str, text: str) -> None:
    if args.out is None:
        return
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{name}.txt"
    path.write_text(text)
    print(f"→ 保存: {path}")


def _save_input(args: argparse.Namespace, task: str) -> None:
    """タスクを input.md として保存（examples/ の体裁: wisdom-council 風）。"""
    if args.out is None:
        return
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "input.md"
    path.write_text(f"# タスク\n\n{task}\n")
    print(f"→ 保存: {path}")


def cmd_generate(args: argparse.Namespace) -> None:
    engine = _make_engine(args)
    _print_artifact("素の生成（B0相当）", engine.generate(args.task))


def cmd_diverge(args: argparse.Namespace) -> None:
    engine = _make_engine(args)
    drafts = engine.diverge(args.task, agents=args.agents)
    for draft in drafts:
        _print_artifact(f"草案: {draft.agent}", draft.content)
        _save(args, f"draft_{draft.agent}", draft.content)


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
    engine = _make_engine(args)
    _save_input(args, args.task)
    drafts = engine.diverge(args.task, agents=args.agents)
    for draft in drafts:
        _save(args, f"draft_{draft.agent}", draft.content)
    reconciliation, elevated = engine.synthesize_with_reconciliation(
        drafts, method=args.method, task=args.task
    )
    if reconciliation:
        _save(args, "reconciliation", reconciliation)
    _print_artifact(f"エレベート成果物（{args.method}）", elevated)
    _save(args, "elevated", elevated)


def _evaluate_and_report(label: str, artifact: str, task: str, evaluator) -> None:
    result = evaluator.evaluate(artifact, task)
    print(f"[{label}] overall={result.overall:.3f}（{evaluator.score_judgment(result.overall)}）")
    for k, v in result.scores.items():
        print(f"    {k}: {v:.2f}")
    print()


def cmd_compare(args: argparse.Namespace) -> None:
    engine = _make_engine(args)
    task = args.task
    _save_input(args, task)
    raw = engine.generate(task)
    drafts = engine.diverge(task, agents=args.agents)
    for draft in drafts:
        _save(args, f"draft_{draft.agent}", draft.content)
    reconciliation, elevated = engine.synthesize_with_reconciliation(
        drafts, method=args.method, task=task
    )
    if reconciliation:
        _save(args, "reconciliation", reconciliation)
    _print_artifact("素の生成（B0相当）", raw)
    _print_artifact(f"エレベート成果物（{args.method}）", elevated)
    _save(args, "raw", raw)
    _save(args, "elevated", elevated)
    if args.evaluate:
        evaluator = _make_evaluator(args)
        _evaluate_and_report("B0（素の生成）", raw, task, evaluator)
        _evaluate_and_report("ELEVATE", elevated, task, evaluator)


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
