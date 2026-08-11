**言語:** [English](CLAUDE.md) | [日本語](CLAUDE-ja.md) | [中文](CLAUDE-zh.md)

# elevate-draft-engine — Project Instructions

## 文書のルール

開発の経緯・履歴（日付付きの変更物語、再調整の経緯、旧設計との比較、過去の実測値など）は
**README / SKILL / examples/README に書かない**。履歴は `HISTORY.md` 一箇所にまとめる。

README / SKILL / examples/README には**現在の情報**だけを書く。現在の機能説明、現在のCLI、
現在の設計理由（日付を伴わない簡潔な理由）はOK。何かを説明するときに「かつてはXだったがYに
変更した」「再調整(2)により…」のような導入経緯の物語が必要になったら、それは HISTORY.md に書く。

**どこに何があるか**:
- `README.md`: 現在の機能・CLI・API・5軸・リポジトリ構成（概要。現在の情報のみ）
- `docs/`: README の深掘り詳細（`output-format.md` 出力フォーマット認識 / `knowledge.md` 前提知識注入 / `measurement.md` compare・improve / `api.md` Python API）。README は各節に概要＋docs/ へのリンクを置く
- `HISTORY.md`: 開発史（バージョン履歴、ルーブリック再調整の経緯、実測記録、知恵の評議会評価）
- `examples/README.md`: 現在のサンプル構成と使い方（過去の削除済みサンプルは載せない）
- `skills/elevate-draft-engine/SKILL.md`: ファサード skill（version番号は現在値のみ、バージョン履歴テーブルは HISTORY.md）
- `.claude/agents/`・`.claude/skills/`: プロジェクト内検出用symlink（root `agents/`・`skills/` への相対リンク。エンジン本体は `agents/*.md` を直接読むためインストール不要）
- `.claude-plugin/`: プラグイン配布定義（`/plugin marketplace add` 用）。`install.sh` は従来のグローバル/ローカル symlink 方式

## ポリシー固定（触らないもの）

- **5軸ルーブリック**: 多様性 / 統合性 / 超越性 / 誠実性 / 実用性（均等0.20）。`evaluation/evaluator.py` と `agents/*.md` は変更禁止。この5軸はポリシーであり、スコアリングの設計目標ではない。
- **3契機弁証法**: 否定・保存・高次化の三契機は機構の中核。発想レベル（`--idea-level`）で発散とAufhebenがどこまで極端に踏み込むかを選ぶ: standard 0.9（既定・後方互換）/ very 1.2 / extreme 1.5。各レベルに段階的な発散ヒントが対になる。最終化の温度0.0 は固定。
- **テーゼ集中形式**: 草案は 核心的主張 / 根拠 / 前提 の3要素・500〜800字。DRAFT_MAX_LENGTH=1000（創作系は3000に緩和）。
- **i18n基準**: 修正・変更の既定として多言語対応（en/ja/zh）を基本とする。新規・変更するプロンプト / CLIメッセージ / テンプレート / 保存出力は3層方式（ロケールJSON / 言語別プロンプト / ミラーツリー）で解決し、ユーザー向けテキストは実行言語（`--lang`）で生成する。

## テスト

`pytest tests/` で全件確認。259件（2026-08-11時点）。

## 破壊してはならないもの

- 完全性ガード（broken output → regenerate, 最大3回）
- per-agent エラー捕捉（単一エージェントの失敗で行列全体を落とさない）
- 安全弁（fmt 仕様の自己矛盾時に構造的に完成した最終試行を採用）

## Git

- `git push` はユーザーが明示的に指示したときだけ。指示なき push は禁止。
- commit message 末尾に `Co-Authored-By: Claude <noreply@anthropic.com>` を付与。
