# -*- coding: utf-8 -*-
"""テストスイート共通の環境固定。

legacy テスト（engine 定数の ja 挙動・ja キーワード・ja マーカーを前提に書かれた 184 件）
を変更なしで通すため、ランタイム既定の言語（en）を環境変数で ja に固定する。
新規の i18n テストは monkeypatch.setenv または --lang で個別に言語を切り替える。
"""

import os

os.environ.setdefault("ELEVATE_DRAFT_ENGINE_LANG", "ja")

import pytest  # noqa: E402  (環境変数設定後に elevate を import できるよう、ここで保証)


@pytest.fixture(autouse=True)
def _reset_i18n_cache():
    """各テストの間、i18n キャッシュを破棄する（言語差がテスト間で漏れないように）。"""
    from elevate import i18n

    i18n.clear_cache()
    yield
    i18n.clear_cache()
