"""サンプル行列の進行確認と打ち切り判定。

各ドメインの measurement.md を集計し、統合が素AI生成を上回っているかを
事前登録した規則で判定する（停止バイアスを防ぐため、基準はデータを見る前に固定）。

打ち切り規則（ユーザー承認済み・2026-08-08 中立ベースラインで再登録）:
    完了済み run の累積勝率 ≤ 50% かつ ELEVATE 平均差 ≤ 0 → 残りの行列を打ち切り。
    規則はデータを見る前に固定する（停止バイアス防止）。

再登録（2026-08-08）: 素の生成ベースラインを中立化（ANALYSIS_SYSTEM が複数視点を
誘引しないように修正）したため、旧設計の測定（knowledge-search 等）は混ぜない。
比較対象ドメインは --domains で明示する。

使い方:
    python examples/check_matrix_progress.py                    # 全ドメインを集計して判定
    python examples/check_matrix_progress.py --domains A B C   # 指定ドメインのみ集計
    python examples/check_matrix_progress.py --json            # 機械可読な結果
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parent


def _parse_measurement(path: Path) -> dict | None:
    text = path.read_text()
    diff = re.search(r"差（ELEVATE−ベースライン）: mean=([+-]?\d+\.\d+)", text)
    win = re.search(r"勝率（ELEVATE > ベースライン）: (\d+)/(\d+)", text)
    if not (diff and win):
        return None
    return {
        "domain": path.parent.name,
        "mean_diff": float(diff.group(1)),
        "wins": int(win.group(1)),
        "runs": int(win.group(2)),
    }


def collect(domains: list[str] | None = None) -> list[dict]:
    rows = []
    for md in sorted(EXAMPLES.glob("*/measurement.md")):
        if domains and md.parent.name not in domains:
            continue  # 新設計の行列ドメインのみ集計（旧設計の測定を混ぜない）
        row = _parse_measurement(md)
        if row:
            rows.append(row)
    return rows


def decide(rows: list[dict]) -> dict:
    total_runs = sum(r["runs"] for r in rows)
    total_wins = sum(r["wins"] for r in rows)
    n = len(rows)
    win_rate = total_wins / total_runs if total_runs else 0.0
    mean_diff = sum(r["mean_diff"] for r in rows) / n if n else 0.0
    stop = n > 0 and win_rate <= 0.50 and mean_diff <= 0.0
    return {
        "domains": n,
        "runs": total_runs,
        "wins": total_wins,
        "win_rate": win_rate,
        "mean_diff": mean_diff,
        "stop": stop,
        "reason": (
            f"累積勝率 {win_rate:.1%} / 平均差 {mean_diff:+.3f} → "
            + ("打ち切り（優位性なし）" if stop else "継続")
        ),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="行列の進行確認と打ち切り判定")
    p.add_argument(
        "--domains", nargs="*", default=None,
        help="集計対象ドメイン（例: ledger-2agents ledger-4agents ml-hypothesis）。省略時は全ドメイン",
    )
    p.add_argument("--json", action="store_true", help="機械可読な結果")
    args = p.parse_args(argv)

    rows = collect(args.domains)
    summary = decide(rows)
    if args.json:
        print(json.dumps({"rows": rows, **summary}, ensure_ascii=False, indent=2))
        return 0

    print(f"完了ドメイン: {summary['domains']} / 累計 run: {summary['runs']}（勝ち {summary['wins']}）")
    for r in rows:
        print(f"  {r['domain']:<20} 差={r['mean_diff']:+.3f}  勝率={r['wins']}/{r['runs']}")
    print(summary["reason"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
