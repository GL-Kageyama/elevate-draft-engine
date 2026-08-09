"""elevate-draft-engine — 複数の独立した草案を昇華（アウフヘーベン）して一段高い成果物を生むエンジン。

## 構造（DIVERGE → AUFHEBEN → FINALIZE）

    タスク
      │
      ├─→ [Draft: strategist]     価値（可能な限り逸脱）
      ├─→ [Draft: differentiator] 独自性（可能な限り逸脱）
      ├─→ [Draft: humanist]       共感（可能な限り逸脱）
      ├─→ [Draft: futurist]       将来性（可能な限り逸脱）
      ├─→ [Draft: designer]       体験設計（可能な限り逸脱）
      ├─→ [Draft: visionary]      世界観（可能な限り逸脱）
      ├─→ [Draft: implementer]    実現性（可能な限り逸脱）
      └─→ [Draft: storyteller]    物語（可能な限り逸脱）
              │
              ↓
       [Aufheben: 弁証法的止揚]    ← 論理を超えた次元で各立場を否定しつつ保存し、昇華する
              │                     （思考の土台。読者向けではない）
              ↓
       [Finalize: 最終化]          ← 止揚の基盤だけを読み、超越的統合として仕上げる
              │
              ↓
         最終成果物

肝は「可能な限り逸脱・発散した個別解を、論理を超えた世界で昇華（アウフヘーベン）し、
超越的な統合解に到達する」こと。統合でなく、アウフヘーベン。
草案生成（diverge）は前段に過ぎず、核心価値は synthesize（弁証法的止揚 → 最終化）にある。
各エージェントは「極限まで逸脱する」クリエイターであり、その意図的不整合が昇華の源泉になる。
止揚は論理的な矛盾解消ではない——対立を包含しつつ一段高い次元へ引き上げる弁証法的跳躍である。

エージェントは**1エージェント=1ファイル**方式（frontmatter + ペルソナ本文）で
agents/{name}.md に配置する。正本はファイル。
ユーザーは add_agent() / remove_agent() で拡張でき、synthesize() は人間が書いた草案など
外部草案も受け付ける。
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

# ---- 素の生成（単発） ----
# 中立プロンプト: 複数視点を誘引しない（compare のベースライン公平性のため。
# 誘引すると単発呼び出しが内部で評議会を演じ、ELEVATE との差が測れなくなる）
ANALYSIS_SYSTEM = (
    "あなたは独立した分析者です。与えられたテーマを深く分析し、"
    "具体的・深い洞察を伴い、実行への手がかりを持つ分析を示してください。"
)

# ---- デフォルトエージェント（全クリエイター目線） ----
# 各エージェントは agents/{name}.md に frontmatter（name, description）+ ペルソナ本文として
# 配置する。正本はファイル。
# 温度は draft_temperature（既定 0.9）で可能な限りの逸脱・発散を確保。
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
    """エージェントプロンプトから旧「最強の主張」断言枠を除去する（アブレーション用）。

    「草案の作り方」の「枠を埋める」ステップと、末尾の「## 最強の主張」セクションを除去する。
    テーゼ集中形式（2026-08-09）以降の組み込みエージェントには旧枠が存在しないため実質
    no-op になるが、旧枠を持つカスタムエージェントが混入しても確実に除去する（後方互換の
    安全網）。インターフェースは strong_claim_frame パラメータのため維持する。
    """
    # 1) 「草案の作り方」内の「枠を埋める」ステップ（数字付き箇条 + 1行の説明）を除去
    text = re.sub(r"(?m)^\d+\. \*\*枠を埋める\*\*:.*\n", "", prompt)
    # 2) 「## 最強の主張」セクション（末尾まで）を除去
    text = re.sub(r"\n## 最強の主張\n.*", "", text, flags=re.DOTALL)
    return text.rstrip()


# ---- 単発昇華（method="single-pass"） ----
SYNTHESIS_SYSTEM = (
    "あなたは昇華者（Aufheber）です。同じテーマに対する複数の極端に逸脱した草案を読み、"
    "それらを論理的な妥協や平均化ではなく、より高次元へ止揚（アウフヘーベン）してください。"
    "各草案の一面的な正しさを否定しつつ、その真理の契機を保存し、矛盾を包括する"
    "新たな枠組みそのものを創出してください。"
)

SYNTHESIS_INSTRUCTION = (
    "以下は、同じテーマを異なる観点から極端に逸脱して書かれた複数の独立した草案である。"
    "これらを読み、以下を満たす止揚分析を作成せよ:\n"
    "1. 各草案の核心的主張を特定し、それがなぜ一面的か（何を見落としているか）を指摘せよ\n"
    "2. 各草案の真理の契機——一面性の奥にある本物の洞察——を抽出せよ\n"
    "3. 草案間の最も深い対立を特定せよ。論理的な解決（条件付き受容・妥協）ではなく、"
    "対立する真理を同時に成立させる新たな枠組みを創出せよ\n"
    "4. その枠組みは、どの単一草案にもなかったものでなければならない\n"
    "5. 創出した枠組みから各草案を再解釈したとき、それらはどう位置づけられるかを示せ\n"
    "6. 確信できる点は断定的に、不確実な点は前提として明示せよ\n\n"
    "単なる「全観点の併記」や「平均化」「論理的妥協」は不合格。"
    "矛盾を解消するのではなく、矛盾を包括する一段高い枠組みを創出することを要求する。"
)

# ---- 2段階止揚（method="two-stage"） ----
# 単発止揚は昇華と表現を同時に要求し、昇華推理の冗長さが明瞭さを損なう。
# 昇華（Aufheben）と表現（Finalize）を分離し、深度と明瞭さを同時に確保する。

# 昇華（Aufheben）: 各草案を否定しつつ保存し、矛盾を包括する新たな枠組みを創出する。
# 読者向けの成果物ではなく「思考の土台」。中間思考を含んでよいため、
# 最終成果物の明瞭さに縛られず深く飛躍できる。
AUFHEBEN_SYSTEM = (
    "あなたは弁証法的な昇華者（Aufheben practitioner）です。同じテーマに対する"
    "複数の独立した草案を読み、論理的「解決」ではなく弁証法的止揚（アウフヘーベン）"
    "によって一段高い次元へ引き上げてください。\n\n"
    "それぞれの草案は意図的に極限まで逸脱しています——論理での「矛盾解消」は"
    "できません。各立場の「一面的真理」を否定しつつ保存し、それらを包含する"
    "超越的な統合へと高めてください。\n\n"
    "この昇華は後続の工程が最終分析に仕上げるための思考の土台であり、"
    "読者が直接見る成果物ではありません。深度と大胆さを最優先し、"
    "結論の一部が未確定でも構いません。"
)

AUFHEBEN_INSTRUCTION = (
    "以下は、同じテーマを異なる観点から分析した、意図的に極限まで逸脱させた複数の独立草案である。"
    "これらを読み、弁証法的止揚（アウフヘーベン）を記述せよ:\n\n"
    "1. **否定（Negation）**: 各草案の「一面的真理」を特定し、その真理が「全体の真理」を"
    "僭称する限りにおいて否定せよ。各立場は正しい——しかしそれだけでは不十分である。"
    "否定は破壊ではなく限定である。\n\n"
    "2. **保存（Preservation）**: 否定した各立場の中に残る本物の洞察（truth-moment）を特定し、"
    "それがなぜ保存されるべきか——なぜ捨ててはならないのか——を記述せよ。\n\n"
    "3. **高次化（Elevation）**: 保存された洞察を、元の対立を包含する一段高い次元へと"
    "引き上げよ。ここでの「解決」は論理的妥協（「条件付きで正しい」「致命的ではない」）"
    "ではなく、対立の両項をそのまま含みながら、それらを超える新しい枠組みの創出である。\n\n"
    "4. **超越的視点**: この止揚を経て初めて見える、元のどの草案にもなかった視点——"
    "元の対立が「対立ですらなかった」と見える次元——を言語化せよ。\n\n"
    "単なる「全観点の併記」や「平均化」や「条件付き論理解決」は不合格。"
    "対立を「解消」するのではなく、対立そのものを素材として一段高い位置へと"
    "昇華することを要求する。\n"
    "この昇華は後続工程の最終分析の材料であり、読者に直接提示する成果物ではない。論証を尽くしてよい。"
)

# 表現（Finalize）: 止揚推理だけを読み、超越的統合解を明瞭な最終成果物に仕上げる。
# 昇華の中間思考（草案同士の比較・弁証法の手続き説明）を最終成果物に残さない。
FINALIZE_SYSTEM = (
    "あなたは超越的統合の表現者です。与えられた「止揚（アウフヘーベン）の基盤」を、"
    "読み手に直接届く最終分析として仕上げてください。止揚の過程（草案同士の比較・"
    "経緯説明）は含めず、高められた結論だけを整理して記述してください。"
    "分析は具体的・整合的・実行可能でありながら、元のどの草案にもなかった"
    "超越的な統合として提示すること。"
    "結論はコンパクトにまとめよ（概ね500〜1000字）。要点に絞って簡潔に書くこと。"
)

FINALIZE_INSTRUCTION = (
    "上記の止揚に基づき、このテーマの最終分析を記述せよ:\n"
    "1. 止揚の中間過程（草案同士の比較・経緯説明）は含めず、高められた結論だけを書く\n"
    "2. Target（対象顧客）・Value（提供価値）・Risk（リスクとその対策）・Opportunity（機会）の"
    "4観点で整理しつつ、これらを超越する統一的視座を示す\n"
    "3. 具体的・整合的・実行可能でありながら、元のどの草案にもなかった超越的統合であること\n"
    "4. 確信できる点は断定的に、不確実な点は前提として明示する\n"
    "5. 単なる「バランスの取れた報告書」ではなく、一段高い次元の理解を読者に与えること"
)

# ---- 論理一貫性の復元工程（--logic-check） ----
# 実測（n=1、旧5軸: creativity/logic）で ELEVATE は creativity +0.10 に対して logic -0.05。
# 昇華が「完成させる」より「多様化する」方向へ偏る可能性を示唆する（旧軸の観察。
# 2026-08-08 再調整(3)で5軸が多様性/統合性/超越性/誠実性/実用性に変わったため、
# この数値は旧軸のままの記録である）。最終化の後に論理的一貫性を検証・
# 復元する収束工程を構造として追加する（既定は無効。仮説の検証手段として使う）。
LOGIC_CHECK_SYSTEM = (
    "あなたは検証者です。与えられた成果物を読み、論理的矛盾・根拠の飛躍・"
    "整合性の欠如を検査してください。ただし、論理を超えた飛躍（アウフヘーベンによる"
    "枠組みの創出）は矛盾とは見なさず、その飛躍に内在的な破綻がある場合のみ指摘せよ。"
    "矛盾を検出した場合は修正した最終版だけを出力し、矛盾が無ければ元の成果物を"
    "そのまま出力してください。"
)

LOGIC_CHECK_INSTRUCTION = (
    "以下の成果物を論理的に検査せよ:\n"
    "1. 観点間で主張が矛盾していないか\n"
    "2. 根拠のない飛躍（断言と論拠の不一致）がないか\n"
    "3. 具体的・整合的・実行可能な状態か\n"
    "矛盾を検出したら、修正した最終版だけを出力せよ（検査の経緯・説明は含めない）。\n"
    "矛盾が無ければ、元の成果物をそのまま出力せよ。"
)

# ---- 感情の道具化ガード（soft guard） ----
# 知恵の評議会の指摘「末期がんの物語が評定点向上のてこに道具化される危険」への対応。
# DIVERGE は「外れる許可」を与えるため、型通りの感情定式（泣かせ定式）に転落しうる。
# ここでは再生成せず、検出を警告として知らせる（本物の感情的真実まで弾かないため）。
_TERMINAL_PATTERNS = ("末期がん", "末期癌", "余命", "ステージ4", "ステージⅣ", "終末期")
_ELDER_PATTERNS = ("73歳", "高齢", "老人", "介護")
_ABANDON_PATTERNS = ("見捨てられ", "見放され", "置き去り", "孤独死", "見捨てた")
_CLICHE_EMOTION_PATTERNS = (
    "涙が止まらない", "胸が熱くなる", "感動を届ける", "心を打つ", "泣ける", "感情を揺さぶる",
)


def _sentimentality_detail(text: str) -> dict[str, bool]:
    """型通りの感情定式（泣かせ定式）の各要素を検出する（soft guard の詳細）。"""
    terminal = any(p in text for p in _TERMINAL_PATTERNS)
    elderly = any(p in text for p in _ELDER_PATTERNS)
    abandonment = any(p in text for p in _ABANDON_PATTERNS)
    cliche = any(p in text for p in _CLICHE_EMOTION_PATTERNS)
    return {
        "terminal_illness": terminal,
        "elderly": elderly,
        "abandonment": abandonment,
        "cliche_emotion": cliche,
        # 三項共起（末期 × 高齢 × 見捨て）は「感情の鍵」の典型。型通りの感傷定式も対象。
        "trope": terminal and elderly and abandonment,
    }


def _detect_sentimentality(text: str) -> bool:
    """型通りの感情定式かどうか（soft guard）。検出しても再生成はしない。"""
    d = _sentimentality_detail(text)
    return d["trope"] or d["cliche_emotion"]


# ---- 草案生成の温度（可能な限りの逸脱・発散の確保）。最終化・評価は 0.0（一貫性のため） ----
DRAFT_TEMPERATURE = 0.9

# 草案の上限（文字数）。草案はテーゼ集中形式（500〜800字指示）で短くなければならず、
# 超過は不完全扱いにする（分析レポート化による昇華の過剰包摂・速度悪化を防ぐ回収ライン）。
DRAFT_MAX_LENGTH = 1000

# 創作系タスク（歌詞・小説・物語・コピー等）向けの草案上限（2026-08-09、ユーザー指示）。
# テーゼ集中の1000字は散文の分析レポート防止用だが、歌詞や小説では完成作品が1000字を
# 自然に超える（実測: 歌詞1116字が上限超過で3回失敗し行列を落とした）。創作系は上限を
# 緩めるが、旧12〜19KBの報告書化を防ぐため無制限にはしない（緩めすぎると回帰する）。
DRAFT_MAX_LENGTH_CREATIVE = 3000

# 創作系タスクの判定キーワード。作品の完成形が長くなりうるジャンルを列挙する。
# 誤判定のコストは「ガードが緩くなるだけ」（500〜800字指示自体はエージェント側にある）ため、
# 広めに取る。裸の「コピー」は除外（「資料のコピー」等の誤爆を避ける。キャッチコピーで十分）。
_CREATIVE_TASK_KEYWORDS = (
    "歌詞", "歌", "曲", "小説", "物語", "詩", "ポエム", "脚本", "演劇", "絵本",
    "キャッチコピー", "ストーリー", "プロット", "短編",
)


def _is_creative_task(task: str) -> bool:
    """創作系タスクか（歌詞・小説・物語・コピー等、作品が長くなりうるジャンル）を判定する。

    真なら草案上限を DRAFT_MAX_LENGTH_CREATIVE に緩める（散文のテーゼ集中上限とは別枠）。
    """
    return any(k in task for k in _CREATIVE_TASK_KEYWORDS)

# 最終成果物（elevated）のサイズ制約。草案のテーゼ集中化と同じく、結論もコンパクトで
# なければならない（実測: 草案が500〜800字に収まっても elevated が7000字級のまま残る）。
# 上限は報告書化の防止（過剰包摂・検証不能な膨張）。下限は結論としての分量保証——
# 「結論なので小さすぎもNG」（ユーザー指示 2026-08-09）。上限・下限とも不完全扱いで再生成する。
ELEVATED_MAX_LENGTH = 1500
ELEVATED_MIN_LENGTH = 300

# ---- 打ち切りガード（崩れたら再生成） ----
_SYNTHESIS_TERMINAL_MARKERS = ("。", "！", "？", "…", "」", "）", "}", ")", '"', ".", "!", "?")

# 昇華生成の再生成上限（打ち切りが直らない場合の明示的失敗の境界）
AUFHEBEN_MAX_ATTEMPTS = 3

# 止揚（アウフヘーベン）の完全性下限。
# 止揚は読者向けの散文ではなく「思考の土台」で、終端記号（。！」）等）で終わるとは限らない
# （矢印「→」・箇条書き・前置きで終わりうる）。文途中の打ち切りは最終化が部分吸収できるため、
# ここでは「止揚が実質的に存在するか（極端に短い=止揚を放棄した出力の防止）」だけを判定する。
# 草案のテーゼ集中化（500〜800字）に合わせ、放棄と見なす下限を 30→60 に上げる。
AUFHEBEN_MIN_LENGTH = 60


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
    """最終分析・単発昇華が文として終端しているか。空応答と打ち切り（終端記号なし）を区別する。"""
    return bool(text) and text.rstrip().endswith(_SYNTHESIS_TERMINAL_MARKERS)


def _aufheben_is_complete(text: str) -> bool:
    """止揚（アウフヘーベン）の完全性判定。空・放棄（極端に短い）を再生成対象にする。"""
    return bool(text) and len(text.strip()) >= AUFHEBEN_MIN_LENGTH


def _draft_is_complete(text: str, max_length: int = DRAFT_MAX_LENGTH) -> bool:
    """草案の完全性判定。文途中で切れた打ち切りと、出力量過多を再生成対象にする。

    草案は昇華段階（Aufheben）に渡す先鋭化したテーゼ（テーゼ集中形式・500〜800字）で、
    途中で切れると内容が欠落するため終端記号で判定する（2026-08-08 実測: ゲートウェイが
    "…横のつながりが強い。「この健保" で打ち切った草案を素通ししていた）。末尾のマーク
    ダウン装飾（** の閉じ等）は除いて判定する（claude -p 経由の草案が "…。**" で終わる
    ことがある）。max_length 超過は「分析レポート化」として不完全扱い——草案は
    完全分析ではなくテーゼである（過剰包摂・速度悪化の回収ライン）。

    max_length は創作系タスク（歌詞・小説・コピー等）では DRAFT_MAX_LENGTH_CREATIVE に
    緩められる。テーゼ集中の1000字は散文の分析レポート防止用で、作品の完成形が
    1000字を自然に超えるジャンルには効かせない（実測 2026-08-09: 歌詞1116字が上限超過）。
    """
    if not text:
        return False
    if len(text) > max_length:
        return False  # 出力量過多（草案はテーゼ集中形式で短くなければならない）
    stripped = text.rstrip("*`~\t\n ")
    return stripped.endswith(_SYNTHESIS_TERMINAL_MARKERS)


def _elevated_is_complete(text: str, fmt: OutputFormat | None = None) -> bool:
    """最終成果物（elevated）の完全性判定。文終端＋上限（コンパクト制約）＋下限（結論としての分量）。

    草案のテーゼ集中化（DRAFT_MAX_LENGTH）と同じく、最終成果物も報告書化してはならない
    （実測: 草案が500〜800字に収まっても、elevated は7000字級のまま残った——昇華が
    過剰包摂して検証不能な数字を捏造し utility を落とす）。上限超過は「報告書化」として
    不完全扱い。ただし最終成果物は結論であるため、小さすぎも不合格（結論としての分量不足）。

    fmt（OutputFormat）が渡されたら、そのフォーマット固有の {min,max}_output_length を
    上限・下限に使う（タグラインなら数文字で合格、小説なら長くて合格、というように
    タスクごとに適切な範囲で判定する）。fmt が無ければ既存の固定値
    （ELEVATED_MIN/MAX_LENGTH）で判定する（後方互換）。
    どちらの違反も _generate_with_completeness_guard により再生成対象になる。

    文末記号チェックは直接成果物（fmt.output_is_direct=True: タグライン・詩・歌詞等）では
    緩める——コピーや詩は文末記号で終わらないのが普通で（"Time to Move"）、これを要求すると
    完成形を不完全扱いにして再生成ループに落とす。長さ範囲内で非空なら形式上の完成とみなす。
    分析系（output_is_direct=False）は従来どおり文終端を要求する。
    """
    if not text:
        return False
    min_len = fmt.min_output_length if fmt is not None else ELEVATED_MIN_LENGTH
    max_len = fmt.max_output_length if fmt is not None else ELEVATED_MAX_LENGTH
    if len(text) > max_len:
        return False  # 出力量過多（結論はコンパクトでなければならない）
    if len(text) < min_len:
        return False  # 分量不足（結論としての最低限を欠く）
    if fmt is not None and fmt.output_is_direct:
        return True  # 直接成果物は長さ範囲内なら完成（タグライン等は文末記号を要しない）
    stripped = text.rstrip("*`~\t\n ")
    return stripped.endswith(_SYNTHESIS_TERMINAL_MARKERS)


def _baseline_is_complete(text: str, fmt: OutputFormat | None = None) -> bool:
    """素の生成（指示のみ）の完全性判定。打ち切り（未完了）だけを再生成対象にする。

    _elevated_is_complete と違い**下限を強制しない**。素の生成は「指示のみ」のナイーブな
    答えであり、フォーマットの分量下限（例: 700字）を満たさないのはナイーブさの反映であって
    不完全ではない。下限を強制すると短い素直な答えが再生成され続け、compare のベースラインが
    成立しない（実測 2026-08-09: 素の生成3回が「分量不足」で連続失敗）。上限超過（report化）と
    文終端なし（打ち切り）だけを不完全とみなす。
    """
    if not text:
        return False
    max_len = fmt.max_output_length if fmt is not None else ELEVATED_MAX_LENGTH
    if len(text) > max_len:
        return False  # 出力量過多（report化）
    if fmt is not None and fmt.output_is_direct:
        return True  # 直接成果物は文終端を要しない
    stripped = text.rstrip("*`~\t\n ")
    return stripped.endswith(_SYNTHESIS_TERMINAL_MARKERS)


def _is_facade_contamination(text: str) -> bool:
    """素の生成がグローバル skill（elevate-draft-engine ファサード）に乗っ取られたかを判定する。

    2026-08-09 実測: press-release の素の生成が「了解しました。**Elevate-Draft-Engine** を起動します。」
    というファサード skill の起動文言を出力し、プレスリリース本体を書かなかった。素の生成は cwd を
    中性ディレクトリにしているが、グローバル skill（~/.claude/skills/）は cwd に関わらず読み込まれる
    ため防げない。出力が skill 起動文言の決定的シグネチャを含んでいたら汚染とみなし、完全性ガードが
    再生成する。
    """
    if not text:
        return False
    if "エンジンの場所を特定します" in text:
        return True
    return "Elevate-Draft-Engine" in text and "起動します" in text


# ---- 出力フォーマット（LLM による動的抽出） ----
#
# パイプラインは従来、出力形式を「分析レポート（テーゼ草案 → TVRO 最終化）」に固定していた。
# しかしキャッチコピー・歌詞・物語・設計書など、分野ごとに期待される形式は異なる
# （実測 2026-08-09: 「キャッチコピーを開発せよ」というタスクが Target/Value/Risk/Opportunity
# の分析レポートになった）。そこでタスクから LLM が期待される出力形式を動的に抽出し、
# diverge → aufheben → finalize の全段階に注入する。分野の数だけフォーマットを事前定義
# する必要はない——LLM がその場で形式を決める。

@dataclass(frozen=True)
class OutputFormat:
    """LLM によってタスクから動的に抽出された出力形式仕様。

    - deliverable_type:  成果物の種別名（例: キャッチコピー / 事業計画書 / 歌詞）
    - draft_guidance:    エージェント草案の形式指示（空なら既存のテーゼ形式に従う）
    - finalize_guidance: 最終化の形式指示（空でなければ TVRO の代わりに使う）
    - output_is_direct:  True=成果物そのもの（コピー・詩・歌詞）/ False=成果物についての分析
    """

    deliverable_type: str
    description: str
    draft_guidance: str
    finalize_guidance: str
    min_output_length: int
    max_output_length: int
    output_is_direct: bool


# 抽出失敗時のフォールバック（既存挙動 = 分析レポート）。各フィールドが既存の定数と一致するため、
# fmt=FORMAT_ANALYTICAL は従来のパイプラインと完全に同一の振る舞いになる。
FORMAT_ANALYTICAL = OutputFormat(
    deliverable_type="分析レポート",
    description="複数の視点を昇華した、超越的で具体的な分析。",
    draft_guidance="",  # 空 → 既存のテーゼ形式（核心的主張/根拠/前提）に従う
    finalize_guidance=FINALIZE_INSTRUCTION,  # TVRO
    min_output_length=ELEVATED_MIN_LENGTH,
    max_output_length=ELEVATED_MAX_LENGTH,
    output_is_direct=False,
)


EXTRACT_FORMAT_SYSTEM = (
    "あなたは形式分析者です。与えられたタスクから「期待される出力形式」を判定してください。"
    "タスクを解いてはいけません——出力がどのような形を取るべきかを記述するだけです。"
)

EXTRACT_FORMAT_PROMPT = (
    "タスク:\n{task}\n\n"
    "このタスクの期待される出力形式を分析し、JSON オブジェクトで返してください:\n"
    "{{\n"
    '  "deliverable_type": "<短い形式名。例: キャッチコピー / 事業計画書 / 歌詞 / 分析レポート / 小説>",\n'
    '  "description": "<このタスクで良い成果物とは何か。1文>",\n'
    '  "draft_guidance": "<個々の草案執筆者への形式指示。分析系ならテーゼ形式（核心的主張/根拠/前提）、'
    '創作系なら作品の断片や骨子、短形式なら候補+意図説明。このタスク固有に具体化せよ。>",\n'
    '  "finalize_guidance": "<最終化工程への形式指示。汎用の Target/Value/Risk/Opportunity を'
    'このタスクに適した構造で置き換えよ。最終成果物の形式・見出し・含むべき要素を具体的に指定せよ。>",\n'
    '  "min_output_length": <最終成果物の下限文字数。整数>,\n'
    '  "max_output_length": <最終成果物の上限文字数。整数。'
    'finalize_guidance が要求する構造（節・候補数・根拠等）を収められる十分な大きさにせよ。'
    '厳しすぎる上限は完全な成果物を弾いてしまう>,\n'
    '  "output_is_direct": <true か false。true=成果物そのもの（コピー・詩・歌詞・小説）／'
    'false=成果物についての分析（事業計画・仮説・レポート）>\n'
    "}}\n"
    "有効な JSON のみを返してください。マークダウンのコードフェンスや余計な文章は不要です。"
)


_format_cache: dict[str, OutputFormat] = {}


def extract_format(generator: Generator, task: str) -> OutputFormat:
    """タスクから期待される出力形式を LLM で動的に抽出する。

    1 回の軽量 LLM 呼び出しで JSON を返させ、OutputFormat に変換する。
    呼び出し失敗・JSON パース失敗・不正な値は FORMAT_ANALYTICAL（既存挙動）に
    フォールバックする——劣化ではなく安全側への退避。
    同一タスクはハッシュでメモ化し、再抽出を避ける。
    """
    import hashlib
    import json

    key = hashlib.sha256(task.encode("utf-8")).hexdigest()
    if key in _format_cache:
        return _format_cache[key]

    fmt = FORMAT_ANALYTICAL
    try:
        raw = generator.generate(
            EXTRACT_FORMAT_SYSTEM, EXTRACT_FORMAT_PROMPT.format(task=task), temperature=0.0
        )
        data = json.loads(raw)
        lo = int(data.get("min_output_length", ELEVATED_MIN_LENGTH))
        hi = int(data.get("max_output_length", ELEVATED_MAX_LENGTH))
        if lo < 1 or hi < lo or hi > 100_000:
            raise ValueError("不正な長さ範囲")
        fmt = OutputFormat(
            deliverable_type=str(data.get("deliverable_type") or "成果物"),
            description=str(data.get("description") or ""),
            draft_guidance=str(data.get("draft_guidance") or ""),
            finalize_guidance=str(data.get("finalize_guidance") or FINALIZE_INSTRUCTION),
            min_output_length=lo,
            max_output_length=hi,
            output_is_direct=_json_bool(data.get("output_is_direct"), False),
        )
    except Exception:
        fmt = FORMAT_ANALYTICAL
    _format_cache[key] = fmt
    return fmt


def _json_bool(value, default: bool = False) -> bool:
    """JSON の真偽値（bool / "true" / "false" 文字列）を bool に正規化する。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1")
    return default


def _generate_with_completeness_guard(
    generator: Generator,
    system: str,
    user: str,
    *,
    temperature: float | None = None,
    label: str = "昇華生成",
    is_complete=None,
    sink: Path | None = None,
    fallback_is_complete=None,
) -> str:
    """指定 system で生成し、完全性ガード（broken output → regenerate）を適用する。

    構造が既知の呼び出し側で決定的に検証し、崩れた出力は再生成する。
    上限回数で直らない場合は明示的失敗（不完全出力を評価に渡さない）。
    temperature を渡すことで、昇華は温度0.9、最終化は0.0を実現する。
    is_complete を渡すと判定を差し替えられる（最終化=文終端 / 止揚=長さ下限）。

    fallback_is_complete を渡すと、フォーマット（OutputFormat）認識の完全性判定が
    上限回数で満たせなかったとき、その緩和判定（通常は文終端のみ）を満たしていれば
    最後の試行を受け入れて続行する。これは「LLMが抽出したフォーマット仕様が
    自己矛盾（finalize_guidance が要求する構造 > max_output_length 等）で実質達成不能」な
    場合の安全弁で、健全な成果物が残っていても仕様不整合だけでパイプライン全体が
    落ちないようにする。form なし（既存の固定値判定）の経路は従来どおり明示的失敗する。

    sink が与えられたら、生成前に空ファイルを作り、on_chunk 経由で届く文字列を
    逐次追記する（草案のストリーム保存）。打ち切りで再生成するときはファイルを
    空に戻してから再開するため、失敗試行の部分文がファイルに残らない。
    """
    if is_complete is None:
        is_complete = _synthesis_is_complete
    last_err = ""
    last_artifact = ""
    for _ in range(AUFHEBEN_MAX_ATTEMPTS):
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
        last_artifact = artifact
        if is_complete(artifact):
            return artifact
        last_err = f"{label}が打ち切られた/不完全（…{artifact[-20:]!r}）"
    if fallback_is_complete is not None and last_artifact and fallback_is_complete(last_artifact):
        # フォーマット仕様が達成不能（自己矛盾）で長さだけ満たせない場合の安全弁。
        # 崩れた出力（空・文途中打ち切り）は fallback でも弾かれる。
        print(
            f"⚠ {label}: フォーマット仕様を {AUFHEBEN_MAX_ATTEMPTS} 回満たせず、"
            "構造的に完成した最後の試行を受け入れて続行します"
            f"（{last_err}）。",
            file=sys.stderr,
        )
        return last_artifact
    raise RuntimeError(f"{label}が{AUFHEBEN_MAX_ATTEMPTS}回連続で打ち切り/不完全: {last_err}")


def _generate_synthesis(generator: Generator, synthesis_user: str, *, sink: Path | None = None,
                        fmt: OutputFormat | None = None) -> str:
    """単発昇華（method="single-pass"）を生成する。打ち切りは再生成し、直らない場合は明示的に失敗させる。

    sink が与えられたら、生成前に空ファイルを作り、生成中に逐次追記する（草案と同じ）。
    fmt が渡されたら、そのフォーマット固有の長さ範囲で完全性を判定する（タスクに応じたサイズ）。
    """
    return _generate_with_completeness_guard(
        generator, ANALYSIS_SYSTEM + SYNTHESIS_SYSTEM, synthesis_user, label="昇華生成",
        is_complete=lambda text: _elevated_is_complete(text, fmt), sink=sink,
        fallback_is_complete=_synthesis_is_complete if fmt is not None else None,
    )


def _generate_aufheben(generator: Generator, aufheben_user: str, *, temperature: float, sink: Path | None = None) -> str:
    """止揚（アウフヘーベン）を生成する。極端に短い（放棄した）出力は再生成。

    止揚は「思考の土台」で文終端記号で終わるとは限らないため、終端記号チェックは誤判定を
    招く（実測: 6104字の完全な推理が再生成ループに落ちた）。長さ下限で「止揚が実質的に
    存在するか」だけを判定する。空応答はクライアントが再試行済み。温度は 0.9
    （発散と同率。弁証法的跳躍に創造性を要するため）。
    sink が与えられたら、生成前に空ファイルを作り、生成中に逐次追記する。
    """
    return _generate_with_completeness_guard(
        generator, AUFHEBEN_SYSTEM, aufheben_user,
        temperature=temperature, label="昇華",
        is_complete=_aufheben_is_complete, sink=sink,
    )


def _generate_finalize(generator: Generator, finalize_user: str, *, sink: Path | None = None,
                       fmt: OutputFormat | None = None) -> str:
    """最終分析を生成する。打ち切りは再生成。温度は 0.0（一貫性。止揚の基盤から超越的統合を明瞭に仕上げる）。
    sink が与えられたら、生成前に空ファイルを作り、生成中に逐次追記する。
    fmt が渡されたら、そのフォーマット固有の長さ範囲で完全性を判定する（タスクに応じたサイズ）。
    """
    return _generate_with_completeness_guard(
        generator, ANALYSIS_SYSTEM + FINALIZE_SYSTEM, finalize_user, label="最終分析",
        is_complete=lambda text: _elevated_is_complete(text, fmt), sink=sink,
        # フォーマット仕様が自己矛盾（抽出した finalize_guidance が求める構造 >
        # 抽出した max_output_length）で達成不能な場合、構造的に完成した最後の試行を
        # 受け入れて続行する（健全な成果物を仕様不整合だけで捨てない）。
        fallback_is_complete=_synthesis_is_complete if fmt is not None else None,
    )


def _generate_logic_check(generator: Generator, artifact: str, task: str, *, sink: Path | None = None,
                          fmt: OutputFormat | None = None) -> str:
    """論理一貫性の復元工程。最終成果物を検査し、矛盾があれば修正版を返す。

    観察された creativity +0.10 / logic -0.05 の非対称（昇華が「多様化」に偏る）への
    対応として、最終化の後に論理的一貫性を復元する収束工程を構造として追加する。
    論理を超えた飛躍（アウフヘーベンによる枠組みの創出）自体は矛盾と見なさない。
    温度は 0.0（一貫性）。完全性ガード（文終端）を適用。矛盾が無ければ元の成果物を
    そのまま返すため、品質を下げない。fmt が渡されたらフォーマット固有の長さ範囲で判定する。
    """
    parts = [f"【タスク】\n{task}"] if task else []
    parts += [
        f"【成果物】\n{artifact}",
        f"【論理検査指示】\n{LOGIC_CHECK_INSTRUCTION}",
    ]
    user = "\n\n".join(parts)
    return _generate_with_completeness_guard(
        generator, ANALYSIS_SYSTEM + LOGIC_CHECK_SYSTEM, user, label="論理検査",
        is_complete=lambda text: _elevated_is_complete(text, fmt), sink=sink,
        fallback_is_complete=_synthesis_is_complete if fmt is not None else None,
    )


def _generate_draft(
    generator: Generator, system: str, user: str, *, temperature: float,
    sink: Path | None = None, max_length: int = DRAFT_MAX_LENGTH,
) -> str:
    """エージェント草案を生成する。文途中の打ち切りは再生成。温度は draft_temperature。

    昇華・最終化と同じ完全性ガード（broken output → regenerate）を草案にも適用する。
    sink が与えられたら、生成前に空ファイルを作り、生成中に逐次追記する。
    max_length で草案上限を差し替えられる（創作系タスクは DRAFT_MAX_LENGTH_CREATIVE）。
    """
    return _generate_with_completeness_guard(
        generator, system, user, temperature=temperature, label="草案生成",
        is_complete=lambda text: _draft_is_complete(text, max_length), sink=sink,
    )


# ---- プロンプト構築（ステートレス生成器への明示補償） ----

def _knowledge_block(knowledge: str | None) -> list[str]:
    """前提知識をプロンプトのセクションに整形する（なければ空リスト）。

    前提知識はタスクの直後に置く（fmt の形式指示より前）。これは「形」ではなく
    「内容」の制約——素材・制約・背景情報——であり、生成の全段階の土台にする。
    """
    if not knowledge:
        return []
    return [f"【前提知識】\n{knowledge}"]


def _drafts_block(drafts: list[Draft]) -> list[str]:
    """各草案を「エージェント名付き」のブロックに整形する。"""
    return [f"【草案（観点: {d.agent}）】\n{d.content}" for d in drafts]


def _build_aufheben_prompt(task: str, drafts: list[Draft], fmt: OutputFormat | None = None,
                           knowledge: str | None = None) -> str:
    """止揚（アウフヘーベン）の user プロンプトを組み立てる。

    fmt が渡されたら、最終成果物の形式（deliverable_type）を意識するよう指示を追記する。
    弁証法（否定/保存/高次化/超越的視点）自体は不変。
    knowledge が渡されたら、前提知識をタスク直後に注入する（止揚が知識の範囲内で行われる）。
    """
    parts = [f"【タスク】\n{task}"] if task else []
    parts += _knowledge_block(knowledge)
    parts += _drafts_block(drafts)
    instruction = AUFHEBEN_INSTRUCTION
    if fmt is not None and fmt.draft_guidance:
        instruction += (
            f"\n\nこの止揚は最終的に「{fmt.deliverable_type}」を生成するための思考の土台である。"
            f"最終出力が{fmt.deliverable_type}の形式になることを意識しつつ、弁証法的止揚を行え。"
        )
    parts.append(f"【昇華指示】\n{instruction}")
    return "\n\n".join(parts)


def _build_synthesis_prompt(task: str, drafts: list[Draft], fmt: OutputFormat | None = None,
                            knowledge: str | None = None) -> str:
    """単発昇華（method="single-pass"）の user プロンプトを組み立てる。

    fmt が渡されたら、最終成果物の形式指示（finalize_guidance）を追記して、
    単発昇華もタスク固有の形式で仕上げさせる（TVRO 前提にしない）。
    knowledge が渡されたら、前提知識をタスク直後に注入する。
    """
    parts = [f"【タスク】\n{task}"] if task else []
    parts += _knowledge_block(knowledge)
    parts += _drafts_block(drafts)
    instruction = SYNTHESIS_INSTRUCTION
    if fmt is not None and fmt.finalize_guidance:
        instruction += (
            f"\n\n最終成果物は「{fmt.deliverable_type}」の形式で仕上げよ。"
            f"\n【最終化指示】\n{fmt.finalize_guidance}"
        )
    parts.append(f"【昇華指示】\n{instruction}")
    return "\n\n".join(parts)


def _build_finalize_prompt(task: str, reconciliation: str, fmt: OutputFormat | None = None,
                           knowledge: str | None = None) -> str:
    """最終分析の user プロンプトを組み立てる。

    最終化は草案ではなく「止揚（アウフヘーベン）の基盤」だけを読む。止揚の中間過程が
    最終成果物に漏れないよう、高められた結論だけを書かせる。
    fmt が渡されたら、そのフォーマット固有の finalize_guidance で TVRO を置き換える
    （タスクに応じた形式で最終成果物を仕上げさせる）。
    knowledge が渡されたら、前提知識をタスク直後に注入する（成果物が知識と矛盾しない）。
    """
    parts = [f"【タスク】\n{task}"] if task else []
    parts += _knowledge_block(knowledge)
    finalize_instruction = fmt.finalize_guidance if (fmt is not None and fmt.finalize_guidance) else FINALIZE_INSTRUCTION
    parts += [
        f"【止揚の基盤】\n{reconciliation}",
        f"【最終化指示】\n{finalize_instruction}",
    ]
    return "\n\n".join(parts)


# ---- エンジン本体 ----

class DraftEngine:
    """複数のエージェント（観点）から草案を生成し、昇華（アウフヘーベン）して一段高い成果物を生むエンジン。

    - `generate(task)`  … 素のAI（単発生成）。1 call
    - `diverge(task)`   … 登録エージェントで独立草案を生成。8 calls（既定）
    - `synthesize(drafts)` … 外部草案も含む複数草案を昇華（核心）
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
        enable_logic_check: bool = False,
    ):
        self.client = client
        self.draft_temperature = draft_temperature
        self.enable_logic_check = enable_logic_check
        if agents is not None:
            self._agents: dict[str, str] = dict(agents)
        else:
            self._agents = load_agents(agents_dir)
        # 断言枠アブレーション: strong_claim_frame=False のとき旧「最強の主張」枠を除去する
        # （テーゼ集中形式の組み込みエージェントには旧枠が無いため実質 no-op。
        # 旧枠を持つカスタムエージェント混入時の安全網。既定 true = 何もしない）。
        if not strong_claim_frame:
            self._agents = {name: _strip_strong_claim(p) for name, p in self._agents.items()}

    # ---- 素の生成 ----

    def generate(self, task: str, *, sink: Path | None = None,
                 fmt: OutputFormat | None = None, knowledge: str | None = None) -> str:
        """素のAI（単発生成）: 指示のみで成果物を生成する。1 call。

        素の生成は**指示のみ**——システムプロンプトを渡さない。リポジトリの機構
        （昇華・エージェント・ルーブリック）の存在を知らせないことが前提。これにより
        compare のベースラインは「素の AI が指示だけを見て書いた答え」になる。
        claude-code エンジンではシステムプロンプトが空のとき `--system-prompt` を省略し、
        中性ディレクトリから起動して CLAUDE.md（リポジトリの自己記述）も読み込ませない。

        草案と同じ完全性ガード（broken output → regenerate）を適用する——
        打ち切られたベースラインを不公平に採点しない。sink が与えられたら、
        生成前に空ファイルを作り、生成中に逐次追記する（草案と同じ横展開）。

        fmt が渡されたら、そのフォーマット固有の最終化指示をタスクに追記する
        （compare の素の生成ベースラインにも同じフォーマットを与えて公平に比較する）。
        完全性判定はフォーマット固有の上限超過だけを再生成対象にする（下限は強制しない——
        素の生成のナイーブさがそのままベースラインになる）。
        knowledge が渡されたら、前提知識をタスク直後に追記する
        （compare の素の生成ベースラインにも同じ前提知識を与えて公平に比較する）。
        """
        task_for_model = task
        if knowledge:
            task_for_model = f"{task_for_model}\n\n【前提知識】\n{knowledge}"
        if fmt is not None and fmt.finalize_guidance:
            task_for_model = (
                f"{task_for_model}\n\n【このタスクの最終成果物形式】\n{fmt.finalize_guidance}"
            )
        def _raw_is_complete(text: str) -> bool:
            if _is_facade_contamination(text):
                print(
                    "⚠ 素の生成がグローバル skill（elevate-draft-engine ファサード）に汚染されました。"
                    "再生成します。",
                    file=sys.stderr,
                )
                return False
            return (
                _baseline_is_complete(text, fmt) if fmt is not None
                else _synthesis_is_complete  # fmt なし = 従来どおり文終端のみ（後方互換）
            )

        return _generate_with_completeness_guard(
            self.client, "", task_for_model, label="素の生成",
            is_complete=_raw_is_complete, sink=sink,
        )

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
        on_error: Callable[[str, Exception], None] | None = None,
        fmt: OutputFormat | None = None,
        knowledge: str | None = None,
    ) -> list[Draft]:
        """指定エージェント（既定は登録済み全エージェント）で独立草案を生成する。

        役割多様性（エージェントごとの system）＋温度多様性（draft_temperature）で独立した草案を保証。
        on_draft(draft) を渡すと、各草案の生成完了時点で逐次コールバックされる
        （進捗表示に使う。全生成完了を待たないため、途中で失敗しても
        生成済み分の草案を失わない）。

        draft_dir を渡すと、各草案は生成前に空の draft_{name}.md として作成され、
        生成中に逐次追記される（claude-code エンジンのストリーム対応クライアントで
        実際に逐次追記される。未対応クライアントでは生成完了時に一括書き込み）。

        on_error(name, exc) を渡すと、単一エージェントの草案が上限回数連続で打ち切り/不完全
        （RuntimeError）になったとき、そのエージェントだけスキップして残りで継続する。
        1エージェントの失敗で呼び出し全体を中断しない（実測 2026-08-09: 歌詞の草案が
        DRAFT_MAX_LENGTH 超過を繰り返し、行列 compare/improve 全体が落ちた）。
        失敗したエージェントの部分草案ファイルは残さない（成功草案と区別するため削除）。
        全エージェントが失敗した場合は空リストを返し、呼び出し側の synthesize が
        「草案がありません」で明確に失敗する。

        創作系タスク（歌詞・小説・コピー等）は草案上限を DRAFT_MAX_LENGTH_CREATIVE に
        緩める（2026-08-09、ユーザー指示）。テーゼ集中の1000字は散文の分析レポート防止用で、
        作品の完成形が長くなりうるジャンルでは、超過が失敗になるのは誤作動だった。
        判定は _is_creative_task のキーワード法。誤判定のコストはガードが緩くなるだけ。

        fmt（OutputFormat）が渡されたら、そのフォーマットに従う:
        - draft_guidance をタスクに追記して、草案の形式をタスク固有に指示する
          （空なら既存のテーゼ形式のまま——分析レポート・フォールバック時）
        - 草案上限は output_is_direct（成果物そのもの）なら DRAFT_MAX_LENGTH_CREATIVE、
          それ以外は DRAFT_MAX_LENGTH。fmt が無ければ従来どおり _is_creative_task で判定。

        knowledge（前提知識）が渡されたら、各エージェントの草案タスクにタスク直後
        （草案形式の指示より前）に注入する。素材・制約・背景情報を生成の土台にする。
        改修ラウンド（improve/compare の _revision_task）でも diverge が内部で知識を
        付与するため、ラウンドをまたいで永続する。
        """
        names = agents if agents is not None else list(self._agents)
        unknown = [a for a in names if a not in self._agents]
        if unknown:
            raise ValueError(f"未登録のエージェント: {unknown}（登録済み: {list(self._agents)}）")
        if fmt is not None:
            max_length = DRAFT_MAX_LENGTH_CREATIVE if fmt.output_is_direct else DRAFT_MAX_LENGTH
        else:
            max_length = DRAFT_MAX_LENGTH_CREATIVE if _is_creative_task(task) else DRAFT_MAX_LENGTH
        draft_task = task
        if knowledge:
            draft_task = f"{draft_task}\n\n【前提知識】\n{knowledge}"
        if fmt is not None and fmt.draft_guidance:
            draft_task = f"{draft_task}\n\n【このタスクの草案形式】\n{fmt.draft_guidance}"
        drafts: list[Draft] = []
        for name in names:
            sink = None
            if draft_dir is not None:
                sink = draft_dir / f"draft_{name}.md"
            try:
                content = _generate_draft(
                    self.client, self._agents[name], draft_task,
                    temperature=self.draft_temperature, sink=sink, max_length=max_length,
                )
            except RuntimeError as exc:
                # 単一エージェントの生成失敗: 部分草案を残さず報告して、次のエージェントへ
                if sink is not None and sink.exists():
                    sink.unlink()
                if on_error is not None:
                    on_error(name, exc)
                continue
            draft = Draft(agent=name, content=content)
            drafts.append(draft)
            if on_draft is not None:
                on_draft(draft)
        return drafts

    # ---- SYNTHESIZE（核心） ----

    def synthesize_with_reconciliation(
        self, drafts: list[Draft], method: str = "two-stage", task: str = "",
        *, enable_logic_check: bool | None = None,
        reconciliation_sink: Path | None = None, artifact_sink: Path | None = None,
        fmt: OutputFormat | None = None, knowledge: str | None = None,
    ) -> tuple[str, str]:
        """昇華し、止揚（昇華の下地）と成果物を返す。

        戻り値: (reconciliation, artifact)。method="single-pass" は止揚が無いため ("", artifact)。
        止揚を保存したい呼び出し側（CLI の --out 等）はこちらを使う。

        enable_logic_check=True で、最終化の後に論理一貫性の復元工程（_generate_logic_check）
        を適用する（既定: エンジンのコンストラクタ設定に従う。false なら従来動作のまま）。

        reconciliation_sink / artifact_sink が与えられたら、それぞれの生成前に空ファイルを
        作り、生成中に逐次追記する（草案のストリーム保存と同じ横展開）。論理検査が有効な
        ときは、成果物の sink は最終化ではなく論理検査の出力に追記される（最終成果物と一致）。

        fmt（OutputFormat）が渡されたら、止揚・最終化・完全性ガードをそのフォーマットに従わせる
        （フォーマット固有の finalize_guidance で TVRO を置換、タスク固有の長さ範囲で判定）。
        knowledge（前提知識）が渡されたら、止揚・最終化（および単発昇華）のプロンプトに
        タスク直後として注入する。
        """
        if not drafts:
            raise ValueError("昇華対象の草案がありません")
        if enable_logic_check is None:
            enable_logic_check = self.enable_logic_check
        if method == "two-stage":
            aufheben_user = _build_aufheben_prompt(task, drafts, fmt, knowledge)
            reconciliation = _generate_aufheben(
                self.client, aufheben_user, temperature=self.draft_temperature,
                sink=reconciliation_sink,
            )
            finalize_user = _build_finalize_prompt(task, reconciliation, fmt, knowledge)
            artifact = _generate_finalize(
                self.client, finalize_user, fmt=fmt,
                sink=None if enable_logic_check else artifact_sink,
            )
            if enable_logic_check:
                artifact = _generate_logic_check(self.client, artifact, task, sink=artifact_sink, fmt=fmt)
            return reconciliation, artifact
        if method == "single-pass":
            synthesis_user = _build_synthesis_prompt(task, drafts, fmt, knowledge)
            artifact = _generate_synthesis(
                self.client, synthesis_user, fmt=fmt,
                sink=None if enable_logic_check else artifact_sink,
            )
            if enable_logic_check:
                artifact = _generate_logic_check(self.client, artifact, task, sink=artifact_sink, fmt=fmt)
            return "", artifact
        raise ValueError(f"未知の method: {method!r}（'two-stage' または 'single-pass'）")

    def synthesize(
        self, drafts: list[Draft], method: str = "two-stage", task: str = "",
        *, enable_logic_check: bool | None = None,
        fmt: OutputFormat | None = None, knowledge: str | None = None,
    ) -> str:
        """複数の独立草案を昇華（アウフヘーベン）して一段高い成果物を返す。

        - method="two-stage": 弁証法的止揚 → 最終化（2段階昇華。温度: 止揚 0.9 / 最終化 0.0）
        - method="single-pass":  単発昇華（1コール）

        drafts は外部草案（人間の専門家が書いた分析、別モデルの出力等）でもよい。
        出所を問わず「複数の異なる視点」を突っ込めば一段高い昇華を返す。
        fmt が渡されたら、止揚・最終化・完全性ガードをそのフォーマットに従わせる。
        knowledge が渡されたら、止揚・最終化のプロンプトに前提知識を注入する。
        """
        _, artifact = self.synthesize_with_reconciliation(
            drafts, method=method, task=task, enable_logic_check=enable_logic_check,
            fmt=fmt, knowledge=knowledge,
        )
        return artifact

    # ---- 便利ラッパー ----

    def elevate(
        self, task: str, method: str = "two-stage", agents: list[str] | None = None,
        *, enable_logic_check: bool | None = None,
        on_error: Callable[[str, Exception], None] | None = None,
        fmt: OutputFormat | None = None, knowledge: str | None = None,
    ) -> str:
        """diverge → synthesize を一気に行う。

        fmt が渡されたら、発散の草案形式・止揚・最終化・完全性ガードをそのフォーマットに従わせる。
        knowledge が渡されたら、発散・止揚・最終化の全段階に前提知識を注入する。
        """
        drafts = self.diverge(task, agents=agents, on_error=on_error, fmt=fmt, knowledge=knowledge)
        return self.synthesize(
            drafts, method=method, task=task, enable_logic_check=enable_logic_check,
            fmt=fmt, knowledge=knowledge,
        )
