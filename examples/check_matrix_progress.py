"""サンプル行列の進行確認と打ち切り判定。

各ドメインの measurement.md を集計し、統合が素AI生成を上回っているかを
事前登録した規則で判定する（停止バイアスを防ぐため、基準はデータを見る前に固定）。

打ち切り規則（ユーザー承認済み・2026-08-08 中立ベースラインで再登録）:
    完了済み run の累積勝率 ≤ 50% かつ ELEVATE 平均差 ≤ 0 → 残りの行列を打ち切り。
    規則はデータを見る前に固定する（停止バイアス防止）。

再登録（2026-08-08）: 素の生成ベースラインを中立化（ANALYSIS_SYSTEM が複数視点を
誘引しないように修正）したため、旧設計の測定（knowledge-search 等）は混ぜない。
比較対象ドメインは --domains で明示する。

再登録（2026-08-11・多言語行列の開始）: ユーザー承認により en/ja/zh の
morning-routine ドメイン（examples/i18n/morning-compare-{en,ja,zh}/measurement.md、
各 n=1 の単一 run）を行列に統合する。測定ラベルは言語別（ja/en/zh）のため
パーサーを多言語対応にし、i18n/ 配下も走査する。n=1 のため CI・効果量は含まれず、
累積勝率・平均差のみで規則を適用する（独立run前提の統計とは別物）。

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


# 測定ラベルは言語で異なる（measurement.md は compare --lang のロケールで書かれる）。
# 差（ELEVATE−ベースライン）/ Difference (ELEVATE − baseline) / 差值（ELEVATE−基线）
_DIFF_RE = re.compile(r"(?:差|Difference|差值)[^:：]*[:：]\s*mean=([+-]?\d+\.\d+)")
# 勝率（ELEVATE > ベースライン）/ Win rate (ELEVATE > baseline) / 胜率（ELEVATE > 基线）
_WIN_RE = re.compile(r"(?:勝率|Win rate|胜率)[^:：]*[:：]\s*(\d+)/(\d+)")


def _parse_measurement(path: Path) -> dict | None:
    text = path.read_text()
    diff = _DIFF_RE.search(text)
    win = _WIN_RE.search(text)
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
    # 行列ドメインは examples/<domain>/、多言語検証は examples/i18n/<domain>/ に保存される
    candidates = list(EXAMPLES.glob("*/measurement.md")) + list(EXAMPLES.glob("i18n/*/measurement.md"))
    for md in sorted(candidates):
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
