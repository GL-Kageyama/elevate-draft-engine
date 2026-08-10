**言語:** [English](../output-format.md) | [日本語](output-format.md) | [中文](../zh/output-format.md)

# 出力フォーマット認識（--output-format / 自動抽出）

パイプライン開始前に、タスクから期待される出力形式を LLM が動的に抽出する
（`extract_format`。1回の軽量コール、温度0.0、同一タスクはキャッシュ）。
抽出した `OutputFormat` を全段階に注入する:

```
Task → extract_format(task) [1 lightweight LLM call] → OutputFormat
                                                          │
    ┌─────────────────────────────────────────────────────┼──────────────────────────┐
    ↓                                                     ↓                          ↓
diverge()                                           aufheben()                 finalize()
・fmt.draft_guidance をタスクに追記                  ・deliverable_type を       ・fmt.finalize_guidance
  （キャッチコピーなら「候補+意図」形式で）           意識させる指示を追記         で TVRO を置換
・出力が成果物そのもの（output_is_direct）なら           （弁証法自体は不変）      ・fmt.{min,max}_output_length
  草案上限を創作系上限に緩める                                                 で完全性判定
```

`OutputFormat`（[elevate/engine.py](../elevate/engine.py)）:

| フィールド | 意味 |
|---|---|
| `deliverable_type` | 成果物の種別名（例: キャッチコピー / 事業計画書 / 歌詞 / 小説） |
| `description` | このタスクで良い成果物とは何か（1文） |
| `draft_guidance` | エージェント草案の形式指示（分析系ならテーゼ形式、短形式なら候補+根拠） |
| `finalize_guidance` | 最終化の形式指示（汎用 TVRO をタスク固有の構造で置換） |
| `min_output_length` / `max_output_length` | 最終成果物の長さ範囲（タスク固有。タグライン min=2 / 小説 max=8000 等） |
| `output_is_direct` | `true`=成果物そのもの（コピー・詩・歌詞） / `false`=成果物についての分析 |

## 挙動の細則

- **抽出失敗時は既存挙動（分析レポート前提・固定値）にフォールバック**する——劣化ではなく安全側への退避。
  分析系タスクは LLM が TVRO 相当の `finalize_guidance` を返すため、既存と同一の挙動になる。
- `--output-format '<JSON>'` で抽出をスキップして明示指定できる（mock でも有効。テスト・再現に使う）。
- 抽出/指定された仕様は `--out/format.md` に保存される（透明性）。
- 完全性ガードはタスク固有の長さ範囲で判定し、**直接成果物（output_is_direct）は文末記号を要求しない**
  （タグラインや詩は「。」で終わらないのが普通。固定の文終端チェックを要求すると完成形を再生成ループに落とす）。
- **仕様の自己矛盾は安全弁で吸収**: LLM 抽出のフォーマットが自己矛盾（抽出した `finalize_guidance` が
  要求する構造 > 抽出した `max_output_length` 等）で実質達成不能なとき、上限回数の再生成後、
  構造的に完成した（文終端のある）最後の試行を受け入れて続行する（警告を stderr に出す）。
  健全な成果物を仕様不整合だけで捨ててパイプライン全体を落とさない。fmt なし（既存の固定値判定）は
  従来どおり明示的失敗する。
- フォーマット適合性はハードゲート（完全性ガード）であり、5軸ルーブリックのスコアには**しない**
  （5軸はポリシー固定。ゴールポストは動かさない）。
