"""elevate-draft-engine 薄い CLI。

使い方:
    python main.py generate "タスク"                 # 素のAI（単発生成）, 1 call
    python main.py diverge "タスク"                  # 8エージェントで草案生成・一覧出力
    python main.py synthesize draft1.md draft2.md  # 外部草案を統合（核心）
    python main.py elevate "タスク"                  # diverge → synthesize 一気
    python main.py compare "タスク"                  # generate vs elevate 両方出力
    python main.py compare "タスク" --evaluate       # + 5軸評価でスコア比較
    python main.py improve "タスク" --rounds 3       # 統合版→改修の草案→統合 のループで反復改善
    python main.py improve "タスク" --rounds 3 --evaluate  # + 各ラウンド採点・頭打ちで早期停止

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
from elevate.engine import _detect_sentimentality


def _build_parser() -> argparse.ArgumentParser:
    # 共通オプションは各サブコマンドの後に置く（親パーサーとして全サブコマンドに共有）。
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--mock", action="store_true", help="API を使わずモックで実行")
    common.add_argument("--engine", default="sdk", choices=["sdk", "claude-code"], help="生成エンジン（既定 sdk。claude-code は claude -p 起動で安定）")
    common.add_argument("--method", default="two-stage", choices=["two-stage", "single-pass"], help="統合方式（既定 two-stage）")
    common.add_argument("--agents", nargs="+", default=None, help="使用するエージェント（既定: 全エージェント）")
    common.add_argument("--out", type=Path, default=None, help="成果物を保存するディレクトリ（省略時は outputs/{タスク名}/ にデフォルト保存）")
    common.add_argument("--no-strong-claim", action="store_true", help="エージェントから「最強の主張」断言枠を除去（アブレーション: 枠あり/なしの統合品質差を測定）")
    common.add_argument("--runs", type=int, default=1, help="compare の比較を N 回反復して統計集計（平均・勝率・標準偏差・95%信頼区間）を出力（既定 1）")
    common.add_argument("--baseline", default="single", choices=["single", "best-of-n"], help="compare の比較対象ベースライン（既定 single: 素の単発生成 / best-of-n: 統合なし最良草案選択＝帰無仮説）")
    common.add_argument("--logic-check", action="store_true", help="最終化の後に論理一貫性の復元工程を適用（統合の多様化への偏りへの収束工程。既定は無効。旧5軸実測由来）")

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

    imp = sub.add_parser(
        "improve", parents=[common],
        help="統合版を反復改善: 統合版→改修の草案(複数)→統合 のループで磨く",
    )
    imp.add_argument("task", help="タスク")
    imp.add_argument("--rounds", type=int, default=3, help="統合を繰り返す回数（既定 3）")
    imp.add_argument("--evaluate", action="store_true", help="各ラウンドの統合版を5軸評価し、改善が頭打ちなら早期停止")
    imp.add_argument("--min-improve", type=float, default=0.01,
                    help="--evaluate 時の早期停止しきい値。直前ラウンドからの overall 改善がこれ未満なら停止（既定 0.01）")
    imp.set_defaults(func=cmd_improve)

    cal = sub.add_parser(
        "calibrate", parents=[common],
        help="温度近似の誤差定量: 同一タスクを複数エンジンでN回生成し、出力の分散を比較",
    )
    cal.add_argument("task", help="タスク")
    cal.add_argument("--engines", nargs="+", default=None,
                    choices=["sdk", "claude-code"],
                    help="比較するエンジン（既定: sdk と claude-code）")
    cal.set_defaults(func=cmd_calibrate)

    return p


# ---- モック（API 不要・パイプライン確認用） ----

_PERSONA_NAME_RE = re.compile(r"You are the \*\*([A-Za-z]+)\*\*")


def _mock_revision_marker(user: str) -> str:
    """改修ラウンド（前回の統合版を磨く）の改善マーカーを返す。

    改修草案を含む user プロンプトを生成する段（推理・最終化・単発統合）が、既に読まれた
    改修度（改修度N）を引き継ぎ +1 して出力に埋め込む。MockEvaluator が統合版に残った
    改修度の最大値で加点するため、統合版が磨かれるごとに overall が上昇し、改善が可視化
    できる（round 1 は改修対象を持たず空文字 → 素の生成と同点）。
    改修ラウンド以外は空文字を返し、モック出力の従来形状を一切変えない。
    """
    if "改修草案" not in user:
        return ""
    prev_core = user.split("改修草案", 1)[1][:40]
    n = user.count("改修度") + 1
    return f" 改修草案の骨子（改修度{n}、{prev_core}…）を統合し、前回の統合版より精緻な解を構成する。"


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
            # 改修ラウンド（round 2 以降）: 前回の統合版の骨子を引き継ぐ改修草案を返す。
            # モック上、統合版を磨くループの「改善の可視化」を再現するマーカーで、既に読まれて
            # いる改修度（改修度N）を引き継ぎ+1して次段へ渡す（実APIの改善過程の決定的な模倣）。
            if "改修対象: 前回の統合版" in user:
                prev_core = user.split("【改修対象: 前回の統合版】", 1)[1].split("。", 1)[0][:40]
                n = user.count("改修度") + 1
                text += f" 改修草案（改修度{n}）として、前回の統合版「{prev_core}…」の骨子を引き継ぎ磨き上げる。"
        # 矛盾解決推理: 長さ基準（最小30字）を満たす推理らしい文を返す
        elif "矛盾解決推理" in system:
            text = (
                "草案間の対立は「価値の最大化と実現性の担保」という軸に集約される。"
                "解決仮説として、まず最小の実現単位で制度に埋め込み、蓄積された実証データで"
                "価値の主張を順次強化する。この統合は単一観点の草案にはない解を構成する。"
            )
            text += _mock_revision_marker(user)
        # それ以外（素の生成・単発統合・矛盾解決推理が system に無い実測・最終化）:
        # 文終端記号で終わる完全な文を返す
        else:
            text = (
                "これは与えられたタスクに対するモックの完全な分析である。"
                "Target は明確であり、Value は実現可能、Risk は具体的な対策とともに示され、"
                "Opportunity は拡張性を持つ。以上が統合された結論である。"
            )
            text += _mock_revision_marker(user)
        # ストリーム追記用: 全文が揃った時点で1回だけ流す（SDK クライアントと同じ動作）
        if on_chunk is not None:
            on_chunk(text)
        return text


class MockEvaluator:
    """評価用のモック。EvaluationEngine と同じプロトコル（EvaluationResult を返す）。

    best-of-n ベースラインが意味を持つよう、成果物テキストごとに決定的に異なるスコアを
    返す（同じテキストなら常に同じ overall）。「モック草案」を含むテキストは、
    エージェント名（全文に現れる）のハッシュで 0.5〜0.9 に分布させる。それ以外の
    （素の生成・統合成果物）は、ポリシー密着5軸（2026-08-08 再調整(3)）に合わせ
    「普通」を 0.60 に置く。さらに improve の改修ラウンド（統合版を磨く）を再現する
    ため、統合版に残った改修度（改修度N）で加点し 0.72（改修度3）で頭打ちにする——
    素の生成相当（round 1）→ 統合版が磨かれるごとに上昇 → 頭打ち、と改善の推移が
    決定的に可視化できる（5軸とも同一 base のため overall = base）。
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
            scores = {"diversity": base, "synthesis": base, "elevation": base, "honesty": base, "utility": base}
        else:
            # 素の生成・統合成果物: 「普通」=0.60。統合版に残った改修度（改修度N）で加点し、
            # 改修度3で頭打ち → 素の生成相当（round 1）→ 統合版が磨かれるごとに上昇 → 頭打ち。
            degrees = [int(m) for m in re.findall(r"改修度(\d+)", system)]
            base = 0.60 + 0.04 * min(max(degrees, default=0), 3)  # 0.60〜0.72
            scores = {"diversity": base, "synthesis": base, "elevation": base, "honesty": base, "utility": base}
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
    engine_args = {
        "strong_claim_frame": not args.no_strong_claim,
        "enable_logic_check": getattr(args, "logic_check", False),
    }
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
    感情の道具化ガード（soft）: 型通りの感情定式を検出したら警告を出す（再生成はしない）。
    """
    if _detect_sentimentality(draft.content):
        print(
            f"⚠ 感傷性の警告（{draft.agent}）: 型通りの感情定式（末期×高齢×見捨て 等）を検出。"
            "抑制と余白で深みを確認してください。",
            file=sys.stderr,
        )
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


def _sd(vals: list[float]) -> float:
    """標本標準偏差（n-1）。"""
    n = len(vals)
    if n < 2:
        return 0.0
    mean = sum(vals) / n
    var = sum((x - mean) ** 2 for x in vals) / (n - 1)
    return var ** 0.5


def _stat_summary(scores: list[float]) -> str:
    """平均・標準偏差（標本分散, n-1）・件数の集計文字列。"""
    n = len(scores)
    mean = sum(scores) / n
    return f"mean={mean:.3f} sd={_sd(scores):.3f}（n={n}）"


# 両側95% t 臨界値（df=1..20。それ以上は正規近似 1.96）。
# 比較 run は小標本（n=1〜10 が典型）のため、分散に不確実性を持つ小標本では
# 正規近似より t 分布の方が区間を正直に広げる。
_T_0_975 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
    16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
}


def _mean_confidence_interval(scores: list[float]) -> tuple[float, float]:
    """平均の 95% 信頼区間（両側）。小標本は t 分布、n=1 は区間が開かない。"""
    n = len(scores)
    if n < 1:
        return (float("nan"), float("nan"))
    if n == 1:
        return (scores[0], scores[0])
    mean = sum(scores) / n
    se = _sd(scores) / (n ** 0.5)
    t = _T_0_975.get(n - 1, 1.96)
    return (mean - t * se, mean + t * se)


def _wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """勝率の Wilson score 区間（95%）。n=1 では区間が意味を持たない（0 か 1 に張る）。"""
    if n < 1:
        return (float("nan"), float("nan"))
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def _cohens_d(baseline: list[float], elevated: list[float]) -> float:
    """統合 vs ベースラインの平均差の効果量（プール標準偏差で正規化）。"""
    n1, n2 = len(baseline), len(elevated)
    if n1 < 2 or n2 < 2:
        return float("nan")
    m1, m2 = sum(baseline) / n1, sum(elevated) / n2
    v1 = sum((x - m1) ** 2 for x in baseline) / (n1 - 1)
    v2 = sum((x - m2) ** 2 for x in elevated) / (n2 - 1)
    sp = (( (n1 - 1) * v1 + (n2 - 1) * v2 ) / (n1 + n2 - 2)) ** 0.5
    if sp == 0:
        return float("nan")
    return (m2 - m1) / sp


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
    preservation_rates: list[float] = []
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

        # 具体性保存指数: 発散草案の具体トークンが統合成果物に残存する割合（--evaluate 時のみ集計）
        if args.evaluate:
            from evaluation.specificity import compute_preservation_rate

            pres = compute_preservation_rate(drafts, elevated)
            if pres["preservation_rate"] is not None:
                preservation_rates.append(pres["preservation_rate"])

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
        wlo, whi = _wilson_interval(wins, runs)
        summary_lines.append(f"  勝率 95%CI（Wilson）: {wlo:.1%}〜{whi:.1%}")
        dlo, dhi = _mean_confidence_interval(diffs)
        summary_lines.append(f"  差の 95%CI（t, 両側）: {dlo:+.3f}〜{dhi:+.3f}")
        d = _cohens_d(baseline_scores, elevated_scores)
        summary_lines.append(f"  効果量（Cohen's d）: {d:+.2f}")
        if preservation_rates:
            pmean = sum(preservation_rates) / len(preservation_rates)
            summary_lines.append(
                f"具体性保存率（発散→統合）: mean={pmean:.1%}（n={len(preservation_rates)}）"
            )
        for line in summary_lines:
            print(line)
        if args.out is not None:
            _save_measurement(
                args.out, baseline_label, baseline_scores, elevated_scores, wins, runs,
                preservation_rates=preservation_rates,
            )


def _save_baseline_score_record(path: Path, label: str, overall: float, evaluator) -> None:
    """best-of-n ベースラインの選択時スコア記録（再評価はしない）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"## {label}\n"
        f"- overall: {overall:.3f}（{evaluator.score_judgment(overall)}）\n"
        "- スコア: 最良草案の選択時評価をそのまま使用（選択を再評価で上書きしない）\n"
    )
    print(f"→ 保存: {path}")


# ---- 反復改善（improve: 統合版を改修草案で磨くループ） ----

def _revision_task(task: str, elevated_prev: str) -> str:
    """前回の統合版を改修する草案のタスクを組み立てる。

    「統合版 → 改修の草案(複数) → 統合」ループの「改修草案」段階。
    各エージェントは前回の統合版を土台に、自分の観点から改修草案を書く。
    統合版の良い部分（特に他観点にはない独自の核）は残し、弱点を補強し、
    前回より高い版を目指す。草案は統合段階で他の改修草案と衝突させる前提なので独立に書く。
    """
    return (
        f"{task}\n\n"
        f"【改修対象: 前回の統合版】\n{elevated_prev}\n\n"
        "あなたはこの統合版を土台に、自分の観点から改修した草案を書く。\n"
        "既にある良い部分（特に、他の観点にはない独自の核）は残し、\n"
        "弱点や欠けている視点を補強し、前回より高い版を目指すこと。\n"
        "草案は統合段階で他の改修草案と衝突させる前提なので、独立して書くこと。"
    )


def cmd_improve(args: argparse.Namespace) -> None:
    """統合版を反復改善する: 統合版 → 改修の草案(複数) → 統合 のループ。

    知恵の評議会の preserve「発散が持つ感情・意味の真実が統合を生き延びる」への対応。
    初回はオリジナルタスクから発散 → 統合で統合版を作り、2回目以降は
    「前回の統合版を改修する草案」を各エージェントが書き、それを統合して次の統合版にする。
    統合版の成果がループを回すごとに相続・改善されていく。

    --evaluate を付けると各ラウンドの統合版を採点し、改善がしきい値（--min-improve）未満に
    なったら早期停止する（過修正で元の良さを失わせない）。
    """
    task = args.task
    _resolve_out(args, task)
    engine = _make_engine(args)
    _save_input(args, task)

    rounds = max(1, args.rounds)
    elevated_prev: str | None = None
    progress: list[dict] = []

    for r in range(1, rounds + 1):
        round_args = args
        if rounds > 1 and args.out is not None:
            rd = args.out / f"round_{r:02d}"
            rd.mkdir(parents=True, exist_ok=True)
            round_args = argparse.Namespace(**vars(args))
            round_args.out = rd

        if elevated_prev is None:
            # 初回: オリジナルタスクから発散 → 統合
            draft_task = task
        else:
            # 2回目以降: 統合版 → 改修の草案(複数)。前回の統合版を土台に改修草案を書かせる
            draft_task = _revision_task(task, elevated_prev)

        drafts = engine.diverge(
            draft_task, agents=args.agents, draft_dir=round_args.out,
            on_draft=lambda d: _report_draft(round_args, d),
        )
        reconciliation, elevated = engine.synthesize_with_reconciliation(
            drafts, method=args.method, task=task
        )
        if reconciliation:
            _save(round_args, "reconciliation", reconciliation)

        print(f"[round {r}/{rounds}] 統合版 {len(elevated)} 字")
        _save(round_args, "elevated", elevated)

        entry = {"round": r, "length": len(elevated)}
        if args.evaluate:
            evaluator = _make_evaluator(args)
            result = _evaluate_and_report(
                f"round {r} 統合版", elevated, task, evaluator,
                save_to=round_args.out / "evaluation.md" if round_args.out else None,
            )
            entry["overall"] = result.overall
        progress.append(entry)

        if args.evaluate and len(progress) >= 2:
            gain = entry["overall"] - progress[-2]["overall"]
            if gain < args.min_improve:
                print(
                    f"→ round {r}: 改善 {gain:+.3f} < しきい値 {args.min_improve}"
                    " → 頭打ちと判断し停止（過修正を避ける）"
                )
                break
        elevated_prev = elevated

    _save_progress(args.out, task, progress, evaluate=args.evaluate)


def _save_progress(out: Path | None, task: str, progress: list[dict], *, evaluate: bool) -> None:
    """各ラウンドの統合版の長さ・評価（progress.md）を保存する。"""
    if out is None:
        return
    out.mkdir(parents=True, exist_ok=True)
    lines = [
        "# 反復改善の記録（improve）",
        "",
        f"タスク: {task}",
        "",
    ]
    if evaluate:
        lines.append("| round | 統合版の長さ | overall | 前回からの改善 |")
        lines.append("|---|---|---|---|")
        for i, e in enumerate(progress):
            gain = "" if i == 0 else f"{e['overall'] - progress[i - 1]['overall']:+.3f}"
            lines.append(f"| {e['round']} | {e['length']} | {e['overall']:.3f} | {gain} |")
    else:
        lines.append("| round | 統合版の長さ |")
        lines.append("|---|---|")
        for e in progress:
            lines.append(f"| {e['round']} | {e['length']} |")
    lines += [
        "",
        "各ラウンドの成果物は `round_NN/` に保存（draft_* / reconciliation / elevated）。",
        "round 2 以降は「前回の統合版 → 改修の草案 → 統合」のループで、",
        "改修草案を統合して次の統合版を作る（統合版の成果が相続される）。",
    ]
    path = out / "progress.md"
    path.write_text("\n".join(lines) + "\n")
    print(f"→ 保存: {path}")


def _save_measurement(
    out: Path, baseline_label: str, baseline_scores: list[float],
    elevated_scores: list[float], wins: int, runs: int,
    *,
    preservation_rates: list[float] | None = None,
) -> None:
    """比較の統計集計（measurement.md）を --out 直下に保存する。"""
    out.mkdir(parents=True, exist_ok=True)
    diffs = [e - b for b, e in zip(baseline_scores, elevated_scores)]
    wlo, whi = _wilson_interval(wins, runs)
    dlo, dhi = _mean_confidence_interval(diffs)
    d = _cohens_d(baseline_scores, elevated_scores)
    text = (
        f"# 比較計測（--runs {runs}）\n\n"
        f"- {baseline_label}: {_stat_summary(baseline_scores)}\n"
        f"- ELEVATE:            {_stat_summary(elevated_scores)}\n"
        f"- 差（ELEVATE−ベースライン）: {_stat_summary(diffs)}\n"
        f"- 勝率（ELEVATE > ベースライン）: {wins}/{runs} = {wins / runs:.1%}\n"
        f"  - 勝率 95%CI（Wilson）: {wlo:.1%}〜{whi:.1%}\n"
        f"  - 差の 95%CI（t, 両側）: {dlo:+.3f}〜{dhi:+.3f}\n"
        f"  - 効果量（Cohen's d）: {d:+.2f}\n"
    )
    if preservation_rates:
        pmean = sum(preservation_rates) / len(preservation_rates)
        text += (
            f"- 具体性保存率（発散→統合）: mean={pmean:.1%}"
            f"（n={len(preservation_rates)}）\n"
        )
    text += "- 各 run の成果物・評価記録は `run_NN/` に保存。\n"
    text += (
        "\n> 知恵の評議会の指摘（discovery_target）: 統合優位性は n≥10 の実測で"
        "立証せよ。勝率が 50% を下回るタスクの開示こそが誠実な主張になる。\n"
    )
    path = out / "measurement.md"
    path.write_text(text)
    print(f"→ 保存: {path}")


# ---- 温度近似の誤差定量（calibrate） ----

_TYPE_TOKEN_RE = re.compile(r"[^\s]+")


def _text_features(text: str) -> dict:
    """出力テキストの粗い特徴量: 長さ・語彙多様性（type-token比）・見出し構成。

    claude-code エンジンは温度をシステムプロンプトの指示文で近似するため、
    SDK 直呼びと比べて出力の分散がどう変わるかを観測する道具。
    """
    tokens = _TYPE_TOKEN_RE.findall(text)
    length = len(text)
    ttr = (len(set(tokens)) / len(tokens)) if tokens else 0.0
    headings = re.findall(r"^#{1,6}\s+.*$", text, flags=re.MULTILINE)
    return {
        "length": length,
        "type_token_ratio": round(ttr, 4),
        "heading_count": len(headings),
    }


def cmd_calibrate(args: argparse.Namespace) -> None:
    """同一タスクを複数エンジンでN回生成し、出力分散の違いを定量化する。

    知恵の評議会の指摘「温度近似の誤差を定量化せよ」への回答。温度は数値として
    再現されない（claude-code はプロンプト指示で近似）ため、その近似が出力の
    長さ・語彙多様性・構造にどれだけの差として現れるかを実測する。
    """
    engines = args.engines or ["sdk", "claude-code"]
    runs = max(1, args.runs)
    engine_results: dict[str, list[dict]] = {}
    for engine in engines:
        if args.mock:
            gen = MockGenerator()
        elif engine == "claude-code":
            from adapters.claude_code_client import ClaudeCodeClient

            gen = ClaudeCodeClient()
        else:
            from adapters.claude_client import ClaudeClient

            gen = ClaudeClient()
        engine_result: list[dict] = []
        for _ in range(runs):
            engine_result.append(_text_features(gen.generate(
                "あなたは経験豊富な企画コンサルタントである。",
                args.task,
                temperature=0.7,
            )))
        engine_results[engine] = engine_result
        print(f"[{engine}] 完了（n={runs}）")

    _save_calibration(args.out, args.task, engines, engine_results)


def _save_calibration(
    out: Path | None, task: str, engines: list[str],
    results: dict[str, list[dict]],
) -> None:
    """キャリブレーション結果（calibration.md）を --out 直下に保存する。"""
    out_dir = out or Path("outputs") / _task_dirname(task)
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# 温度近似の誤差定量（calibrate）",
        "",
        f"タスク: {task}",
        f"生成エンジン: {', '.join(engines)}",
        "",
        "| エンジン | n | 長さ mean | 長さ sd | type-token比 mean | 見出し数 mean |",
        "|---------|---|----------|---------|-------------------|---------------|",
    ]
    for engine in engines:
        rs = results[engine]
        lens = [r["length"] for r in rs]
        ttrs = [r["type_token_ratio"] for r in rs]
        heads = [r["heading_count"] for r in rs]
        lines.append(
            f"| {engine} | {len(rs)} | {sum(lens) / len(lens):.0f} | "
            f"{_sd([float(x) for x in lens]):.1f} | "
            f"{sum(ttrs) / len(ttrs):.3f} | {sum(heads) / len(heads):.1f} |"
        )
    lines += [
        "",
        "> 温度は claude-code エンジンではシステムプロンプトの指示文で近似される"
        "（数値としての再現性はない）。上の分散が近似の誤差の実測である。",
    ]
    path = out_dir / "calibration.md"
    path.write_text("\n".join(lines) + "\n")
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
