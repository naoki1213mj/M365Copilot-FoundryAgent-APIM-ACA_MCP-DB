# Zenn Markdown 記法リファレンス

## フロントマター
```yaml
---
title: "記事タイトル"
emoji: "📦"
type: "tech"
topics: ["azure", "foundry", "apim", "mcp", "m365copilot"]
published: false
---
```

## メッセージボックス
```markdown
:::message
通常メッセージ
:::

:::message alert
警告
:::
```

## アコーディオン
```markdown
:::details タイトル
折りたたみ内容
:::
```

## コードブロック（ファイル名付き）
````markdown
```python:src/main.py
def hello():
    print("hello")
```
````

## 脚注
```markdown
本文[^1]
[^1]: 脚注内容
```
