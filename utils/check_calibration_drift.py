#!/usr/bin/env python3
"""多言語ストアの静的較正ドリフトチェック（計画フェーズ8.2 の前半）。

prompts/{lang}.json のルーブリックが、翻訳後も**数値の較正契約**を維持しているかを
検証する。ここが証明できるのは「数値が翻訳で動いていない」ことだけで、
「LLM が言語ごとに同じ厳しさを適用する」ことは証明できない（それは
utils/calibrate_language_bias.py のランタイム較正の仕事）。

検証する較正契約:
    1. 5軸評価（evaluator.RUBRIC）の軸名が3言語すべてで正規形に対応する
       （en: Diversity/Synthesis/Elevation/Honesty/Utility
        ja: 多様性/統合性/超越性/誠実性/実用性
        zh: 多样性/整合性/超越性/诚实性/实用性）。
    2. 採点アンカー（0.5 = 無難基準 / 0.7〜0.8 = 確かに良い / 0.9 以上 = 卓越）が
       各言語の RUBRIC に存在する。
    3. 軸ごとの帯域（0.9-1.0 / 0.7-0.8 / 0.5-0.6 / 0.0-0.4）が各言語に存在する。
    4. 品質評価（quality.RUBRIC）のJSONキー（novelty/originality/surprise）が
       3言語すべてで維持されている（D2 の英語キー一本化）。
    5. 言語間で RUBRIC が同一ではない（翻訳されている）ことを確認。

wisdom-council-layer の check_calibration_drift.py と同じ方針（空リスト等価は
誤 PASS になる → 各抽出が非空であることも確認する）。

Usage:
    python utils/check_calibration_drift.py          # 人間可読レポート
    python utils/check_calibration_drift.py --json   # 機械可読結果

Exit codes:
    0  全チェック PASS
    1  ドリフトあり・または利用法エラー
"""

import argparse
import json
import os
import re
import sys

PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "prompts")

LANGS = ("en", "ja", "zh")

# 正規形の5軸名。各言語のルーブリックにすべて含まれている必要がある。
CANONICAL_AXES = {
    "en": ["Diversity", "Synthesis", "Elevation", "Honesty", "Utility"],
    "ja": ["多様性", "統合性", "超越性", "誠実性", "実用性"],
    "zh": ["多样性", "整合性", "超越性", "诚实性", "实用性"],
}

# 採点アンカー（各言語の RUBRIC に出現する数値表現）
ANCHOR_PATTERNS = [
    (r"0\.5", "0.5（無難基準）"),
    (r"0\.7", "0.7"),
    (r"0\.8", "0.8"),
    (r"0\.9", "0.9"),
]

# 軸ごとの帯域（3言語すべての軸定義行にこの4帯域がある）
BAND_PATTERNS = [r"0\.9[-–～~]1\.0", r"0\.7[-–～~]0\.8", r"0\.5[-–～~]0\.6", r"0\.0[-–～~]0\.4"]

# 品質評価JSONキー（D2: 英語キーに一本化）
QUALITY_KEYS = ["novelty", "originality", "surprise"]


def load_prompts(lang: str) -> dict:
    path = os.path.join(PROMPTS_DIR, f"{lang}.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def run_checks() -> list[dict]:
    """全チェックを実行し [(check_name, ok, detail)] を返す。"""
    results: list[dict] = []
    rubrics = {}

    for lang in LANGS:
        prompts = load_prompts(lang)
        rubrics[lang] = {
            "evaluator": prompts.get("evaluator", {}).get("RUBRIC", ""),
            "quality": prompts.get("quality", {}).get("RUBRIC", ""),
        }
        ev, qa = rubrics[lang]["evaluator"], rubrics[lang]["quality"]

        # 1. 5軸名がすべて含まれる
        missing = [ax for ax in CANONICAL_AXES[lang] if ax not in ev]
        results.append({
            "name": f"{lang}: 5軸名の完全性",
            "ok": not missing and bool(ev),
            "detail": "欠落: " + ", ".join(missing) if missing else
                      (", ".join(CANONICAL_AXES[lang]) if ev else "RUBRIC が空"),
        })

        # 2. 採点アンカーが存在する
        missing_anchors = [label for pat, label in ANCHOR_PATTERNS if not re.search(pat, ev)]
        results.append({
            "name": f"{lang}: 採点アンカー",
            "ok": not missing_anchors,
            "detail": "欠落: " + ", ".join(missing_anchors) if missing_anchors else "0.5/0.7/0.8/0.9 あり",
        })

        # 3. 軸ごとの帯域が存在する
        missing_bands = [pat for pat in BAND_PATTERNS if not re.search(pat, ev)]
        results.append({
            "name": f"{lang}: 軸帯域",
            "ok": not missing_bands,
            "detail": "欠落: " + ", ".join(missing_bands) if missing_bands else "4帯域あり",
        })

        # 4. 品質評価の英語キー（D2）
        missing_keys = [k for k in QUALITY_KEYS if k not in qa]
        results.append({
            "name": f"{lang}: 品質評価キー（英語・D2）",
            "ok": not missing_keys and bool(qa),
            "detail": "欠落: " + ", ".join(missing_keys) if missing_keys else ", ".join(QUALITY_KEYS),
        })

    # 5. 言語間で同一でない（翻訳されている）
    texts = [r["evaluator"] for r in rubrics.values()]
    distinct = len({t for t in texts}) == len(LANGS) and all(texts)
    results.append({
        "name": "言語間でルーブリックが区別されている",
        "ok": distinct,
        "detail": "3言語で異なる（翻訳済み）" if distinct else "同一または空",
    })

    return results


def main() -> int:
    ap = argparse.ArgumentParser(description="多言語ストアの静的較正ドリフトチェック")
    ap.add_argument("--json", action="store_true", help="機械可読で出力")
    args = ap.parse_args()

    results = run_checks()
    all_ok = all(r["ok"] for r in results)

    if args.json:
        print(json.dumps({"ok": all_ok, "checks": results}, ensure_ascii=False, indent=2))
    else:
        for r in results:
            mark = "PASS" if r["ok"] else "FAIL"
            print(f"[{mark}] {r['name']}: {r['detail']}")
        print()
        print("ALL PASS" if all_ok else "DRIFT FOUND")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
