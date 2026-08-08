"""Claude Code CLI（claude -p）経由の生成アダプタ。

各コールを 1 つの `claude -p` プロセスとして起動する——各エージェントを独立した
サブエージェントとして起動し、互いの文脈を共有しない独立起動をライブラリで実現する。
system（ペルソナ）は `--system-prompt` で渡す。

背景: 生 SDK（anthropic.Anthropic）は Claude Code 互換ゲートウェイが間欠的に空応答
（200・空文字列、stop=max_tokens）を返す環境で不安定だった（2026-08-08 実測:
長いプロンプトで成功率 ~1/3）。同じゲートウェイでも Claude Code CLI 経由は安定して
応答する（実測: reconcile 15KB を完全出力）。温度は CLI に直接渡せないため、
発散（高温度相当）／一貫性（低温度相当）の指示をプロンプトに含めて近似する。
"""

from __future__ import annotations

import json
import subprocess
import time
from typing import Callable

# 発散（diverge / reconcile）と一貫性（finalize / generate）の温度指示。
# claude -p は温度パラメータを持たないため、設計意図（0.7=多様性 / 0.0=一貫性）を
# プロンプト指示で近似する。
_DIVERGE_HINT = (
    "多様性・発散を重視せよ。最も型破りな可能性まで自由に発想し、"
    "自分の観点を強く主張せよ。"
)
_CONSISTENT_HINT = (
    "一貫性と明瞭さを重視せよ。与えられた材料だけを使い、"
    "定型的で過不足のない回答に仕上げよ。"
)


class ClaudeCodeClient:
    """Claude Code CLI を 1 コールごとに起動する生成アダプタ。

    Generator プロトコル（generate(system, user, *, temperature)）を満たす。
    空応答・異常終了は「崩れた出力」として再試行する（broken output → regenerate 方式）。
    """

    def __init__(self, *, max_retries: int = 3, timeout: int = 600) -> None:
        self.max_retries = max_retries
        self.timeout = timeout

    def generate(
        self,
        system: str,
        user: str,
        *,
        temperature: float | None = None,
        on_chunk: Callable[[str], None] | None = None,
    ) -> str:
        """生成し、応答を返す。

        on_chunk が与えられたら、届いた文字列を逐次コールバックする（草案のストリーム保存）。
        claude -p --output-format stream-json の assistant イベントは累積テキストを運ぶため、
        前回分からの差分を取り出して on_chunk に流す。応答が速い場合は 1 イベントで全文が届く
        （トークン単位ではなくバースト配送）。届いた途中までの文字列は部分文として返し、
        完全性ガード側が「打ち切り」と判定して再生成する（このときファイルは空に戻る）。
        """
        prompt = self._build_user(system, user, temperature)
        last_err = ""
        for attempt in range(self.max_retries):
            try:
                text = self._run_stream(prompt, system, on_chunk)
            except RuntimeError as exc:
                # 空応答・異常終了（部分テキストが無い時だけ発生）。再試行可能。
                text = ""
                last_err = str(exc)
            if text:
                return text
            if attempt < self.max_retries - 1:
                # 指数バックオフ + ゲートウェイ負荷軽減
                time.sleep(2**attempt + 2)
        raise RuntimeError(f"Claude API 呼び出しに失敗しました: {last_err}")

    def _run_stream(self, prompt: str, system: str, on_chunk) -> str:
        """claude -p をストリーム起動し、assistant イベントの累積テキストを逐次 on_chunk に流す。

        stream-json は改行区切り JSON を吐く。assistant イベントの message.content 内の
        text ブロックが累積テキストを持つため、前回分からの差分（text[len(cumulative):]）だけを
        返す。timeout を超えたらプロセスを kill し、届いた分を返す（完全性ガードが再生成する）。
        """
        proc = subprocess.Popen(
            [
                "claude", "-p", "--verbose", "--output-format", "stream-json",
                "--system-prompt", system,
                prompt,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        chunks: list[str] = []
        cumulative = ""
        stderr = ""
        deadline = time.monotonic() + self.timeout
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                if time.monotonic() > deadline:
                    proc.kill()
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    continue  # ストリームに混ざる非JSON行（診断ログ等）は無視
                if not isinstance(event, dict) or event.get("type") != "assistant":
                    continue  # JSONオブジェクトでない行（素の文字列等）も無視
                for block in event.get("message", {}).get("content", []):
                    if block.get("type") != "text":
                        continue
                    text = block.get("text", "")
                    if len(text) > len(cumulative):
                        delta = text[len(cumulative):]  # 累積テキストからの差分
                        cumulative = text
                        chunks.append(delta)
                        if on_chunk is not None:
                            on_chunk(delta)
        finally:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            if proc.stderr is not None:
                stderr = proc.stderr.read()
        if chunks:
            # 部分文（打ち切り含む）はそのまま返し、完全性ガード側の判定に委ねる。
            # 部分が書かれたファイルは再生成時に空に戻るため、重複追記は起きない。
            return "".join(chunks)
        if proc.returncode != 0:
            raise RuntimeError(
                f"claude -p が空応答/異常終了（exit={proc.returncode}, stderr={stderr[:120]!r}）"
            )
        return ""

    @staticmethod
    def _build_user(system: str, user: str, temperature: float | None) -> str:
        """温度の設計意図をプロンプト指示で近似する。"""
        if temperature is not None and temperature >= 0.5:
            return f"[発散を重視]\n{_DIVERGE_HINT}\n\n{user}"
        if temperature is not None and temperature < 0.5:
            return f"[一貫性を重視]\n{_CONSISTENT_HINT}\n\n{user}"
        return user
