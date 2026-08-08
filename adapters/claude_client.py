"""Claude API クライアント（第一アダプタ）。

生成（Skill）と評価（Evaluation Engine）で**必ず別モデル系統**を使う。
生成と評価が同一系統だと、評価者が自分の成果物を採点する循環評価になるため、
系統分離は実装の中核。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import anthropic

# モデル系統（独立評価系統）
# 生成と評価で異なるモデル系統を使う。両者が同一だと循環評価になるため禁止。
DEFAULT_GENERATION_MODEL = "claude-sonnet-4-5"
DEFAULT_EVALUATION_MODEL = "claude-haiku-4-5"


@dataclass
class ClaudeConfig:
    api_key: str = ""
    auth_token: str = ""
    base_url: str = ""
    generation_model: str = DEFAULT_GENERATION_MODEL
    evaluation_model: str = DEFAULT_EVALUATION_MODEL
    max_tokens: int = 4096
    temperature: float = 0.0
    max_retries: int = 3
    min_interval_seconds: float = 0.0  # 0 以下ならスロットル無効（実実行は main.py から 2.0 を渡す）

    def __post_init__(self) -> None:
        """api_key か auth_token のどちらか一方が必須。両方指定時は api_key 優先。"""
        if not self.api_key and not self.auth_token:
            raise ValueError(
                "Claude の認証情報がありません。api_key または auth_token を設定してください。"
            )
        self.validate_lineage_separation()

    def validate_lineage_separation(self) -> None:
        """生成系と評価系の系統分離を保証する（同一系統は循環評価を招く）。"""
        if self.generation_model == self.evaluation_model:
            raise ValueError(
                "generation_model と evaluation_model が同一です。"
                "独立評価系統を保つため異なるモデルを指定してください。"
            )


class ClaudeClient:
    """Anthropic SDK の薄いラッパー。系統分離をAPIで強制する。

    - `generate()` … Skill（生成）専用。生成系モデルを使用
    - `evaluate()` … Evaluation Engine（評価）専用。評価系モデルを使用
    """

    def __init__(self, config: ClaudeConfig | None = None):
        config = config or self._default_config()
        config.validate_lineage_separation()
        self.config = config
        # ゲートウェイ対応: api_key 優先、なければ auth_token（ANTHROPIC_AUTH_TOKEN 経由）
        kwargs: dict = {"base_url": config.base_url or None}
        if config.api_key:
            kwargs["api_key"] = config.api_key
        elif config.auth_token:
            kwargs["auth_token"] = config.auth_token
        self.client = anthropic.Anthropic(**kwargs)
        # スロットル用の最終リクエスト時刻（time.monotonic ベース）
        self._last_request_at = 0.0

    @staticmethod
    def _default_config() -> ClaudeConfig:
        """環境変数から認証情報を解決する。

        通常の Anthropic API:    ANTHROPIC_API_KEY
        Claude Code 互換ゲートウェイ: ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL
        """
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "")
        # 実ゲートウェイ（deepseek 経由）は連続呼び出しで空応答を返す率が上がるため、
        # 既定で最小リクエスト間隔を 2 秒に設定（CLAUDE_MIN_INTERVAL_SECONDS で変更可）。
        min_interval = float(os.environ.get("CLAUDE_MIN_INTERVAL_SECONDS", "2.0"))
        # 空応答は間欠的（長い system で失敗率が上がる）ため、再試行上限を 6 回に強化。
        # 3 回では高負荷時に全滅し得る（2026-08-08 実測: strategist@0.7 で約2/3空応答）。
        max_retries = int(os.environ.get("CLAUDE_MAX_RETRIES", "6"))
        return ClaudeConfig(
            api_key=api_key,
            auth_token=auth_token,
            base_url=base_url,
            min_interval_seconds=min_interval,
            max_retries=max_retries,
        )

    def generate(self, system: str, user: str, *, temperature: float | None = None) -> str:
        """生成系モデルで呼び出す（Skill: Analysis 用）。

        temperature は per-call で上書き可能（草案生成（diverge）で多様性を
        確保するために 0.7 を渡す。省略時は config の既定温度）。
        """
        return self._call(self.config.generation_model, system, user, temperature=temperature)

    def evaluate(self, system: str, user: str) -> str:
        """評価系モデルで呼び出す（Evaluation Engine 用）。"""
        return self._call(self.config.evaluation_model, system, user)

    def _call(
        self, model: str, system: str, user: str, *, temperature: float | None = None
    ) -> str:
        """モデルを呼び出し、テキスト応答を返す。

        空応答は「崩れた出力」として再試行する（broken output → regenerate 方針）。
        実ゲートウェイ（deepseek 経由）では稀に空応答を返すことが観測され、
        これをそのまま返すと空成果物のまま評価され成功率を歪める（2026-08-08 dev検証で35%空）。
        文途中の打ち切りはここで判定しない（JSON応答の誤検出を避ける）。構造が既知の
        呼び出し側（統合出力など）が再生成を担当する。
        """
        temp = temperature if temperature is not None else self.config.temperature
        last_err: Exception | None = None
        for attempt in range(self.config.max_retries):
            try:
                self._throttle()
                response = self.client.messages.create(
                    model=model,
                    max_tokens=self.config.max_tokens,
                    temperature=temp,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                text = "".join(
                    b.text for b in response.content if getattr(b, "type", "") == "text"
                ).strip()
                if text:
                    return text
                # 空応答は「崩れた出力」として再試行（broken output → regenerate 方針）。
                # 文途中の打ち切りはここでは判定しない（JSON応答を誤検出するため）。
                # 構造が既知の呼び出し側（統合出力など）で再生成を担当する。
                last_err = RuntimeError("空の応答（モデルが空文字列を返した）")
                if attempt < self.config.max_retries - 1:
                    time.sleep(2**attempt)
            except (anthropic.APIStatusError, anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
                last_err = e
                if attempt < self.config.max_retries - 1:
                    time.sleep(2**attempt)  # 指数バックオフ
        raise RuntimeError(f"Claude API 呼び出しに失敗しました: {last_err}") from last_err

    def _throttle(self) -> None:
        """最小リクエスト間隔（スロットル）を強制する。

        実ゲートウェイ（api.deepseek.com/anthropic）は連続呼び出し（バースト）で
        空応答（200・空文字列）を返す率が上昇する（~40% @ 0秒間隔、2秒間隔でほぼ解消）。
        全リクエスト（生成・評価・再試行含む）を最低 min_interval_seconds 空けて送ることで、
        この測定汚染を全条件に均等に抑える（2026-08-08 dev 検証の知見）。
        対象チューニングではないためゴールポストは動かさない。
        並列生成を導入する場合はこの時刻管理をロックで共有すること。
        """
        if self.config.min_interval_seconds <= 0:
            return
        now = time.monotonic()
        wait = self.config.min_interval_seconds - (now - self._last_request_at)
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()
