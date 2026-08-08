"""比較ドキュメント生成: compare の出力ディレクトリから「素AI生成 vs 昇華版」を読める形に。

知恵の評議会の「昇華優位性の実証」は、統計（CI）だけでなく、実際の成果物で
素AI生成と昇華版を並べて人間が客観的に読めること自体が目的である。

compare は run ごとに raw.md（素AI生成）と elevated.md（昇華版）を保存する
（--runs>1 なら run_NN/ サブフォルダ）。このスクリプトはそれらを1つの
comparison.md に束ね、スコア表つきで「どちらが読んでいて優れているか」を
人間が判断できる形にする。

使い方:
    python render_comparison.py examples/<sample_dir>            # 比較ドキュメントを生成
    python render_comparison.py examples/<sample_dir> --html     # HTML版も生成（横並び表示）
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def _read(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def _find_runs(out_dir: Path) -> list[Path]:
    """run_NN/ サブフォルダのリスト（昇順）。なければ [out_dir] を返す（--runs 1）。"""
    runs = sorted([p for p in out_dir.iterdir() if p.is_dir() and re.fullmatch(r"run_\d+", p.name)])
    return runs or [out_dir]


def _score_table(measurement: str) -> str:
    """measurement.md のスコア表ブロックを抽出して返す（無ければ空文字）。"""
    m = re.search(r"## 結果\n(.*?)(?:\n## |\n$)", measurement, re.S)
    if not m:
        # 新形式（--runs>1 の比較集計）: 集計行を取り出す
        lines = [ln for ln in measurement.splitlines() if "95%CI" in ln or "効果量" in ln or "保存率" in ln]
        return "\n".join(lines)
    return m.group(1).strip()


def _run_block(run_dir: Path, idx: int) -> list[str]:
    """1 run 分の比較ブロック（素AI生成と昇華版を並べて読める形）を組み立てる。"""
    raw = _read(run_dir / "raw.md").strip()
    elevated = _read(run_dir / "elevated.md").strip()
    baseline_eval = _read(run_dir / "evaluation_baseline.md").strip()
    elevated_eval = _read(run_dir / "evaluation_elevated.md").strip()

    lines: list[str] = []
    if not raw and not elevated:
        return lines
    lines.append(f"## run {idx}")
    lines.append("")
    if baseline_eval:
        lines.append(f"**素AI生成の評価**\n\n```\n{baseline_eval}\n```")
    if elevated_eval:
        lines.append(f"**昇華版の評価**\n\n```\n{elevated_eval}\n```")
    if raw and elevated:
        lines.append(
            "### 素AI生成（raw.md）\n\n<details><summary>読む（クリックで展開）</summary>\n\n```markdown\n"
            + raw
            + "\n```\n\n</details>"
        )
        lines.append(
            "### 昇華版（elevated.md）\n\n<details><summary>読む（クリックで展開）</summary>\n\n```markdown\n"
            + elevated
            + "\n```\n\n</details>"
        )
    elif raw:
        lines.append(f"### 素AI生成（raw.md）\n\n```markdown\n{raw}\n```")
    elif elevated:
        lines.append(f"### 昇華版（elevated.md）\n\n```markdown\n{elevated}\n```")
    lines.append("")
    return lines


def render(out_dir: Path, task: str | None = None) -> str:
    """out_dir の compare 出力から comparison.md の本文を生成する。"""
    out_dir = out_dir.resolve()
    input_md = _read(out_dir / "input.md")
    if not task:
        m = re.search(r"# タスク\n\n(.+)", input_md)
        task = m.group(1).strip() if m else out_dir.name

    measurement = _read(out_dir / "measurement.md")
    score_block = _score_table(measurement) if measurement else ""

    lines = [
        "# 比較: 素AI生成 vs 昇華版",
        "",
        f"**タスク**: {task}",
        f"**保存先**: `{out_dir}`",
        "",
        "> このドキュメントは「統合優位性の実証」の材料である。**結論は数値が下すのではなく、",
        "> あなたが両方を読んで判断する。** 数値は客観視のための補助であり、単発生成（約1回）と",
        "> 統合（8草案×温度0.7→推理→最終化、約10回）はコストが桁違いに異なる点に注意せよ。",
    ]
    if measurement:
        lines += [
            "",
            "## 計測サマリ",
            "",
            f"```\n{measurement.strip()}\n```",
        ]
    if score_block:
        lines += ["", "### スコア", "", score_block, ""]

    for idx, run_dir in enumerate(_find_runs(out_dir), start=1):
        lines += _run_block(run_dir, idx)

    return "\n".join(lines)


def _html_of(md: str) -> str:
    """Markdown の比較ドキュメントから横並びHTMLを生成する（ブラウザで客観視用）。

    完全なMarkdownパーサーは持たない。run ブロックの「素AI生成」/「昇華版」を
    2カラムに並べる軽量変換のみを行う。
    """
    from html import escape

    runs: list[tuple[str, str]] = []
    cur_raw: list[str] = []
    cur_elev: list[str] = []
    in_raw = in_elev = False
    for line in md.splitlines():
        if line.startswith("### 素AI生成（raw.md）"):
            in_raw, in_elev = True, False
            cur_raw, cur_elev = [], []
            continue
        if line.startswith("### 昇華版（elevated.md）"):
            in_raw, in_elev = False, True
            continue
        if line.startswith("## ") or line.startswith("# "):
            if cur_raw or cur_elev:
                runs.append(("\n".join(cur_raw), "\n".join(cur_elev)))
            in_raw = in_elev = False
            continue
        if in_raw:
            cur_raw.append(line)
        elif in_elev:
            cur_elev.append(line)
    if cur_raw or cur_elev:
        runs.append(("\n".join(cur_raw), "\n".join(cur_elev)))

    cards = []
    for i, (raw, elev) in enumerate(runs, start=1):
        cards.append(
            f"""
<h2>run {i}</h2>
<div style="display:flex;gap:1em;flex-wrap:wrap;">
  <div style="flex:1;min-width:320px;border:1px solid #ccc;padding:1em;">
    <h3 style="color:#a33;">素AI生成</h3>
    <pre style="white-space:pre-wrap;font-family:inherit;">{escape(raw.strip())}</pre>
  </div>
  <div style="flex:1;min-width:320px;border:1px solid #ccc;padding:1em;">
    <h3 style="color:#3a3;">昇華版</h3>
    <pre style="white-space:pre-wrap;font-family:inherit;">{escape(elev.strip())}</pre>
  </div>
</div>"""
        )
    return f"<!doctype html><html><body>{''.join(cards)}</body></html>"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="compare 出力から比較ドキュメントを生成")
    p.add_argument("out_dir", type=Path, help="compare の出力ディレクトリ")
    p.add_argument("--task", default=None, help="タスク名（省略時は input.md から読む）")
    p.add_argument("--html", action="store_true", help="横並びHTML版も生成")
    args = p.parse_args(argv)

    md = render(args.out_dir, task=args.task)
    path = args.out_dir / "comparison.md"
    path.write_text(md)
    print(f"→ 保存: {path}")

    if args.html:
        html_path = args.out_dir / "comparison.html"
        html_path.write_text(_html_of(md))
        print(f"→ 保存: {html_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
