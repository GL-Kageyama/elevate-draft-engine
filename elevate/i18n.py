"""言語解決とロケール/プロンプト読み込み。3言語 (en/ja/zh)。

- `locales/{lang}.json` … CLI / UI / 保存テンプレートの文字列
- `prompts/{lang}.json` … LLM プロンプト（engine 定数・RUBRIC・温度ヒント・改修マーカー）

言語選択の優先順位（wisdom-council-layer と同じ三段）:
1. CLI フラグ `--lang {en,ja,zh}`
2. 環境変数 `ELEVATE_DRAFT_ENGINE_LANG`
3. デフォルト `en`（D1確定: ランタイム既定は英語）
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_SUPPORTED = ("en", "ja", "zh")
_ENV_VAR = "ELEVATE_DRAFT_ENGINE_LANG"
_DEFAULT_LANG = "en"  # D1確定: ランタイム既定は英語（--lang 省略時）

_cache: dict[str, dict[str, dict]] = {"locales": {}, "prompts": {}}


def resolve_lang(cli_lang: str | None = None) -> str:
    """言語を解決する。CLI > 環境変数 > 既定（en）。未対応言語は警告して既定へ。"""
    lang = (cli_lang or os.environ.get(_ENV_VAR) or _DEFAULT_LANG).lower()
    if lang not in _SUPPORTED:
        sys.stderr.write(
            f"Warning: unsupported language '{lang}', falling back to '{_DEFAULT_LANG}'\n"
        )
        return _DEFAULT_LANG
    return lang


def _load(dirname: str, lang: str) -> dict:
    resolved = resolve_lang(lang)
    if resolved not in _cache[dirname]:
        p = Path(__file__).resolve().parent.parent / dirname / f"{resolved}.json"
        _cache[dirname][resolved] = json.loads(p.read_text(encoding="utf-8"))
    return _cache[dirname][resolved]


def load_locale(lang: str) -> dict:
    """locales/{lang}.json を読み込む（キャッシュ）。"""
    return _load("locales", lang)


def load_prompts(lang: str) -> dict:
    """prompts/{lang}.json を読み込む（キャッシュ）。"""
    return _load("prompts", lang)


def clear_cache() -> None:
    """キャッシュを破棄する（テスト用）。"""
    _cache["locales"].clear()
    _cache["prompts"].clear()


# ---- アダプタ共通: 発想レベルの発散強化ヒント解決 ----
# 発想レベル（engine.IDEA_LEVELS のキー）→ ヒント/プレフィックスのキー。正本はここ。
# 文言は prompts/{lang}.json の adapters 節に 3言語で定義する。
_IDEA_LEVEL_HINTS: dict[str, tuple[str, str]] = {
    "standard": ("DIVERGE_HINT", "DIVERGE_PREFIX"),
    "very": ("DIVERGE_VERY_HINT", "DIVERGE_VERY_PREFIX"),
    "extreme": ("DIVERGE_EXTREME_HINT", "DIVERGE_EXTREME_PREFIX"),
}


def adapter_hint(prompts: dict, *, idea_level: str | None = None,
                 temperature: float | None = None) -> tuple[str | None, str | None]:
    """idea_level（発想レベル）または温度から、アダプタ用の強化ヒント (prefix, hint) を解決する。

    アダプタ（sdk / claude-code）から呼ばれる。idea_level が渡されたら発想レベルに応じた
    発散強化ヒント（standard/very/extreme）を返す。渡されなければ従来の温度ベース
    （>=0.5 発散 / <0.5 一貫性）で後方互換。ヒント無し（素のまま）なら (None, None)。
    戻り値は (prefix, hint)。両方 None ならユーザープロンプトに手を加えない。
    """
    ad = (prompts or {}).get("adapters", {}) or {}
    if idea_level is not None:
        hint_key, prefix_key = _IDEA_LEVEL_HINTS.get(idea_level, _IDEA_LEVEL_HINTS["standard"])
        hint = ad.get(hint_key)
        return (ad.get(prefix_key), hint) if hint else (None, None)
    if temperature is not None and temperature >= 0.5:
        return ad.get("DIVERGE_PREFIX"), ad.get("DIVERGE_HINT")
    if temperature is not None and temperature < 0.5:
        return ad.get("CONSISTENT_PREFIX"), ad.get("CONSISTENT_HINT")
    return None, None
