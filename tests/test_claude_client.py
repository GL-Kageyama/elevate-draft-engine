"""ClaudeClient アダプタのテスト（2026-08-08 追加）。

対象: adapters/claude_client.py の _call が空応答を再試行する（崩れたら再生成方針）。
dev 検証で実ゲートウェイが空文字を返し、空成果物のまま評価されて成功率が歪んだ
（35%が overall 0.1）。空応答は API 例外と同様に再試行し、最大回数後に失敗にする。
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.claude_client import ClaudeClient, ClaudeConfig  # noqa: E402
from adapters.claude_code_client import ClaudeCodeClient  # noqa: E402


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


def _make_client(messages: FakeMessages, *, lang: str | None = None) -> ClaudeClient:
    cfg = ClaudeConfig(
        api_key="sk-test",
        base_url="https://test.local",
        generation_model="claude-sonnet-4-5",
        evaluation_model="claude-haiku-4-5",
        max_retries=3,
    )
    client = ClaudeClient(cfg, lang=lang)
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


def test_generation_uses_roomy_max_tokens_for_gateway_reasoning():
    """生成は思考ブロックに max_tokens を食われ空 text にならない十分な予算を使う。

    実ゲートウェイ（deepseek 経由）は reasoning モデルが thinking ブロックを返す。
    max_tokens が 4096 だと長い system（en の止揚 670字 + 「Prioritize depth」指示）で
    思考が予算を全て消費し、text が 0 の空応答→再試行→失敗になる
    （2026-08-10 実測: en 止揚で12連続空。ja/zh は system が短く思考も短いため成功）。
    思考と成果物を両方収められる予算（既定 16384）で送ることを回帰テストで保証する。
    """
    captured: dict = {}

    class RecorderMessages:
        def create(self, **kwargs):
            captured["max_tokens"] = kwargs.get("max_tokens")
            return FakeResponse(["成果物"])

    client = _make_client(FakeMessages([FakeResponse(["成果物"])]))
    client.client = FakeClient(RecorderMessages())
    client.generate(system="s", user="u")
    assert captured["max_tokens"] >= 8192, (
        f"生成の max_tokens が思考で枯渇し空 text になる: {captured['max_tokens']}"
    )


def test_default_config_uses_roomy_max_tokens(monkeypatch):
    """環境変数未指定の既定 config も思考込みの予算を使う（4096 に戻したら回帰）。"""
    import adapters.claude_client as mod

    monkeypatch.delenv("CLAUDE_MAX_TOKENS", raising=False)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    cfg = mod.ClaudeClient._default_config()
    assert cfg.max_tokens >= 8192


def test_default_config_max_tokens_override(monkeypatch):
    """CLAUDE_MAX_TOKENS 環境変数で max_tokens を変更できる。"""
    import adapters.claude_client as mod

    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "t")
    monkeypatch.setenv("CLAUDE_MAX_TOKENS", "1000")
    cfg = mod.ClaudeClient._default_config()
    assert cfg.max_tokens == 1000


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


# ---- ClaudeCodeClient のストリーム解析（claude -p --output-format stream-json） ----

class _FakePopen:
    """subprocess.Popen の代役。lines を stdout として返し、returncode を保持する。"""

    def __init__(self, lines: list[str], returncode: int = 0):
        self.lines = lines
        self.returncode = returncode
        self.calls = 0

    def __call__(self, cmd: list[str], **kwargs):
        self.calls += 1
        self.cmd = cmd
        self.stdout = iter(self.lines)
        self.stderr = type("_Stderr", (), {"read": lambda self: ""})()
        return self

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9


def _stream_jsonl(events: list[dict]) -> list[str]:
    """stream-json の改行区切り JSON を組み立てる。"""
    return [json.dumps(e, ensure_ascii=False) for e in events]


def test_claude_code_stream_extracts_cumulative_text_deltas(monkeypatch):
    """assistant イベントの累積テキストから差分を取り出し、on_chunk に逐次流す。

    system/init・thinking ブロック・result イベントは読み飛ばし、text ブロックの
    累積テキスト（前回分との差分）だけを返す。全文は最後の累積値に一致する。
    """
    import adapters.claude_code_client as mod

    events = _stream_jsonl([
        {"type": "system", "subtype": "init", "content": "diagnostics"},
        {"type": "assistant", "message": {"content": [
            {"type": "thinking", "text": "考え中のノート"},
            {"type": "text", "text": "前半の"},
        ]}},
        {"type": "assistant", "message": {"content": [
            {"type": "thinking", "text": "考え中のノート"},
            {"type": "text", "text": "前半の後半である。"},
        ]}},
        {"type": "result", "subtype": "success", "result": "前半の後半である。"},
        "これはJSON文字列だがオブジェクトではない",
        "これは完全な非JSON行 {",
    ])
    fake = _FakePopen(events)
    monkeypatch.setattr(mod.subprocess, "Popen", fake)
    client = mod.ClaudeCodeClient()

    deltas: list[str] = []
    text = client._run_stream("prompt", "system", on_chunk=deltas.append)

    assert text == "前半の後半である。"
    assert deltas == ["前半の", "後半である。"]


def test_claude_code_stream_empty_output_is_retried_then_fails(monkeypatch):
    """全文が届かない空出力（exit 0）は再試行され、直らなければ明示的に失敗する。"""
    import adapters.claude_code_client as mod

    fake = _FakePopen([], returncode=0)
    monkeypatch.setattr(mod.subprocess, "Popen", fake)
    client = mod.ClaudeCodeClient(max_retries=3)

    with pytest.raises(RuntimeError, match="Claude API 呼び出しに失敗"):
        client.generate(system="s", user="u")
    assert fake.calls == 3  # 空応答は再試行される（broken output → regenerate）


def test_claude_code_stream_nonzero_exit_without_text_raises(monkeypatch):
    """部分テキストが無いまま異常終了（exit≠0）なら RuntimeError（再試行可能）。"""
    import adapters.claude_code_client as mod

    fake = _FakePopen([], returncode=1)
    monkeypatch.setattr(mod.subprocess, "Popen", fake)
    client = mod.ClaudeCodeClient(max_retries=1)

    with pytest.raises(RuntimeError, match="claude -p が空応答/異常終了"):
        client.generate(system="s", user="u")


# ---- 発想レベル（idea_level）のヒント注入 ----

class _RecorderMessages:
    def __init__(self):
        self.captured: dict = {}

    def create(self, **kwargs):
        self.captured.update(kwargs)
        return FakeResponse(["成果物"])


def test_claude_client_injects_idea_level_hint():
    """sdk アダプタは idea_level のヒントを user に前置し、温度も API に渡す。

    発想レベルは「より極端」の意味論をプロンプトで担保する主レバー（reasoning モデルでは
    温度だけでは確実な強化にならないため）。very=1.2 のときその強化ヒントが入る。
    """
    rec = _RecorderMessages()
    client = _make_client(FakeMessages([FakeResponse(["成果物"])]), lang="ja")
    client.client = FakeClient(rec)
    client.generate(system="s", user="タスク", temperature=1.2, idea_level="very")

    user = rec.captured["messages"][0]["content"]
    assert "[非常に極端な発散を重視]" in user
    assert "前提そのもの" in user
    assert rec.captured["temperature"] == 1.2


def test_claude_client_no_hint_without_idea_level():
    """sdk アダプタは idea_level 未指定なら素のプロンプト（後方互換: 温度のみ）。"""
    rec = _RecorderMessages()
    client = _make_client(FakeMessages([FakeResponse(["成果物"])]), lang="ja")
    client.client = FakeClient(rec)
    client.generate(system="s", user="タスク", temperature=0.9)

    assert rec.captured["messages"][0]["content"] == "タスク"
    assert rec.captured["temperature"] == 0.9


def test_claude_code_idea_level_three_tier_hints():
    """claude-code は idea_level に応じて ①②③ の3段ヒントに切り替わる。"""
    client = ClaudeCodeClient(lang="ja")
    base = "タスク本文"
    standard = client._localized_user(base, temperature=0.9, idea_level="standard")
    very = client._localized_user(base, temperature=1.2, idea_level="very")
    extreme = client._localized_user(base, temperature=1.5, idea_level="extreme")

    assert "[発散を重視]" in standard
    assert "[非常に極端な発散を重視]" in very
    assert "[極度に極端な発散を重視]" in extreme
    assert standard != very != extreme


def test_claude_code_temperature_fallback_backward_compat():
    """claude-code は idea_level 未指定なら従来の温度ベース（>=0.5 発散 / <0.5 一貫性）。"""
    client = ClaudeCodeClient(lang="ja")
    assert "[発散を重視]" in client._localized_user("u", temperature=0.9)
    assert "[一貫性を重視]" in client._localized_user("u", temperature=0.0)
    assert client._localized_user("u", temperature=None) == "u"
