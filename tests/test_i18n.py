# -*- coding: utf-8 -*-
"""多言語化（en/ja/zh）のテスト（計画フェーズ8.1）。

検証対象:
- resolve_lang の優先順位（CLI > 環境変数 > 既定 en）
- load_locale / load_prompts の3言語ロードとキー整合
- load_agents(lang=...) が言語によらず同一のベース名（8名）を返す
- mock での elevate / compare / improve が en（既定）/ ja / zh で完走し、
  出力が言語別にローカライズされる
- 品質評価の英語キー抽出（D2）・感傷ガード・創作系判定の言語別
- プロンプトストアの「ja = 旧エンジン定数」の一致（翻訳時退行の防止）

conftest.py が ELEVATE_DRAFT_ENGINE_LANG=ja を固定しているため、
「既定が en」を検証するテストは環境変数を除去した上でキャッシュを破棄する。
"""

import io
import json
import os
import re
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main  # noqa: E402
from elevate import i18n  # noqa: E402
from elevate.engine import (  # noqa: E402
    ANALYSIS_SYSTEM,
    AUFHEBEN_SYSTEM,
    _detect_sentimentality,
    _is_creative_task,
    load_agents,
)
from evaluation.quality import _QUALITY_RUBRIC, _extract_json, format_quality_line  # noqa: E402

LANGUAGES = ("en", "ja", "zh")
AGENT_BASES = [
    "designer", "differentiator", "futurist", "humanist",
    "implementer", "storyteller", "strategist", "visionary",
]


@pytest.fixture
def _no_env_lang(monkeypatch):
    """既定言語テスト用に環境変数を除去する（conftest の ja 固定を解除）。"""
    monkeypatch.delenv("ELEVATE_DRAFT_ENGINE_LANG", raising=False)
    i18n.clear_cache()
    yield
    i18n.clear_cache()


# ---- resolve_lang: CLI > 環境変数 > 既定 en ----

def test_resolve_lang_default_is_en(_no_env_lang) -> None:
    """CLI・環境変数とも未指定なら既定は en（D1確定）。"""
    assert i18n.resolve_lang(None) == "en"


def test_resolve_lang_env_var(monkeypatch) -> None:
    """環境変数 ELEVATE_DRAFT_ENGINE_LANG が優先される。"""
    monkeypatch.setenv("ELEVATE_DRAFT_ENGINE_LANG", "zh")
    assert i18n.resolve_lang(None) == "zh"


def test_resolve_lang_cli_over_env(monkeypatch) -> None:
    """CLI フラグが環境変数より優先される。"""
    monkeypatch.setenv("ELEVATE_DRAFT_ENGINE_LANG", "zh")
    assert i18n.resolve_lang("ja") == "ja"


def test_resolve_lang_unsupported_falls_back_to_en(_no_env_lang) -> None:
    """未対応言語は警告して既定 en にフォールバックする。"""
    err = io.StringIO()
    with redirect_stderr(err):
        lang = i18n.resolve_lang("fr")
    assert lang == "en"
    assert "unsupported" in err.getvalue().lower() or "警告" in err.getvalue()


# ---- ロケール・プロンプトストアのロードとキー整合 ----

def test_load_locale_and_prompts_all_languages() -> None:
    """3言語すべてで locales / prompts がロードでき、主要セクションを持つ。"""
    for lang in LANGUAGES:
        loc = i18n.load_locale(lang)
        pr = i18n.load_prompts(lang)
        assert loc, f"locales/{lang}.json が空"
        assert "console" in loc and "templates" in loc
        for section in ("BLOCKS", "engine", "quality", "mock"):
            assert section in pr, f"prompts/{lang}.json に {section} が無い"


def test_markers_have_language_specific_draft_header() -> None:
    """言語別の「草案の作り方」見出しが互いに異なり、エージェント翻訳と整合する。"""
    headers = {
        lang: i18n.load_prompts(lang)["engine"]["MARKERS"]["draft_instruction_header"]
        for lang in LANGUAGES
    }
    assert headers["en"] == "How to write a draft"
    assert headers["ja"] == "草案の作り方"
    assert headers["zh"] == "草案的写法"
    assert len(set(headers.values())) == 3


def _strip_json_example(rubric: str) -> str:
    """品質ルーブリックの最終行 JSON 出力例（{"…"}）を除いた散文部分を返す。"""
    return rubric.rsplit('\n{', 1)[0]


def test_ja_store_matches_engine_constants() -> None:
    """ja のプロンプトストアは旧エンジン定数と一致する（翻訳時の退行防止）。

    conftest の ja 固定は既存 184 件を守る前提。ja ストアが定数からずれると
    既存挙動が変わるため、ここで常に一致を保証する。
    品質ルーブリックのみ D2（品質キー英語化）で最終行 JSON のキーを意図的に
    英語へ変更している。散文部分は旧定数と一致すること（退行の防止）。
    """
    ja = i18n.load_prompts("ja")
    assert ja["engine"]["ANALYSIS_SYSTEM"] == ANALYSIS_SYSTEM
    assert ja["engine"]["AUFHEBEN_SYSTEM"] == AUFHEBEN_SYSTEM
    assert _strip_json_example(ja["quality"]["RUBRIC"]) == _strip_json_example(_QUALITY_RUBRIC)
    assert '"novelty"' in ja["quality"]["RUBRIC"]  # D2: 品質キーは英語


# ---- load_agents: 言語非依存のベース名 ----

def test_load_agents_returns_same_base_names_per_language() -> None:
    """en/ja/zh すべてで同一の8ベース名が返る（--agents の言語非依存化）。"""
    for lang in LANGUAGES:
        agents = load_agents(lang=lang)
        assert sorted(agents) == sorted(AGENT_BASES), f"{lang}: {sorted(agents)}"
        # 各エージェントファイルに「You are the **Name**」テンプレートが維持されている
        # （MockGenerator のペルソナ抽出がこれに依存する）。
        for body in agents.values():
            assert "You are the **" in body, "英語テンプレートが全言語で維持されること"


# ---- mock での一気通貫（elevate / compare / improve × en(既定)/ja/zh） ----

def _run_main(argv: list[str], *, cwd: Path) -> tuple[int, str]:
    """main.main() を実行し (exit_code, stdout+stderr) を返す。"""
    old = os.getcwd()
    os.chdir(cwd)
    try:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            code = main.main(argv)
        return code, out.getvalue()
    finally:
        os.chdir(old)


@pytest.mark.parametrize("lang,task", [
    ("en", "Design a morning routine that makes the day productive"),
    ("ja", "朝のルーティーンを設計して、一日を充実した地に足の着いたものにしよう"),
    ("zh", "设计一个让一天高效而踏实的晨间习惯"),
])
def test_mock_elevate_completes_in_each_language(tmp_path, lang, task) -> None:
    """elevate --mock が各言語で完走し、ローカライズされた成果物が保存される。"""
    code, _ = _run_main(
        ["elevate", task, "--mock", "--lang", lang, "--out", str(tmp_path)],
        cwd=tmp_path.parent,
    )
    assert code == 0
    elevated = (tmp_path / "artifacts" / "elevated.md").read_text(encoding="utf-8")
    assert elevated.strip(), "昇華成果物が空でない"
    # 出力が言語別テンプレート（generic_text）であること
    gen = main.MockGenerator(lang=lang)
    expected = gen.mock["generic_text"].strip()
    assert expected in elevated, f"{lang}: 成果物が {lang} テンプレートを含まない"


@pytest.mark.parametrize("lang,task,header", [
    ("en", "Design a morning routine that makes the day productive", "# Prior Knowledge"),
    ("ja", "朝のルーティーンを設計して、一日を充実した地に足の着いたものにしよう", "# 前提知識"),
    ("zh", "设计一个让一天高效而踏实的晨间习惯", "# 背景知识"),
])
def test_mock_elevate_with_knowledge_saves_localized_file(tmp_path, lang, task, header) -> None:
    """elevate --mock --knowledge が各言語で完走し、ローカライズされた knowledge.md を保存する。

    前提知識の注入は全言語共通の機能であり、i18n でも知識の保存・見出しのローカライズを
    保証する（見出しがコード内の ja 定数にフォールバックすると en/zh で日本語が漏れる）。
    """
    code, _ = _run_main(
        ["elevate", task, "--mock", "--lang", lang, "--out", str(tmp_path),
         "--knowledge", "材料: 再生PET。ターゲット: 20〜30代。"],
        cwd=tmp_path.parent,
    )
    assert code == 0
    knowledge = (tmp_path / "knowledge.md").read_text(encoding="utf-8")
    assert header in knowledge, f"{lang}: knowledge.md の見出しがローカライズされていない"
    assert "材料" in knowledge, f"{lang}: 前提知識の本文が保存されていない"


@pytest.mark.parametrize("lang", LANGUAGES)
def test_mock_compare_completes_in_each_language(tmp_path, lang) -> None:
    """compare --mock --runs 1 が各言語で完走する。"""
    code, _ = _run_main(
        ["compare", "task", "--mock", "--runs", "1", "--lang", lang, "--out", str(tmp_path)],
        cwd=tmp_path.parent,
    )
    assert code == 0
    files = [p.name for p in tmp_path.rglob("*")]
    assert any("elevated" in n for n in files), f"{lang}: 比較成果物が保存されていない"


@pytest.mark.parametrize("lang", LANGUAGES)
def test_mock_improve_completes_in_each_language(tmp_path, lang) -> None:
    """improve --mock --rounds 2 --evaluate が各言語で完走する。"""
    code, _ = _run_main(
        ["improve", "task", "--mock", "--rounds", "2", "--evaluate",
         "--lang", lang, "--out", str(tmp_path)],
        cwd=tmp_path.parent,
    )
    assert code == 0
    assert (tmp_path / "progress.md").exists(), f"{lang}: progress.md が無い"


def test_mock_elevate_default_lang_is_en(_no_env_lang, tmp_path) -> None:
    """--lang 未指定なら既定 en で動き、英語テンプレートの成果物になる。"""
    code, _ = _run_main(
        ["elevate", "Design a morning routine", "--mock", "--out", str(tmp_path)],
        cwd=tmp_path.parent,
    )
    assert code == 0
    elevated = (tmp_path / "artifacts" / "elevated.md").read_text(encoding="utf-8")
    en_text = main.MockGenerator(lang="en").mock["generic_text"].strip()
    assert en_text in elevated


# ---- --output-format 明示指定のフォールバックが言語別（コード内 ja 定数漏れ防止） ----

@pytest.mark.parametrize("lang,expected_type", [
    ("en", "analytical report"),
    ("ja", "分析レポート"),
    ("zh", "分析报告"),
])
def test_parse_output_format_fallbacks_are_localized(lang, expected_type) -> None:
    """--output-format の JSON に欠けているフィールドは言語別ストアから補う。

    コード内の ja 定数（"成果物" / FINALIZE_INSTRUCTION）にフォールバックすると
    en/zh 実行で日本語が漏れるため、ストアの FORMAT_ANALYTICAL_TYPE /
    FINALIZE_INSTRUCTION を使う。ja は従来挙動（日本語）のまま。
    """
    raw = '{"min_output_length": 100, "max_output_length": 500, "description": "test"}'
    fmt = main._parse_output_format(raw, lang=lang)
    assert fmt.deliverable_type == expected_type
    # finalize_guidance は ja 定数（上記の止揚に基づき…）そのものでないこと。
    # ja の場合は日本語指示が正しいので、en/zh だけが日本語でないことを確認する。
    if lang == "ja":
        assert "上記の止揚" in fmt.finalize_guidance
    else:
        assert "上記の止揚" not in fmt.finalize_guidance


def test_parse_output_format_explicit_fields_win() -> None:
    """ユーザーが指定したフィールドは言語フォールバックより優先される。"""
    raw = ('{"deliverable_type": "tagline", "min_output_length": 5, "max_output_length": 50,'
           ' "finalize_guidance": "Write a punchy one-liner."}')
    fmt = main._parse_output_format(raw, lang="zh")
    assert fmt.deliverable_type == "tagline"
    assert fmt.finalize_guidance == "Write a punchy one-liner."


# ---- 品質評価: 英語キー抽出（D2）と言語別表示 ----

def test_quality_extract_english_keys() -> None:
    """品質評価JSONは英語キー（novelty/originality/surprise/rationale）で抽出する（D2）。"""
    text = '説明。\n{"novelty": 0.4, "originality": 0.6, "surprise": 0.5, "rationale": "理由"}'
    data = _extract_json(text)
    assert data == {"novelty": 0.4, "originality": 0.6, "surprise": 0.5, "rationale": "理由"}


def test_quality_extract_rejects_ja_keys() -> None:
    """旧日本語キーのみの JSON は抽出しない（D2: 英語キーに一本化）。"""
    text = '{"新奇度": 0.4, "独自性": 0.6, "意外性": 0.5, "理由": "…"}'
    assert _extract_json(text) == {}


def test_format_quality_line_localizes_labels() -> None:
    """format_quality_line のラベルが言語別に変わる。"""
    from evaluation.quality import QualityResult

    r = QualityResult(novelty=0.5, originality=0.5, surprise=0.5, rationale="…")
    en = format_quality_line(r, lang="en")
    ja = format_quality_line(r, lang="ja")
    zh = format_quality_line(r, lang="zh")
    assert en != ja and ja != zh and en != zh


# ---- 感傷ガード・創作系判定の言語別 ----

@pytest.mark.parametrize("lang,cliche", [
    ("ja", "感動を届ける"),
    ("zh", "泪流不止"),
    ("en", "can't stop crying"),
])
def test_sentimentality_detected_per_language(lang, cliche) -> None:
    """感傷定式（泣かせ定式）の検出が言語別キーワードで機能する。"""
    assert _detect_sentimentality(f"本文。{cliche}。", lang=lang)


@pytest.mark.parametrize("lang,term", [
    ("ja", "歌詞"),
    ("zh", "歌词"),
    ("en", "lyrics"),
])
def test_creative_task_detected_per_language(lang, term) -> None:
    """創作系タスク判定が言語別キーワードで機能する（草案上限の緩和）。"""
    assert _is_creative_task(f"{term}を書いてください", lang=lang)


def test_creative_task_not_detected_cross_language() -> None:
    """ja キーワードは en 判定に漏れない（言語別ストアが独立している）。"""
    assert not _is_creative_task("歌詞を書いてください", lang="en")
    assert not _is_creative_task("Write lyrics", lang="ja")


# ---- フェーズ8.2: 静的較正ドリフトチェック（翻訳後も数値契約が維持される） ----

def test_static_calibration_drift_passes() -> None:
    """3言語ストアのルーブリックが、翻訳後も較正契約（軸名・アンカー・帯域・品質キー）を維持する。"""
    import importlib.util

    script = Path(__file__).resolve().parent.parent / "utils" / "check_calibration_drift.py"
    spec = importlib.util.spec_from_file_location("check_calibration_drift", str(script))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    results = mod.run_checks()
    assert results, "チェックが空"
    failed = [r for r in results if not r["ok"]]
    assert not failed, f"較正契約のドリフト: {failed}"


# ---- 全コマンド × 3言語のフルカバレッジ（mock。ゲートウェイ不要） ----
# elevate / compare / improve は上記の通り。ここでは generate / diverge / synthesize と
# 各共通フラグ（--agents / --knowledge-file / --output-format）が全言語で完走し、
# 出力がローカライズされ、en/zh に日本語が漏れないことを保証する。

_KANA = re.compile(r"[ぁ-んァ-ヶ]")


@pytest.mark.parametrize("lang,task", [
    ("en", "Design a morning routine that makes the day productive"),
    ("ja", "朝のルーティーンを設計して、一日を充実した地に足の着いたものにしよう"),
    ("zh", "设计一个让一天高效而踏实的晨间习惯"),
])
def test_mock_generate_localized_output(tmp_path, lang, task) -> None:
    """generate --mock が各言語で完走し、出力が言語別テンプレートになる。"""
    code, out = _run_main(
        ["generate", task, "--mock", "--lang", lang, "--out", str(tmp_path)],
        cwd=tmp_path.parent,
    )
    assert code == 0
    expected = main.MockGenerator(lang=lang).mock["generic_text"].strip()
    assert expected in out, f"{lang}: generate 出力が {lang} テンプレートを含まない"


@pytest.mark.parametrize("lang,task", [
    ("en", "Design a morning routine that makes the day productive"),
    ("ja", "朝のルーティーンを設計して、一日を充実した地に足の着いたものにしよう"),
    ("zh", "设计一个让一天高效而踏实的晨间习惯"),
])
def test_mock_diverge_localized_drafts(tmp_path, lang, task) -> None:
    """diverge --mock が各言語で8草案を生成し、en/zh に日本語が漏れない。"""
    code, _ = _run_main(
        ["diverge", task, "--mock", "--lang", lang, "--out", str(tmp_path)],
        cwd=tmp_path.parent,
    )
    assert code == 0
    drafts = sorted((tmp_path / "drafts").glob("draft_*.md"))
    assert len(drafts) == 8, f"{lang}: 草案が8つでない"
    for p in drafts:
        text = p.read_text(encoding="utf-8")
        assert text.strip(), f"{lang}: {p.name} が空"
        if lang != "ja":
            assert not _KANA.search(text), f"{lang}: {p.name} に日本語が漏れている"


@pytest.mark.parametrize("lang,task", [
    ("en", "Design a morning routine that makes the day productive"),
    ("ja", "朝のルーティーンを設計して、一日を充実した地に足の着いたものにしよう"),
    ("zh", "设计一个让一天高效而踏实的晨间习惯"),
])
def test_mock_synthesize_localized(tmp_path, lang, task) -> None:
    """synthesize --mock が diverge した草案群から昇華し、言語別成果物を出す。"""
    code, _ = _run_main(
        ["diverge", task, "--mock", "--lang", lang, "--out", str(tmp_path)],
        cwd=tmp_path.parent,
    )
    assert code == 0
    drafts = [str(p) for p in sorted((tmp_path / "drafts").glob("draft_*.md"))]
    syn = tmp_path / "syn"
    code, _ = _run_main(
        ["synthesize"] + drafts + ["--task", task, "--mock", "--lang", lang, "--out", str(syn)],
        cwd=tmp_path.parent,
    )
    assert code == 0, f"{lang}: synthesize が完走しない"
    elevated = (syn / "artifacts" / "elevated.md").read_text(encoding="utf-8")
    assert elevated.strip(), f"{lang}: 昇華成果物が空"
    expected = main.MockGenerator(lang=lang).mock["generic_text"].strip()
    assert expected in elevated, f"{lang}: 成果物が {lang} テンプレートを含まない"


@pytest.mark.parametrize("lang,task", [
    ("en", "Design a morning routine that makes the day productive"),
    ("ja", "朝のルーティーンを設計して、一日を充実した地に足の着いたものにしよう"),
    ("zh", "设计一个让一天高效而踏实的晨间习惯"),
])
def test_mock_agents_subset_per_language(tmp_path, lang, task) -> None:
    """--agents で指定したエージェントのみ草案を生成する（言語横断）。"""
    code, _ = _run_main(
        ["elevate", task, "--mock", "--lang", lang, "--agents", "designer", "visionary",
         "--out", str(tmp_path)],
        cwd=tmp_path.parent,
    )
    assert code == 0
    names = sorted(p.stem for p in (tmp_path / "drafts").glob("draft_*.md"))
    assert names == ["draft_designer", "draft_visionary"], f"{lang}: サブセットが不正 {names}"


@pytest.mark.parametrize("lang,task,header", [
    ("en", "Design a morning routine that makes the day productive", "# Prior Knowledge"),
    ("ja", "朝のルーティーンを設計して、一日を充実した地に足の着いたものにしよう", "# 前提知識"),
    ("zh", "设计一个让一天高效而踏实的晨间习惯", "# 背景知识"),
])
def test_mock_knowledge_file_localized(tmp_path, lang, task, header) -> None:
    """--knowledge-file でも knowledge.md がローカライズされ保存される。"""
    kf = tmp_path / "kf.txt"
    kf.write_text("材料: 再生PET。ターゲット: 20〜30代。", encoding="utf-8")
    code, _ = _run_main(
        ["elevate", task, "--mock", "--lang", lang, "--knowledge-file", str(kf),
         "--out", str(tmp_path)],
        cwd=tmp_path.parent,
    )
    assert code == 0
    knowledge = (tmp_path / "knowledge.md").read_text(encoding="utf-8")
    assert header in knowledge, f"{lang}: knowledge.md の見出しがローカライズされていない"
    assert "材料" in knowledge, f"{lang}: 前提知識の本文が保存されていない"


@pytest.mark.parametrize("lang,task", [
    ("en", "Design a morning routine that makes the day productive"),
    ("ja", "朝のルーティーンを設計して、一日を充実した地に足の着いたものにしよう"),
    ("zh", "设计一个让一天高效而踏实的晨间习惯"),
])
def test_mock_explicit_output_format_per_language(tmp_path, lang, task) -> None:
    """--output-format 明示指定が各言語で完走し、format.md を保存する。"""
    fmt = ('{"deliverable_type": "plan", "min_output_length": 200, '
           '"max_output_length": 1500, "description": "morning plan"}')
    code, _ = _run_main(
        ["elevate", task, "--mock", "--lang", lang, "--output-format", fmt, "--out", str(tmp_path)],
        cwd=tmp_path.parent,
    )
    assert code == 0, f"{lang}: --output-format 指定が完走しない"
    assert (tmp_path / "format.md").exists(), f"{lang}: format.md が保存されていない"
