#!/usr/bin/env python
"""examples/idea-levels-ja/* に parameters.md をバックフィルする。

発想レベル実測の実行（examples/_run_idea_levels.sh）は parameters.md 保存対応より前に
始まったため、完了した各レベルに実行時パラメータを追記する。エンジンの
main._save_run_params をそのまま使う（テンプレート一致）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402

LEVELS = ["standard", "very", "extreme"]
TASK = "人類の通勤を完全に廃止する最も過激な方法を提案せよ。既存の枠組みを完全に壊す発想で。"


def run() -> None:
    for level in LEVELS:
        out = Path(__file__).resolve().parent / "idea-levels-ja" / level
        if not (out / "input.md").exists():
            print(f"skip (未完了): {out}")
            continue
        ns = argparse.Namespace(
            out=out,
            command="elevate",
            lang="ja",
            engine="sdk",
            method="two-stage",
            idea_level=level,
            agents=["strategist", "visionary", "storyteller"],
            no_strong_claim=True,
            logic_check=False,
            output_format=None,
            knowledge=None,
            knowledge_file=None,
            ask_knowledge=False,
            rounds=3,
            min_improve=0.01,
            quality_ceiling=0.75,
            runs=1,
            baseline="single",
            evaluate=False,
        )
        main._save_run_params(ns)
    print("DONE backfill")


if __name__ == "__main__":
    run()
