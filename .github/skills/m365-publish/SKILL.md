---
name: m365-publish
description: "Foundry Agent を M365 Copilot / Teams に公開する手順。Triggers: publish to M365, one-click publish, Teams に公開, M365 Copilot, organization scope, Individual scope, agent store, エージェント公開"
---
# M365 Copilot Publish

## 手順

### 1. Agent Application 作成
Foundry → Agent → Publish → Create Agent Application。安定 endpoint + 専用 agent identity が生成される。

### 2. M365 Copilot に公開
Publish to Teams and M365 Copilot → メタデータ入力 → Azure Bot Service 自動作成 → scope 選択 → Prepare → Publish

### 3. Scope 戦略
- **Individual scope（デモ推奨）**: admin 不要、即時利用可、リンク共有。agent store の "Your agents" に表示
- **Organization scope（本番）**: M365 Admin Center で承認必要。"Built by your org" に表示

### 4. Agent Identity の権限付け直し（必須）
publish 後に agent identity が project identity から分離する。APIM の MCP.Tools.Read ロールを agent identity に再割り当て。これを忘れると 401。

### 5. テスト
M365 Copilot → agent store → "Your agents" → 選択 → 「INV-004 の在庫を教えて」

## 制約 (2026-03)
- `required_approval=false` → tool 実行に確認なし → read-only 限定で運用
- OAuth tool auth 未対応 → shared Entra auth or API key
- Private Link 未対応 → APIM レイヤーで保護
- Streaming/citations 未対応 → 在庫クエリなら問題なし
- Teams app catalog 自動登録なし → Individual scope か .zip 手動アップロード

## デモスクリプト
1. Foundry Playground で動作確認
2. Publish → M365 Copilot（Individual scope）
3. M365 Copilot で同じ質問 → 動く
4. 「API もセキュリティも同じ。UI surface だけ変わった」

## 参考
- https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/publish-copilot
- https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/publish-agent
- https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/publishing-agents-from-microsoft-foundry-to-microsoft-365-copilot--teams/4471184
