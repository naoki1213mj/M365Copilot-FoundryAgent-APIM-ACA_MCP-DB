---
name: Zenn 記事 Markdown 規約
description: Zenn 技術記事の Markdown 記法・文体ルール。articles/ 配下の .md 編集時に自動適用。AI 文体排除と Zenn 固有の記法制約を強制。
applyTo: "articles/**/*.md"
---
# Zenn 記事 Markdown ルール
- Zenn 記法準拠（https://zenn.dev/zenn/articles/markdown-guide）
- フロントマター必須: title (70字以内), emoji, type, topics, published
- コードブロックに言語指定。見出しは H2 から。見出しにコロン禁止
- :::message / :::details は ::: で閉じる
- Mermaid: subgraph ID は英数字のみ。ノードラベルに絵文字なし。分岐は半角英字
- 画像は /images/ 配下、出典キャプション必須
- bare URL 単独行は markdownlint-disable MD034 で囲む
- 冒頭に参照時点の :::message、末尾に :::details 免責事項
- AI 定型表現禁止（「以下に示すように」「非常に重要」「包括的な」）
- 体言止め禁止。6 点以上の箇条書き禁止。「まとめ」セクション禁止
