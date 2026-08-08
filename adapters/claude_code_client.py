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

import subprocess

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

    def generate(self, system: str, user: str, *, temperature: float | None = None) -> str:
        prompt = self._build_user(system, user, temperature)
        last_err = ""
        for attempt in range(self.max_retries):
            proc = subprocess.run(
                [
                    "claude", "-p", "--output-format", "text",
                    "--system-prompt", system,
                    prompt,
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            text = proc.stdout.strip()
            if text:
                return text
            last_err = f"claude -p が空応答/異常終了（exit={proc.returncode}, stderr={proc.stderr[:120]!r}）"
            if attempt < self.max_retries - 1:
                # 指数バックオフ + ゲートウェイ負荷軽減
                import time

                time.sleep(2**attempt + 2)
        raise RuntimeError(f"Claude API 呼び出しに失敗しました: {last_err}")

    @staticmethod
    def _build_user(system: str, user: str, temperature: float | None) -> str:
        """温度の設計意図をプロンプト指示で近似する。"""
        if temperature is not None and temperature >= 0.5:
            return f"[発散を重視]\n{_DIVERGE_HINT}\n\n{user}"
        if temperature is not None and temperature < 0.5:
            return f"[一貫性を重視]\n{_CONSISTENT_HINT}\n\n{user}"
        return user
