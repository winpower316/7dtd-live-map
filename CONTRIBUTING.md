# コントリビューション

IssueまたはPull Requestを歓迎します。

変更前に次を実行してください。

```powershell
python -m unittest discover -s player-auth -p "test_*.py"
python scripts/check_public_tree.py
```

PowerShellエージェントや公開APIを変更する場合は、個人情報を増やしていないこと、汎用コマンド実行経路を作っていないこと、再起動機能が既定OFFのままであることも確認してください。
