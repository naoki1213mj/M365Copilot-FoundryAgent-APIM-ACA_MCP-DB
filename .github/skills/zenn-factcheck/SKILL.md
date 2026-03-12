---
name: zenn-factcheck
description: "技術記事のファクトチェック。公式ドキュメント・GitHub・PyPI と照合。Triggers: ファクトチェック, バージョン確認, 公式と照合"
---
# ファクトチェック

## 検証対象

| 対象 | 確認内容 | 一次情報源 |
|------|---------|-----------|
| 製品名 | 正式名称、リブランド | 公式ドキュメント |
| バージョン | SDK版、GA/Preview | GitHub Releases, PyPI |
| コード | endpoint、認証方式 | SDK リポジトリ |
| 数値 | 価格、制限値 | 公式 Pricing |
| URL | リンク切れ | curl -sI |

## 検証コマンド
```bash
pip index versions <package> | head -5
gh release list --repo <owner>/<repo> --limit 5
curl -sI "<url>" | head -5
```

## 報告形式
### ✅ 正確
- 項目 — ソース確認済み

### ⚠️ 要修正
| 箇所 | 記事 | 正しい | ソース |
|------|------|--------|--------|

### ❌ 確認不可
- 項目 → 公式に記載なし
