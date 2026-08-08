"""elevate-draft-engine — 複数の独立した草案を統合して一段高い成果物を生むエンジン。

## 構造（DIVERGE → SYNTHESIZE）

    タスク
      │
      ├─→ [Draft: strategist]     価値
      ├─→ [Draft: differentiator] 独自性
      ├─→ [Draft: humanist]       共感
      ├─→ [Draft: futurist]       将来性
      ├─→ [Draft: designer]       体験設計
      ├─→ [Draft: visionary]      世界観
      ├─→ [Draft: implementer]    実現性
      └─→ [Draft: storyteller]    物語
              │
              ↓
       [Reconcile: 矛盾解決推理]   ← エージェント間の衝突を検出し、一段高い位置から解決する
              │                     （思考の土台。読者向けではない）
              ↓
       [Finalize: 最終化]          ← 解決済み推理だけを読み、明瞭な最終分析に仕上げる
              │
              ↓
         最終成果物

肝は「複数の全く異なった draft を統合する」こと。草案生成（diverge）は前段に過ぎず、
核心価値は synthesize（矛盾解決推理 → 最終化）にある。各エージェントは「より良いものを
作る」クリエイター目線で統一され、エージェント同士の生産的衝突が統合解の源泉になる。

エージェントは**1エージェント=1ファイル**方式（frontmatter + ペルソナ本文）で
agents/{name}.md に配置する。正本はファイル。
ユーザーは add_agent() / remove_agent() で拡張でき、synthesize() は人間が書いた草案など
外部草案も受け付ける。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

# ---- 素の生成（単発） ----
ANALYSIS_SYSTEM = (
    "あなたはAIサービス企画の専門家です。与えられたテーマを"
    "Target（対象顧客）・Value（提供価値）・Risk（リスク）・Opportunity（機会）の"
    "4観点で分析してください。分析は具体的・整合的・実行可能であること。"
)

# ---- デフォルトエージェント（全クリエイター目線） ----
# 各エージェントは agents/{name}.md に frontmatter（name, description）+ ペルソナ本文として
# 配置する。正本はファイル。
# 温度は draft_temperature（既定 0.7）で多様性を確保。
DEFAULT_AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"


def _parse_agent_file(text: str) -> tuple[dict[str, str], str]:
    """frontmatter（---で挟んだ YAML 風 key: value）+ 本文を分離する。"""
    m = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return {}, text.strip()
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip().strip('"').strip("'")
    return fm, text[m.end():].strip()


def load_agents(agents_dir: str | Path | None = None) -> dict[str, str]:
    """agents/*.md から {エージェント名: システムプロンプト} を読み込む。

    エージェント名は frontmatter の name（なければファイル名）。ファイル名順（アルファベット順）。
    ディレクトリが無い・ファイルが無い場合は空 dict（エージェント0のエンジンとして動く）。
    """
    d = Path(agents_dir) if agents_dir else DEFAULT_AGENTS_DIR
    result: dict[str, str] = {}
    if not d.is_dir():
        return result
    for path in sorted(d.glob("*.md")):
        fm, body = _parse_agent_file(path.read_text())
        name = fm.get("name") or path.stem
        if body:
            result[name] = body
    return result


def _strip_strong_claim(prompt: str) -> str:
    """エージェントプロンプトから「最強の主張」断言枠を除去する（アブレーション用）。

    「草案の作り方」の「枠を埋める」ステップと、末尾の「## 最強の主張」セクションを除去する。
    reconcile は草案本文全体からも最強の主張を拾えるため、枠が無くても統合は機能する
    （枠は「確実に拾うための定型」であり、必須ではない）。枠あり/なしの統合品質差を
    測定したい場合（--no-strong-claim など）に使う。
    """
    # 1) 「草案の作り方」内の「枠を埋める」ステップ（数字付き箇条 + 1行の説明）を除去
    text = re.sub(r"(?m)^\d+\. \*\*枠を埋める\*\*:.*\n", "", prompt)
    # 2) 「## 最強の主張」セクション（末尾まで）を除去
    text = re.sub(r"\n## 最強の主張\n.*", "", text, flags=re.DOTALL)
    return text.rstrip()


# ---- 単発統合（method="single-pass"） ----
SYNTHESIS_SYSTEM = (
    "あなたは統合分析者です。同じテーマに対する複数の独立した草案を統合し、観点間の矛盾を"
    "解消した一段高い分析を提示してください。"
)

SYNTHESIS_INSTRUCTION = (
    "以下は、同じテーマを異なる観点から分析した複数の独立した草案である。これらを読み、"
    "以下を満たす統合分析を作成せよ:\n"
    "1. 各草案の最強の主張と、それに対する最強の反論をそれぞれ特定せよ\n"
    "2. 観点間の矛盾を無視せず、解消する論理を示せ（なぜ一方の懸念は致命傷ではないのか、"
    "あるいはある観点の楽観はどの条件で正当化されるのか）\n"
    "3. 最も強い反論に直接答えよ（回避せず、正面から論破または条件付き受容せよ）\n"
    "4. 確信できる点は断定的に、不確実な点は前提として明示せよ\n"
    "5. 統合を経て初めて得られた新たな視点があれば、それを明示せよ\n\n"
    "単なる「全観点の併記」や「平均化」は不合格。矛盾を解決する一段高い推論を要求する。"
)

# ---- 2段階統合（method="two-stage"） ----
# 単発統合は推理と表現を同時に要求し、推理の冗長さが明瞭さを損なう。推理（Reconcile）と
# 表現（Finalize）を分離し、深度と明瞭さを同時に確保する。

# 推理（Reconcile）: 観点間の矛盾の解決論理を深く言語化する。読者向けの成果物ではなく
# 「思考の土台」。中間思考を含んでよいため、最終成果物の明瞭さに縛られず深く論証できる。
RECONCILIATION_SYSTEM = (
    "あなたは統合推理家です。同じテーマに対する複数の独立した草案を読み、観点間の矛盾を"
    "解消する推理を記述してください。この推理は後続の工程が最終分析に仕上げるための"
    "思考の土台であり、読者が直接見る成果物ではありません。論証の丁寧さと深さを最優先し、"
    "結論の一部が未確定でも構いません。"
)

RECONCILIATION_INSTRUCTION = (
    "以下は、同じテーマを異なる観点から分析した複数の独立した草案である。これらを読み、"
    "以下を明らかにする推理を記述せよ:\n"
    "1. 各草案の最強の主張（他の観点がこれに反論しそうなもの）\n"
    "2. 観点同士の最強の対立（どの観点がどこで衝突しているか）\n"
    "3. 対立の本質がどこにあるか\n"
    "4. その対立を解消する解決仮説（なぜ一方の懸念は致命傷ではないのか、"
    "あるいはある観点の楽観はどの条件で正当化されるのか）\n"
    "5. 統合を経て初めて得られる新たな視点\n\n"
    "単なる「全観点の併記」や「平均化」は不合格。観点間の矛盾を解決する一段高い推論を要求する。\n"
    "この推理は後続工程の最終分析の材料であり、読者に直接提示する成果物ではない。論証を尽くしてよい。"
)

# 表現（Finalize）: 解決済みの推理だけを読み、単発生成と同水準の明瞭な最終分析に仕上げる。
# 推理の中間思考（草案同士の比較・経緯説明）を最終成果物に残さない。
FINALIZE_SYSTEM = (
    "あなたはAIサービス企画の専門家です。与えられた「矛盾解決推理」を、読み手に直接届く最終分析として"
    "仕上げてください。推理の過程（草案同士の比較・経緯説明）は含めず、確定した結論だけを整理して"
    "記述してください。分析は具体的・整合的・実行可能であること。"
)

FINALIZE_INSTRUCTION = (
    "上記の推理に基づき、このテーマの最終分析を記述せよ:\n"
    "1. 推理の中間思考（草案同士の比較・経緯説明）は含めず、確定した結論だけを書く\n"
    "2. Target（対象顧客）・Value（提供価値）・Risk（リスクとその対策）・Opportunity（機会）の"
    "4観点で整理する\n"
    "3. 具体的・整合的・実行可能であること\n"
    "4. 確信できる点は断定的に、不確実な点は前提として明示する"
)

# ---- 草案生成の温度（多様性の確保）。統合・最終化・評価は 0.0（一貫性のため） ----
DRAFT_TEMPERATURE = 0.7

# ---- 打ち切りガード（崩れたら再生成） ----
_SYNTHESIS_TERMINAL_MARKERS = ("。", "！", "？", "…", "」", "）", "}", ")", '"', ".", "!", "?")

# 統合生成の再生成上限（打ち切りが直らない場合の明示的失敗の境界）
SYNTHESIS_MAX_ATTEMPTS = 3

# 矛盾解決推理の完全性下限。
# 推理は読者向けの散文ではなく「思考の土台」で、終端記号（。！」）等）で終わるとは限らない
# （矢印「→」・箇条書き・前置きで終わりうる）。文途中の打ち切りは最終化が部分吸収できるため、
# ここでは「推理が実質的に存在するか（極端に短い=推理を放棄した出力の防止）」だけを判定する。
RECONCILIATION_MIN_LENGTH = 30


class Generator(Protocol):
    """生成系 Claude のインターフェイス。temperature はエージェント草案の多様性確保に使う。

    on_chunk はストリーム追記用のコールバック（草案の逐次保存）。実装が未対応でも
    省略すれば呼ばれないため、既存クライアントはそのまま動く。
    """

    def generate(
        self,
        system: str,
        user: str,
        *,
        temperature: float | None = None,
        on_chunk: Callable[[str], None] | None = None,
    ) -> str: ...


@dataclass(frozen=True)
class Draft:
    """1つの草案。agent はエージェント名（例: "strategist"、外部草案なら "external" 等）。"""

    agent: str
    content: str


# ---- 完全性ガード ----

def _synthesis_is_complete(text: str) -> bool:
    """最終分析・単発統合が文として終端しているか。空応答と打ち切り（終端記号なし）を区別する。"""
    return bool(text) and text.rstrip().endswith(_SYNTHESIS_TERMINAL_MARKERS)


def _reconciliation_is_complete(text: str) -> bool:
    """矛盾解決推理の完全性判定。空・推理放棄（極端に短い）を再生成対象にする。"""
    return bool(text) and len(text.strip()) >= RECONCILIATION_MIN_LENGTH


def _draft_is_complete(text: str) -> bool:
    """草案の完全性判定。文途中で切れた打ち切りを再生成対象にする。

    草案は統合段階（reconcile）の読み物で、途中で切れると内容が欠落するため終端記号で
    判定する（2026-08-08 実測: ゲートウェイが "…横のつながりが強い。「この健保" で
    打ち切った草案を素通ししていた）。末尾のマークダウン装飾（** の閉じ等）は除いて
    判定する（claude -p 経由の草案が "…。**" で終わることがある）。「最強の主張」枠の
    有無は必須にしない——枠が無くても reconcile は本文全体から最強の主張を拾える。
    """
    if not text:
        return False
    stripped = text.rstrip("*`~\t\n ")
    return stripped.endswith(_SYNTHESIS_TERMINAL_MARKERS)


def _generate_with_completeness_guard(
    generator: Generator,
    system: str,
    user: str,
    *,
    temperature: float | None = None,
    label: str = "統合生成",
    is_complete=None,
    sink: Path | None = None,
) -> str:
    """指定 system で生成し、完全性ガード（broken output → regenerate）を適用する。

    構造が既知の呼び出し側で決定的に検証し、崩れた出力は再生成する。
    上限回数で直らない場合は明示的失敗（不完全出力を評価に渡さない）。
    temperature を渡すことで、推理は温度0.7、最終化は0.0を実現する。
    is_complete を渡すと判定を差し替えられる（最終化=文終端 / 推理=長さ下限）。

    sink が与えられたら、生成前に空ファイルを作り、on_chunk 経由で届く文字列を
    逐次追記する（草案のストリーム保存）。打ち切りで再生成するときはファイルを
    空に戻してから再開するため、失敗試行の部分文がファイルに残らない。
    """
    if is_complete is None:
        is_complete = _synthesis_is_complete
    last_err = ""
    for _ in range(SYNTHESIS_MAX_ATTEMPTS):
        kwargs = {"system": system, "user": user, "temperature": temperature}
        handle = None
        if sink is not None:
            sink.parent.mkdir(parents=True, exist_ok=True)
            handle = open(sink, "w", encoding="utf-8")  # 生成前に空ファイルを作る

            def on_chunk(delta: str, handle=handle) -> None:
                handle.write(delta)
                handle.flush()

            kwargs["on_chunk"] = on_chunk
        try:
            artifact = generator.generate(**kwargs)
        finally:
            if handle is not None:
                handle.close()
        if is_complete(artifact):
            return artifact
        last_err = f"{label}が打ち切られた/不完全（…{artifact[-20:]!r}）"
    raise RuntimeError(f"{label}が{SYNTHESIS_MAX_ATTEMPTS}回連続で打ち切り/不完全: {last_err}")


def _generate_synthesis(generator: Generator, synthesis_user: str) -> str:
    """単発統合（method="single-pass"）を生成する。打ち切りは再生成し、直らない場合は明示的に失敗させる。"""
    return _generate_with_completeness_guard(
        generator, ANALYSIS_SYSTEM + SYNTHESIS_SYSTEM, synthesis_user, label="統合生成"
    )


def _generate_reconciliation(generator: Generator, reconcile_user: str, *, temperature: float) -> str:
    """矛盾解決推理を生成する。極端に短い（推理を放棄した）出力は再生成。

    推理は「思考の土台」で文終端記号で終わるとは限らないため、終端記号チェックは誤判定を
    招く（実測: 6104字の完全な推理が再生成ループに落ちた）。長さ下限で「推理が実質的に
    存在するか」だけを判定する。空応答はクライアントが再試行済み。温度は 0.7（多様性・深度）。
    """
    return _generate_with_completeness_guard(
        generator, RECONCILIATION_SYSTEM, reconcile_user,
        temperature=temperature, label="矛盾解決推理",
        is_complete=_reconciliation_is_complete,
    )


def _generate_finalize(generator: Generator, finalize_user: str) -> str:
    """最終分析を生成する。打ち切りは再生成。温度は 0.0（一貫性。素の生成と同じ明瞭な表形式）。"""
    return _generate_with_completeness_guard(
        generator, ANALYSIS_SYSTEM + FINALIZE_SYSTEM, finalize_user, label="最終分析"
    )


def _generate_draft(
    generator: Generator, system: str, user: str, *, temperature: float, sink: Path | None = None
) -> str:
    """エージェント草案を生成する。文途中の打ち切りは再生成。温度は draft_temperature。

    推理・最終化と同じ完全性ガード（broken output → regenerate）を草案にも適用する。
    sink が与えられたら、生成前に空ファイルを作り、生成中に逐次追記する。
    """
    return _generate_with_completeness_guard(
        generator, system, user, temperature=temperature, label="草案生成",
        is_complete=_draft_is_complete, sink=sink,
    )


# ---- プロンプト構築（ステートレス生成器への明示補償） ----

def _drafts_block(drafts: list[Draft]) -> list[str]:
    """各草案を「エージェント名付き」のブロックに整形する。"""
    return [f"【草案（観点: {d.agent}）】\n{d.content}" for d in drafts]


def _build_reconciliation_prompt(task: str, drafts: list[Draft]) -> str:
    """矛盾解決推理の user プロンプトを組み立てる。"""
    parts = [f"【タスク】\n{task}"] if task else []
    parts += _drafts_block(drafts)
    parts.append(f"【推理指示】\n{RECONCILIATION_INSTRUCTION}")
    return "\n\n".join(parts)


def _build_synthesis_prompt(task: str, drafts: list[Draft]) -> str:
    """単発統合（method="single-pass"）の user プロンプトを組み立てる。"""
    parts = [f"【タスク】\n{task}"] if task else []
    parts += _drafts_block(drafts)
    parts.append(f"【統合指示】\n{SYNTHESIS_INSTRUCTION}")
    return "\n\n".join(parts)


def _build_finalize_prompt(task: str, reconciliation: str) -> str:
    """最終分析の user プロンプトを組み立てる。

    最終化は草案ではなく「解決済みの推理」だけを読む。推理の中間思考が最終成果物に
    漏れないよう、確定した結論だけを書かせる。
    """
    parts = [f"【タスク】\n{task}"] if task else []
    parts += [
        f"【矛盾解決推理】\n{reconciliation}",
        f"【最終化指示】\n{FINALIZE_INSTRUCTION}",
    ]
    return "\n\n".join(parts)


# ---- エンジン本体 ----

class DraftEngine:
    """複数のエージェント（観点）から草案を生成し、統合して一段高い成果物を生むエンジン。

    - `generate(task)`  … 素のAI（単発生成）。1 call
    - `diverge(task)`   … 登録エージェントで独立草案を生成。8 calls（既定）
    - `synthesize(drafts)` … 外部草案も含む複数草案を統合（核心）
    - `elevate(task)`   … diverge → synthesize の一気ラッパー

    スロットル（空応答対策）は client（ClaudeClient）側で効いている。
    """

    def __init__(
        self,
        client: Generator,
        *,
        draft_temperature: float = DRAFT_TEMPERATURE,
        agents_dir: str | Path | None = None,
        agents: dict[str, str] | None = None,
        strong_claim_frame: bool = True,
    ):
        self.client = client
        self.draft_temperature = draft_temperature
        if agents is not None:
            self._agents: dict[str, str] = dict(agents)
        else:
            self._agents = load_agents(agents_dir)
        # 断言枠アブレーション: strong_claim_frame=False のとき「最強の主張」枠を除去する
        # （枠あり/なしの統合品質差を測定したいとき用。既定は枠あり = 従来動作）。
        if not strong_claim_frame:
            self._agents = {name: _strip_strong_claim(p) for name, p in self._agents.items()}

    # ---- 素の生成 ----

    def generate(self, task: str) -> str:
        """素のAI（単発生成）: 温度 0.0 で分析成果物を生成する。1 call。"""
        return self.client.generate(system=ANALYSIS_SYSTEM, user=task)

    # ---- エージェント管理 ----

    def list_agents(self) -> list[str]:
        return list(self._agents)

    def add_agent(self, name: str, system_prompt: str) -> None:
        if name in self._agents:
            raise ValueError(f"エージェントが既に登録されています: {name!r}")
        self._agents[name] = system_prompt

    def remove_agent(self, name: str) -> None:
        if name not in self._agents:
            raise ValueError(f"エージェントが登録されていません: {name!r}")
        del self._agents[name]

    # ---- DIVERGE ----

    def diverge(
        self,
        task: str,
        agents: list[str] | None = None,
        on_draft=None,
        draft_dir: Path | None = None,
    ) -> list[Draft]:
        """指定エージェント（既定は登録済み全エージェント）で独立草案を生成する。

        役割多様性（エージェントごとの system）＋温度多様性（draft_temperature）で独立した草案を保証。
        on_draft(draft) を渡すと、各草案の生成完了時点で逐次コールバックされる
        （進捗表示に使う。全生成完了を待たないため、途中で失敗しても
        生成済み分の草案を失わない）。

        draft_dir を渡すと、各草案は生成前に空の draft_{name}.md として作成され、
        生成中に逐次追記される（claude-code エンジンのストリーム対応クライアントで
        実際に逐次追記される。未対応クライアントでは生成完了時に一括書き込み）。
        """
        names = agents if agents is not None else list(self._agents)
        unknown = [a for a in names if a not in self._agents]
        if unknown:
            raise ValueError(f"未登録のエージェント: {unknown}（登録済み: {list(self._agents)}）")
        drafts: list[Draft] = []
        for name in names:
            sink = None
            if draft_dir is not None:
                sink = draft_dir / f"draft_{name}.md"
            content = _generate_draft(
                self.client, self._agents[name], task,
                temperature=self.draft_temperature, sink=sink,
            )
            draft = Draft(agent=name, content=content)
            drafts.append(draft)
            if on_draft is not None:
                on_draft(draft)
        return drafts

    # ---- SYNTHESIZE（核心） ----

    def synthesize_with_reconciliation(
        self, drafts: list[Draft], method: str = "two-stage", task: str = ""
    ) -> tuple[str, str]:
        """統合し、推理（統合の下地）と成果物を返す。

        戻り値: (reconciliation, artifact)。method="single-pass" は推理が無いため ("", artifact)。
        推理を保存したい呼び出し側（CLI の --out 等）はこちらを使う。
        """
        if not drafts:
            raise ValueError("統合対象の草案がありません")
        if method == "two-stage":
            reconcile_user = _build_reconciliation_prompt(task, drafts)
            reconciliation = _generate_reconciliation(
                self.client, reconcile_user, temperature=self.draft_temperature
            )
            finalize_user = _build_finalize_prompt(task, reconciliation)
            return reconciliation, _generate_finalize(self.client, finalize_user)
        if method == "single-pass":
            synthesis_user = _build_synthesis_prompt(task, drafts)
            return "", _generate_synthesis(self.client, synthesis_user)
        raise ValueError(f"未知の method: {method!r}（'two-stage' または 'single-pass'）")

    def synthesize(self, drafts: list[Draft], method: str = "two-stage", task: str = "") -> str:
        """複数の独立草案を統合して一段高い成果物を返す。

        - method="two-stage": 矛盾解決推理 → 最終化（2段階統合。温度: 推理 0.7 / 最終化 0.0）
        - method="single-pass":  単発統合（1コール）

        drafts は外部草案（人間の専門家が書いた分析、別モデルの出力等）でもよい。
        出所を問わず「複数の異なる視点」を突っ込めば一段高い統合を返す。
        """
        _, artifact = self.synthesize_with_reconciliation(drafts, method=method, task=task)
        return artifact

    # ---- 便利ラッパー ----

    def elevate(self, task: str, method: str = "two-stage", agents: list[str] | None = None) -> str:
        """diverge → synthesize を一気に行う。"""
        drafts = self.diverge(task, agents=agents)
        return self.synthesize(drafts, method=method, task=task)
