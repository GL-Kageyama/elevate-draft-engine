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
