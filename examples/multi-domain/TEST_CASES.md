# 分野横断フォーマット認識テスト — ケース記録

出力フォーマット認識（LLM動的抽出）＋前提知識注入の検証ケース。
再実行は実 API（claude-code）で
`main.py elevate <task> --engine claude-code --agents strategist humanist differentiator storyteller --out examples/multi-domain/<key>`
（エージェント構成は全ケース固定）。

背景: 分析レポート前提のパイプライン（TVRO最終化・ELEVATED_MIN_LENGTH=300）では
キャッチコピーも事業計画も同じ「分析レポート」になっていた。本機能により
**各分野の成果物そのもの**が出力されるようになった。

2026-08-09 に順次実行開始。**歌詞（ケース1）完了後、テストは途中で中止**（残りは未実行）。

2026-08-09 再開方針（ユーザー承認）: ケース2〜6は**前提知識（--knowledge）を全ケースに注入**して実行する。
知識は生成の土台（材料・市場・形式制約）として全段階に注入され、知識の範囲内で捏造しないことを
実 API で同時検証する（mock 検証は test_knowledge.py 19件で済み）。

## 実行ログ

| # | 分野 | タスク | 前提知識（--knowledge） | 結果 | exit |
|---|------|--------|--------------------------|------|------|
| 1 | 歌詞 | 海をテーマにした歌詞を書きなさい | なし | Aメロ/サビ/間奏/Cメロ/サビの節割りの歌詞本体『潮は返る』を出力。抽出 min=1200 に対し~700字の完成品となり3回再生成後に安全弁（構造的に完成した最終試行を受け入れて続行）が発動し exit 0 | 0 |
| 2 | 事業計画 | LED照明の事業計画を立案せよ | 材料・市場・規制・競合・価格帯 | 全草案（GaN/Ra80+/EU規制/200〜400EUR）を矛盾なく織り込んだ事業計画書（11,711字）。differentiator が草案生成で3回連続打ち切り→per-agent エラー捕捉でスキップし、残り3体で継続。末尾に整合性検証あり | 0 |
| 3 | 俳句 | 夏の終わりを詠んだ俳句を3句作りなさい | 季語・形式（五七五）・テーマ | 指定季語（月見・残暑・秋の蝉）を各1句に使用した五七五定型3句。形式と語彙は規範内に保ち、逸脱は意味の次元に置く二層構造を意図 | 0 |
| 4 | キャッチコピー | リサイクル素材のスニーカー『Maru』のキャッチコピーを開発せよ | 材料・ターゲット・価格帯・ブランド価値 | — | — |
| 5 | プレスリリース | リサイクル素材スニーカー『Maru』の新製品発表プレスリリースを作成せよ | 会社・製品・発売日・価格・特長 | — | — |
| 6 | 研究アブストラクト | 量子アニーリングの実用化に関する研究アブストラクトを書け | 分野・現状・課題・応用・制約 | — | — |

## ケースごとの知識・実行コマンド

```bash
# 2: 事業計画
.venv/bin/python main.py elevate "LED照明の事業計画を立案せよ" --engine claude-code \
  --agents strategist humanist differentiator storyteller --out examples/multi-domain/business-plan \
  --knowledge "材料: 窒化ガリウム(GaN)系LED、演色性Ra80以上。市場: 欧州の商業施設照明（2025年時点でLED化率約60%）。規制: EUエコデザイン指令により2030年までに蛍光灯の販売が禁止される。競合: 低価格品の多くはRa80未満の粗悪品。ターゲット: ヨーロッパの高級レストラン・ブティック。価格帯: 1台あたり200〜400EUR。"

# 3: 俳句
.venv/bin/python main.py elevate "夏の終わりを詠んだ俳句を3句作りなさい" --engine claude-code \
  --agents strategist humanist differentiator storyteller --out examples/multi-domain/haiku \
  --knowledge "季語: 残暑・初秋・秋の蝉・月見・萩。形式: 五七五の定型で、季語を1つ含む。テーマ: 夏の終わりの名残惜しさ、過ぎ去る季節への感傷。心象: 日本の四季の美意識・物哀れ。"

# 4: キャッチコピー
.venv/bin/python main.py elevate "リサイクル素材のスニーカー『Maru』のキャッチコピーを開発せよ" --engine claude-code \
  --agents strategist humanist differentiator storyteller --out examples/multi-domain/tagline \
  --knowledge "材料: 海岸回収の再生PETを100%使用。環境負荷は新品PET比で約70%削減。ターゲット: 20〜30代の環境意識の高い都市部在住。価格帯: 12,000円。ブランド価値: 海を守る一足。ライバル: 高機能だが環境配慮の乏しい既存ランニングシューズ。"

# 5: プレスリリース
.venv/bin/python main.py elevate "リサイクル素材スニーカー『Maru』の新製品発表プレスリリースを作成せよ" --engine claude-code \
  --agents strategist humanist differentiator storyteller --out examples/multi-domain/press-release \
  --knowledge "会社: 株式会社Maru（本社: 東京都港区）。製品: リサイクル素材スニーカー『Maru』。材料: 海岸回収の再生PETを100%使用。発売日: 2026年10月1日。価格: 12,000円（税込）。ターゲット: 20〜30代。特長: 環境負荷70%削減、軽量・通気性。"

# 6: 研究アブストラクト
.venv/bin/python main.py elevate "量子アニーリングの実用化に関する研究アブストラクトを書け" --engine claude-code \
  --agents strategist humanist differentiator storyteller --out examples/multi-domain/abstract \
  --knowledge "分野: 量子アニーリング（D-Wave系）。現状: 特定の最適化問題（組合せ最適化）で古典アルゴリズムを上回る事例が出始めているが、汎用的な高速化は未達成。課題: ノイズ・スケール・誤差補正・問題マッピング。応用候補: 物流ルート最適化・創薬の分子構造予測・ポートフォリオ最適化。制約: 数千量子ビット級の実機で実証。"
```
