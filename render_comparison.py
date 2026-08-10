"""比較ドキュメント生成: compare の出力ディレクトリから「素AI生成 vs 昇華版」を読める形に。

知恵の評議会の「昇華優位性の実証」は、統計（CI）だけでなく、実際の成果物で
素AI生成と昇華版を並べて人間が客観的に読めること自体が目的である。

compare は run ごとに raw.md（素AI生成）と elevated.md（昇華版）を保存する
（--runs>1 なら run_NN/ サブフォルダ）。このスクリプトはそれらを1つの
comparison.md に束ね、スコア表つきで「どちらが読んでいて優れているか」を
人間が判断できる形にする。見出し・ラベルは locales/{lang}.json の render 節から
言語別に取る（--lang で選択、既定は i18n 解決＝en）。

使い方:
    python render_comparison.py examples/<sample_dir>            # 比較ドキュメントを生成
    python render_comparison.py examples/<sample_dir> --lang ja  # 日本語で生成
    python render_comparison.py examples/<sample_dir> --html     # HTML版も生成（横並び表示）
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from elevate import i18n


def _loc(lang: str | None) -> dict:
    """ロケール辞書を取得する（lang 未指定は i18n 解決＝既定 en）。"""
    return i18n.load_locale(i18n.resolve_lang(lang))


def _t(loc: dict, section: str, name: str, default: str, **fmt) -> str:
    """ロケール辞書の section.name を取得し {fmt} を適用する（無ければ default に退避）。

    name という引数名にしているのは、テンプレートの書式キー（{key} 等）と衝突しないため。
    """
    tmpl = loc.get(section, {}).get(name, default)
    return tmpl.format(**fmt) if fmt else tmpl


def _read(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def _read_first(*paths: Path) -> str:
    """最初に存在するファイルの内容を返す（無ければ空文字）。

    2026-08-09 の出力カテゴリ分類（drafts/evaluations/artifacts）以前のフラットな
    出力ディレクトリにも対応するため、新レイアウト → 旧レイアウトの順に探す。
    """
    for p in paths:
        if p.exists():
            return p.read_text()
    return ""


def _find_runs(out_dir: Path) -> list[Path]:
    """run_NN/ サブフォルダのリスト（昇順）。なければ [out_dir] を返す（--runs 1）。"""
    runs = sorted([p for p in out_dir.iterdir() if p.is_dir() and re.fullmatch(r"run_\d+", p.name)])
    return runs or [out_dir]


def _score_table(measurement: str) -> str:
    """measurement.md の統計行ブロックを抽出して返す（無ければ空文字）。

    言語別の文言に依存せず、数値マーカー（95%CI / Cohen's d / mean=）で判定する。
    CI ラベル（Wilson / Cohen's d）は全言語で英語のまま維持しているため、ここは
    言語非依存で安全に抽出できる。
    """
    lines = [ln for ln in measurement.splitlines() if re.search(r"95%CI|Cohen's d|mean=", ln)]
    return "\n".join(lines)


def _run_block(run_dir: Path, idx: int, loc: dict) -> list[str]:
    """1 run 分の比較ブロック（素AI生成と昇華版を並べて読める形）を組み立てる。"""
    raw = _read_first(run_dir / "artifacts/raw.md", run_dir / "raw.md").strip()
    elevated = _read_first(run_dir / "artifacts/elevated.md", run_dir / "elevated.md").strip()
    baseline_eval = _read_first(
        run_dir / "evaluations/evaluation_baseline.md", run_dir / "evaluation_baseline.md"
    ).strip()
    elevated_eval = _read_first(
        run_dir / "evaluations/evaluation_elevated.md", run_dir / "evaluation_elevated.md"
    ).strip()

    raw_heading = _t(loc, "render", "raw_heading", "### 素AI生成（raw.md）")
    elevated_heading = _t(loc, "render", "elevated_heading", "### 昇華版（elevated.md）")
    expand = _t(loc, "render", "click_to_expand", "読む（クリックで展開）")

    lines: list[str] = []
    if not raw and not elevated:
        return lines
    lines.append(_t(loc, "render", "run_heading", "## run {idx}", idx=idx))
    lines.append("")
    if baseline_eval:
        lines.append(f"{_t(loc, 'render', 'raw_eval', '**素AI生成の評価**')}\n\n```\n{baseline_eval}\n```")
    if elevated_eval:
        lines.append(f"{_t(loc, 'render', 'elevated_eval', '**昇華版の評価**')}\n\n```\n{elevated_eval}\n```")
    if raw and elevated:
        lines.append(
            f"{raw_heading}\n\n<details><summary>{expand}</summary>\n\n```markdown\n"
            + raw
            + "\n```\n\n</details>"
        )
        lines.append(
            f"{elevated_heading}\n\n<details><summary>{expand}</summary>\n\n```markdown\n"
            + elevated
            + "\n```\n\n</details>"
        )
    elif raw:
        lines.append(f"{raw_heading}\n\n```markdown\n{raw}\n```")
    elif elevated:
        lines.append(f"{elevated_heading}\n\n```markdown\n{elevated}\n```")
    lines.append("")
    return lines


def render(out_dir: Path, task: str | None = None, lang: str | None = None) -> str:
    """out_dir の compare 出力から comparison.md の本文を生成する。"""
    loc = _loc(lang)
    out_dir = out_dir.resolve()
    input_md = _read(out_dir / "input.md")
    if not task:
        m = re.search(r"# (?:タスク|任务|Task)\n\n(.+)", input_md)
        task = m.group(1).strip() if m else out_dir.name

    measurement = _read(out_dir / "measurement.md")
    score_block = _score_table(measurement) if measurement else ""

    lines = [
        _t(loc, "render", "title", "# 比較: 素AI生成 vs 昇華版"),
        "",
        _t(loc, "render", "task", "**タスク**: {task}", task=task),
        _t(loc, "render", "saved_at", "**保存先**: `{dir}`", dir=out_dir),
        "",
        _t(loc, "render", "disclaimer",
           "> このドキュメントは「統合優位性の実証」の材料である。**結論は数値が下すのではなく、"
           "> あなたが両方を読んで判断する。** 数値は客観視のための補助であり、単発生成（約1回）と"
           "> 統合（8草案×温度0.7→推理→最終化、約10回）はコストが桁違いに異なる点に注意せよ。"),
    ]
    if measurement:
        lines += [
            "",
            _t(loc, "render", "measurement_summary", "## 計測サマリ"),
            "",
            f"```\n{measurement.strip()}\n```",
        ]
    if score_block:
        lines += ["", _t(loc, "render", "score", "### スコア"), "", score_block, ""]

    for idx, run_dir in enumerate(_find_runs(out_dir), start=1):
        lines += _run_block(run_dir, idx, loc)

    return "\n".join(lines)


def _html_of(md: str, raw_marker: str, elev_marker: str, html_raw: str, html_elevated: str) -> str:
    """Markdown の比較ドキュメントから横並びHTMLを生成する（ブラウザで客観視用）。

    完全なMarkdownパーサーは持たない。run ブロックの「素AI生成」/「昇華版」を
    2カラムに並べる軽量変換のみを行う。セクション見出しのマーカー（言語別）と
    カラムラベル（言語別）は引数で受け取る。
    """
    from html import escape

    runs: list[tuple[str, str]] = []
    cur_raw: list[str] = []
    cur_elev: list[str] = []
    in_raw = in_elev = False
    for line in md.splitlines():
        if line.startswith(raw_marker):
            in_raw, in_elev = True, False
            cur_raw, cur_elev = [], []
            continue
        if line.startswith(elev_marker):
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
    <h3 style="color:#a33;">{html_raw}</h3>
    <pre style="white-space:pre-wrap;font-family:inherit;">{escape(raw.strip())}</pre>
  </div>
  <div style="flex:1;min-width:320px;border:1px solid #ccc;padding:1em;">
    <h3 style="color:#3a3;">{html_elevated}</h3>
    <pre style="white-space:pre-wrap;font-family:inherit;">{escape(elev.strip())}</pre>
  </div>
</div>"""
        )
    return f"<!doctype html><html><body>{''.join(cards)}</body></html>"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="compare 出力から比較ドキュメントを生成")
    p.add_argument("out_dir", type=Path, help="compare の出力ディレクトリ")
    p.add_argument("--task", default=None, help="タスク名（省略時は input.md から読む）")
    p.add_argument("--lang", default=None, choices=["en", "ja", "zh"], help="出力言語（既定は i18n 解決＝en）")
    p.add_argument("--html", action="store_true", help="横並びHTML版も生成")
    args = p.parse_args(argv)

    loc = _loc(args.lang)
    md = render(args.out_dir, task=args.task, lang=args.lang)
    path = args.out_dir / "comparison.md"
    path.write_text(md)
    print(_t(loc, "console", "saved", "→ 保存: {path}", path=path))

    if args.html:
        raw_heading = _t(loc, "render", "raw_heading", "### 素AI生成（raw.md）")
        elev_heading = _t(loc, "render", "elevated_heading", "### 昇華版（elevated.md）")
        html_raw = _t(loc, "render", "html_raw", "素AI生成")
        html_elevated = _t(loc, "render", "html_elevated", "昇華版")
        html_path = args.out_dir / "comparison.html"
        html_path.write_text(_html_of(md, raw_heading, elev_heading, html_raw, html_elevated))
        print(_t(loc, "console", "saved", "→ 保存: {path}", path=html_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
