"""具体性保存指数（Specificity Preservation Index）。

発散草案が持つ「具体的な要素」（固有名詞・数字・独自造語）が、統合成果物に
どれだけ残存するかを測る。知恵の評議会の指摘「発散の感情的・意味的真実が
統合を生き延びるかは未実証」への実測手段。

「見捨てられた人が、この企画の主人公だ」のような具体は、Reconcile→Finalize を
経て「平均化」により失われやすい。この指数はその残存率を数値化し、
統合が外れる許可（DIVERGE）を解消していないかを観測する。

限定事項:
- 日本語の固有表現解析は使わない軽量実装。抽出できるのはカタカナ語・数字・
  英単語（識別子）のみで、「藤原浩一」のような漢字固有名詞は捉えられない。
  保存率は下限の推定値として読む（漢字固有名詞の残存は測れない分、過小に出る）。
"""

from __future__ import annotations

import re
from typing import Callable, Iterable

# 抽出対象の具体トークン:
# - カタカナ語（2字以上。ゾンビ知識・ゲーミフィケーション・ナレッジ等）
# - 数字列（73、ステージ4 の 4、0件 の 0 等。小数含む）
# - 英単語・識別子（2字以上。AI、API、best-of-n 等）
_KATAKANA_RE = re.compile(r"[ァ-ヶー]{2,}")
_DIGIT_RE = re.compile(r"\d+(?:\.\d+)?")
_ASCII_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,}")


def extract_concrete_tokens(text: str) -> set[str]:
    """テキストから具体トークン（カタカナ語・数字・英単語）の集合を抽出する。"""
    tokens: set[str] = set()
    for pat in (_KATAKANA_RE, _DIGIT_RE, _ASCII_WORD_RE):
        tokens.update(m.group(0) for m in pat.finditer(text))
    return tokens


def _survives(token: str, elevated: str) -> bool:
    """具体トークンが統合成果物に部分文字列として残っているか。"""
    return token in elevated


def compute_preservation_rate(
    drafts: Iterable["object"],
    elevated: str,
    *,
    get_content: Callable[[object], str] | None = None,
) -> dict:
    """発散草案の具体トークンの統合後残存率を計算する。

    Args:
        drafts: 草案のイテラブル（Draft 等。`get_content` で本文を取る）。
        elevated: 統合成果物テキスト。
        get_content: 草案オブジェクトから本文文字列を取り出す関数。
            省略時は `.content` 属性を使う（elevate.engine.Draft 用）。

    Returns:
        {
          "preservation_rate": float | None,  # 残存率（0.0-1.0）。抽出源が無ければ None
          "source_tokens": list[str],          # 抽出された具体トークンの和集合
          "matched": list[str],                # elevated に残存したトークン
          "survival": list[bool],              # トークンごとの残存フラグ
          "per_draft": {agent: {"tokens": [...], "survived": [...], "rate": float|None}},
        }
    """
    if get_content is None:
        get_content = lambda d: d.content  # noqa: E731

    per_draft: dict[str, dict] = {}
    source: set[str] = set()
    for draft in drafts:
        agent = getattr(draft, "agent", "?")
        tokens = extract_concrete_tokens(get_content(draft))
        source |= tokens
        survived = [t for t in tokens if _survives(t, elevated)]
        per_draft[agent] = {
            "tokens": sorted(tokens),
            "survived": sorted(survived),
            "rate": (len(survived) / len(tokens)) if tokens else None,
        }

    matched = [t for t in source if _survives(t, elevated)]
    rate = (len(matched) / len(source)) if source else None
    return {
        "preservation_rate": rate,
        "source_tokens": sorted(source),
        "matched": sorted(matched),
        "survival": [t in matched for t in sorted(source)],
        "per_draft": per_draft,
    }


def format_preservation_report(result: dict) -> str:
    """保存率の集計を Markdown 文字列に整形する。"""
    rate = result["preservation_rate"]
    lines = [
        "### 具体性保存指数（発散 → 統合）",
        f"- 残存率: **{rate:.1%}**" if rate is not None else "- 残存率: 評価不能（具体トークンなし）",
        f"- 抽出された具体トークン: {len(result['source_tokens'])} 個",
    ]
    if result["matched"]:
        lines.append(f"- 統合に残存: {len(result['matched'])} 個（{', '.join(result['matched'][:20])}{'…' if len(result['matched']) > 20 else ''}）")
    if not result["matched"] and result["source_tokens"]:
        lines.append("- 統合に残存: 0 個 — 発散の具体が統合で全て失われている")
    if rate is not None and rate < 0.5:
        lines.append(
            "- 判定: **残存率 50% 未満**。統合が発散の具体（名前・数字・独自造語）を"
            "平滑化していないか要確認。"
        )
    for agent, d in result["per_draft"].items():
        r = f"{d['rate']:.0%}" if d["rate"] is not None else "—"
        lines.append(f"  - {agent}: 残存 {r}（{len(d['survived'])}/{len(d['tokens'])} トークン）")
    return "\n".join(lines)
