# LiveMapServerTools

公開WebマップのWindowsエージェント専用に、次の読み取り専用機能を追加する。

- `webplayerstats`: オンラインプレイヤーの名前、レベル、座標、HP、ping、ゲームステージ
- `webserverstats`: 稼働時間、FPS、メモリ、チャンク数、プレイヤー数、ゾンビ数、エンティティ数
- `webentityowners`: セーブ済みの所有エンティティIDと所有プレイヤーの表示名
- ゲーム内で「全員に共有」したウェイポイントを `shared-waypoints.json` へ保存

フレンド限定および私用ウェイポイントは保存しない。共有地点はゲームからWebへの一方向連携とし、Web側からゲームへ地点を作成する機能は持たせない。

IPアドレス、プラットフォームID、インベントリなどは出力しない。所有者一覧はプレイヤーセーブから読み、負荷を抑えるため1分間キャッシュする。コマンドはTelnet経由でWindowsエージェントだけが呼び出し、公開Webから任意コマンドを実行する経路は作らない。

## ビルド

`GameManagedPath` にDedicated Serverの `7DaysToDieServer_Data\Managed` を指定する。

```powershell
dotnet build -c Release `
  -p:GameManagedPath='C:\Program Files (x86)\Steam\steamapps\common\7 Days To Die\7DaysToDieServer_Data\Managed'
```

生成された `LiveMapServerTools.dll` を `ModInfo.xml` とともに、ゲームサーバーの `Mods\LiveMapServerTools` へ配置する。DLLの読み込みにはゲームサーバーの再起動が必要。

全員共有ウェイポイントの保持件数を変更する場合は、`config.example.json`を同じディレクトリの`config.json`へコピーして`sharedWaypointMaximumEntries`を1～5000の範囲で指定する。未配置時は200件。
