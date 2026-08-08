"""ClaudeClient アダプタのテスト（2026-08-08 追加）。

対象: adapters/claude_client.py の _call が空応答を再試行する（崩れたら再生成方針）。
dev 検証で実ゲートウェイが空文字を返し、空成果物のまま評価されて成功率が歪んだ
（35%が overall 0.1）。空応答は API 例外と同様に再試行し、最大回数後に失敗にする。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.claude_client import ClaudeClient, ClaudeConfig  # noqa: E402


class FakeResponse:
    """content に空の list または text ブロックを持つ応答を模す。"""

    def __init__(self, texts: list[str]):
        self.content = [type("Block", (), {"type": "text", "text": t})() for t in texts]


class FakeMessages:
    def __init__(self, results: list[FakeResponse | object]):
        """results: 各試行で返す応答。例外オブジェクトも指定できる。"""
        self.results = list(results)
        self.calls = 0

    def create(self, **kwargs):
        idx = min(self.calls, len(self.results) - 1)
        self.calls += 1
        r = self.results[idx]
        if isinstance(r, Exception):
            raise r
        return r


class FakeClient:
    def __init__(self, messages: FakeMessages):
        self.messages = messages


def _make_client(messages: FakeMessages) -> ClaudeClient:
    cfg = ClaudeConfig(
        api_key="sk-test",
        base_url="https://test.local",
        generation_model="claude-sonnet-4-5",
        evaluation_model="claude-haiku-4-5",
        max_retries=3,
    )
    client = ClaudeClient(cfg)
    client.client = FakeClient(messages)
    return client


def test_empty_response_is_retried():
    """空応答は再試行され、次の非空応答が返る（崩れたら再生成）。"""
    messages = FakeMessages([FakeResponse([""]), FakeResponse(["正常な成果物"])])
    client = _make_client(messages)
    out = client.generate(system="s", user="u")
    assert out == "正常な成果物"
    assert messages.calls == 2


def test_whitespace_only_is_retried():
    """空白のみの応答も空扱いで再試行される。"""
    messages = FakeMessages([FakeResponse(["   \n  "]), FakeResponse(["成果物"])])
    client = _make_client(messages)
    out = client.generate(system="s", user="u")
    assert out == "成果物"
    assert messages.calls == 2


def test_all_empty_raises():
    """全試行が空なら RuntimeError（再生成で直らない場合は明示的に失敗）。"""
    messages = FakeMessages([FakeResponse([""]), FakeResponse([""]), FakeResponse([""])])
    client = _make_client(messages)
    with pytest.raises(RuntimeError, match="空の応答"):
        client.generate(system="s", user="u")
    assert messages.calls == 3


def test_api_error_then_empty_then_success():
    """API例外→空応答→成功 を順に試す（両方の再試行経路が動く）。"""
    import anthropic

    err = anthropic.APITimeoutError(request=object())
    messages = FakeMessages([err, FakeResponse([""]), FakeResponse(["成功"])])
    client = _make_client(messages)
    out = client.generate(system="s", user="u")
    assert out == "成功"
    assert messages.calls == 3


def test_min_interval_throttles_requests():
    """min_interval_seconds 以上空けてリクエストが送られる（スロットル）。

    実ゲートウェイは連続呼び出しで空応答を返す率が上がるため、全リクエストを
    最小間隔に保つ（2026-08-08 dev 検証の知見。全条件均等適用）。"""
    import time as _time

    cfg = ClaudeConfig(
        api_key="sk-test",
        base_url="https://test.local",
        generation_model="claude-sonnet-4-5",
        evaluation_model="claude-haiku-4-5",
        max_retries=3,
        min_interval_seconds=0.1,
    )
    client = ClaudeClient(cfg)

    times = []

    class TimedMessages:
        def create(self, **kwargs):
            times.append(_time.monotonic())
            return FakeResponse(["成果物"])

    client.client = FakeClient(TimedMessages())
    client.generate(system="s", user="u")
    client.generate(system="s", user="u")
    assert len(times) == 2
    assert times[1] - times[0] >= 0.1


def test_throttle_disabled_when_zero():
    """min_interval_seconds=0 ならスロットルしない（ライブラリ既定は無効）。"""
    import time as _time

    cfg = ClaudeConfig(
        api_key="sk-test",
        base_url="https://test.local",
        generation_model="claude-sonnet-4-5",
        evaluation_model="claude-haiku-4-5",
        max_retries=3,
        min_interval_seconds=0.0,
    )
    client = ClaudeClient(cfg)
    times = []

    class TimedMessages:
        def create(self, **kwargs):
            times.append(_time.monotonic())
            return FakeResponse(["成果物"])

    client.client = FakeClient(TimedMessages())
    client.generate(system="s", user="u")
    client.generate(system="s", user="u")
    assert len(times) == 2
    assert times[1] - times[0] < 0.1
