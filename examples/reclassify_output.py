#!/usr/bin/env python3
"""compare/improve の出力をカテゴリ分類（drafts/evaluations/artifacts）に再構成する。

2026-08-09 の出力分類変更（ユーザー指示: フラットな出力を種類ごとのフォルダに分類）以前に
保存されたフラットな出力ディレクトリを、新しいレイアウト
（run_NN/ round_NN/ 内を drafts/ | evaluations/ | artifacts/ に分類）に揃えるマイグレーション。
compare（run_NN/）と improve（round_NN/）の両方に対応する。
再実行しても安全（既に分類済みのファイルはスキップする冪等設計）。

使い方:
    python examples/reclassify_output.py examples/ledger-2agents examples/lyrics-improve ...
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

# カテゴリ → ファイル名の判定。input.md / comparison.* / measurement.md / progress.md 等は
# 上位（--out 直下）に置くため触らない。
_CATEGORIES = {
    "drafts": lambda name: name.startswith("draft"),
    "evaluations": lambda name: name.startswith("evaluation"),
    "artifacts": lambda name: name in {"reconciliation.md", "elevated.md", "raw.md", "best_single.md"},
}


def _reclassify_dir(step_dir: Path) -> list[Path]:
    """1つの run_NN/ round_NN/ 内のフラットなファイルをカテゴリ別サブフォルダへ移動。"""
    moved: list[Path] = []
    for f in sorted(step_dir.iterdir()):
        if not f.is_file() or f.name.startswith("."):
            continue
        target = None
        for cat, pred in _CATEGORIES.items():
            if pred(f.name):
                target = step_dir / cat
                break
        if target is None:
            continue  # 上位に置くファイル（input.md 等）は触らない
        dest = target / f.name
        target.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            continue  # 既に分類済み（冪等）
        shutil.move(str(f), str(dest))
        moved.append(dest)
    return moved


def reclassify(out_dir: Path) -> list[Path]:
    """出力ディレクトリ直下の run_NN/ round_NN/ を再構成し、移動したファイルを返す。"""
    out_dir = out_dir.resolve()
    steps = sorted(
        p for p in out_dir.iterdir()
        if p.is_dir() and re.fullmatch(r"(?:run|round)_\d+", p.name)
    )
    moved: list[Path] = []
    for step in steps:
        moved.extend(_reclassify_dir(step))
    return moved


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="compare/improve 出力をカテゴリ分類レイアウトへ再構成")
    p.add_argument("out_dirs", nargs="+", type=Path, help="出力ディレクトリ（compare/improve の --out）")
    args = p.parse_args(argv)

    total = 0
    for d in args.out_dirs:
        moved = reclassify(d)
        for m in moved:
            print(f"→ 移動: {m}")
        total += len(moved)
    print(f"再構成完了: {total} ファイルを移動")
    return 0


if __name__ == "__main__":
    sys.exit(main())
