"""Claude Code CLI（claude -p）経由の生成アダプタ。

各コールを 1 つの `claude -p` プロセスとして起動する——各エージェントを独立した
サブエージェントとして起動し、互いの文脈を共有しない独立起動をライブラリで実現する。
system（ペルソナ）は `--system-prompt` で渡す。system が空のとき（素の生成＝指示のみ）は
`--system-prompt` を省略し、中性ディレクトリから起動する。これはリポジトリの CLAUDE.md
（リポジトリの自己記述）を読み込ませないためで、素の生成がリポジトリの機構の存在を
知らない「指示のみ」の答えを出す前提を守る。

背景: 生 SDK（anthropic.Anthropic）は Claude Code 互換ゲートウェイが間欠的に空応答
（200・空文字列、stop=max_tokens）を返す環境で不安定だった（2026-08-08 実測:
長いプロンプトで成功率 ~1/3）。同じゲートウェイでも Claude Code CLI 経由は安定して
応答する（実測: 昇華推理 15KB を完全出力）。温度は CLI に直接渡せないため、
発散（高温度相当）／一貫性（低温度相当）の指示をプロンプトに含めて近似する。
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from typing import Callable

from elevate import i18n

# 発散（diverge / aufheben）と一貫性（finalize / generate）の温度指示。
# claude -p は温度パラメータを持たないため、設計意図（0.9=極限の逸脱 / 0.0=一貫性）を
# プロンプト指示で近似する。ja 定数は後方互換。正本は prompts/{lang}.json の adapters 節。
_DIVERGE_HINT = (
    "可能な限り逸脱・発散せよ。他の観点と相容れない極限まで自説を推し進め、"
    "統計的平均に回収されない過激な個別解を提示せよ。"
    "中間解や妥協案は出すな——この発散は後の昇華（アウフヘーベン）の素材である。"
    "自説を「唯一の真理」として限界まで主張せよ。"
)
_CONSISTENT_HINT = (
    "一貫性と明瞭さを重視せよ。与えられた止揚の基盤だけを使い、"
    "超越的統合を過不足なく明瞭に表現せよ。"
    "材料を超えた推論は加えず、提示された結論を誠実に仕上げよ。"
)


class ClaudeCodeClient:
    """Claude Code CLI を 1 コールごとに起動する生成アダプタ。

    Generator プロトコル（generate(system, user, *, temperature)）を満たす。
    空応答・異常終了は「崩れた出力」として再試行する（broken output → regenerate 方式）。
    lang で温度ヒントの言語を選ぶ（既定は i18n 解決）。
    """

    def __init__(self, *, max_retries: int = 3, timeout: int = 600, lang: str | None = None) -> None:
        self.max_retries = max_retries
        self.timeout = timeout
        self.lang = i18n.resolve_lang(lang)
        self.prompts: dict = i18n.load_prompts(self.lang)

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
        prompt = self._localized_user(user, temperature)
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
        cmd = ["claude", "-p", "--verbose", "--output-format", "stream-json"]
        if system and system.strip():
            cmd += ["--system-prompt", system]
        cmd.append(prompt)
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            # 中性ディレクトリから起動し、リポジトリの CLAUDE.md（リポジトリの自己記述）を
            # 読み込ませない。素の生成（指示のみ）は言うまでもなく、昇華側も各コールは
            # 自己完結したプロンプトなので、リポジトリ文脈に依存しない（独立サブエージェント）。
            cwd=tempfile.gettempdir(),
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
        """温度の設計意図をプロンプト指示で近似する（ja 定数で近似。言語は generate 側で解決）。"""
        if temperature is not None and temperature >= 0.5:
            return f"[発散を重視]\n{_DIVERGE_HINT}\n\n{user}"
        if temperature is not None and temperature < 0.5:
            return f"[一貫性を重視]\n{_CONSISTENT_HINT}\n\n{user}"
        return user

    def _localized_user(self, user: str, temperature: float | None) -> str:
        """温度の設計意図を、このクライアントの言語のヒントで近似する。"""
        ad = self.prompts.get("adapters", {})
        if temperature is not None and temperature >= 0.5:
            hint = ad.get("DIVERGE_HINT", _DIVERGE_HINT)
            prefix = ad.get("DIVERGE_PREFIX", "[発散を重視]")
            return f"{prefix}\n{hint}\n\n{user}"
        if temperature is not None and temperature < 0.5:
            hint = ad.get("CONSISTENT_HINT", _CONSISTENT_HINT)
            prefix = ad.get("CONSISTENT_PREFIX", "[一貫性を重視]")
            return f"{prefix}\n{hint}\n\n{user}"
        return user
