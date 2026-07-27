[CmdletBinding()]
param(
    [string]$ApiBase = 'http://127.0.0.1:18081',
    [string]$TokenPath = 'C:\ProgramData\7dtd-web-restart\agent.token',
    [string]$StartShortcut = 'C:\7dtd-server\startdedicated.bat.lnk',
    [string]$AuditPath = 'C:\ProgramData\7dtd-web-map\agent-audit.jsonl',
    [string]$GameRoot = 'C:\Program Files (x86)\Steam\steamapps\common\7 Days To Die',
    [ValidateSet('weekday', 'holiday', 'custom')]
    [string]$ScheduleMode = 'custom',
    [ValidateRange(0, 1440)]
    [int]$DayNightLengthMinutes = 0,
    [string]$MaintenanceTaskName = '',
    [ValidateRange(5, 300)]
    [int]$MapEntityPublishIntervalSeconds = 10,
    [ValidateRange(5, 300)]
    [int]$PlayerSnapshotPublishIntervalSeconds = 10,
    [switch]$EnableRestart,
    [switch]$Once,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Write-RestartAudit {
    param(
        [Parameter(Mandatory)]
        [string]$Event,
        [string]$JobId = '',
        [string]$Detail = ''
    )

    $record = [ordered]@{
        timestamp = (Get-Date).ToUniversalTime().ToString('o')
        event = $Event
        job_id = $JobId
        detail = $Detail
        dry_run = [bool]$DryRun
    }
    Add-Content -LiteralPath $AuditPath -Value (
        $record | ConvertTo-Json -Compress
    ) -Encoding utf8
}

function Test-TcpPort {
    param(
        [Parameter(Mandatory)]
        [string]$HostName,
        [Parameter(Mandatory)]
        [int]$Port,
        [int]$TimeoutMilliseconds = 1000
    )

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync($HostName, $Port)
        return $task.Wait($TimeoutMilliseconds) -and $client.Connected
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Receive-GameTelnetText {
    param(
        [Parameter(Mandatory)]
        [System.Net.Sockets.NetworkStream]$Stream,
        [int]$TimeoutSeconds = 4,
        [string]$StopPattern = '',
        [int]$IdleMilliseconds = 0
    )

    $buffer = [byte[]]::new(8192)
    $text = [System.Text.StringBuilder]::new()
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastDataAt = $null
    do {
        while ($Stream.DataAvailable) {
            try {
                $read = $Stream.Read($buffer, 0, $buffer.Length)
            }
            catch [System.IO.IOException] {
                return $text.ToString()
            }
            if ($read -le 0) {
                return $text.ToString()
            }
            $null = $text.Append(
                [System.Text.Encoding]::UTF8.GetString($buffer, 0, $read)
            )
            $lastDataAt = Get-Date
        }

        if (
            $StopPattern -and
            [regex]::IsMatch($text.ToString(), $StopPattern)
        ) {
            break
        }
        if (
            $IdleMilliseconds -gt 0 -and
            $null -ne $lastDataAt -and
            ((Get-Date) - $lastDataAt).TotalMilliseconds -ge
                $IdleMilliseconds
        ) {
            break
        }
        Start-Sleep -Milliseconds 100
    } while ((Get-Date) -lt $deadline)

    return $text.ToString()
}

function Send-GameCommand {
    param(
        [Parameter(Mandatory)]
        [string]$Command
    )

    if ($DryRun) {
        Write-RestartAudit -Event 'dry_run_command' -Detail $Command
        return
    }

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $connectTask = $client.ConnectAsync('127.0.0.1', 8081)
        if (-not $connectTask.Wait(5000) -or -not $client.Connected) {
            throw '7DTD Telnet (127.0.0.1:8081) に接続できません。'
        }
        $stream = $client.GetStream()
        $null = Receive-GameTelnetText `
            -Stream $stream `
            -TimeoutSeconds 3
        $bytes = [System.Text.Encoding]::UTF8.GetBytes("$Command`r`n")
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush()
        $response = Receive-GameTelnetText `
            -Stream $stream `
            -TimeoutSeconds 3 `
            -StopPattern 'Executing command|Chat \('
        if ($response -notmatch 'Executing command|Chat \(') {
            throw "Telnetコマンドの実行応答を確認できませんでした: $Command"
        }
    }
    finally {
        $client.Dispose()
    }
}

function Get-GameCommandResponse {
    param(
        [Parameter(Mandatory)]
        [string]$Command,
        [string]$StopPattern = 'Total of \d+ entities'
    )

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $connectTask = $client.ConnectAsync('127.0.0.1', 8081)
        if (-not $connectTask.Wait(5000) -or -not $client.Connected) {
            throw '7DTD Telnet (127.0.0.1:8081) に接続できません。'
        }
        $stream = $client.GetStream()
        $null = Receive-GameTelnetText `
            -Stream $stream `
            -TimeoutSeconds 3
        $bytes = [System.Text.Encoding]::UTF8.GetBytes("$Command`r`n")
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush()
        return Receive-GameTelnetText `
            -Stream $stream `
            -TimeoutSeconds 6 `
            -StopPattern $StopPattern `
            -IdleMilliseconds 800
    }
    finally {
        $client.Dispose()
    }
}

function Get-RunningGameLogPath {
    $serverProcess = Get-CimInstance Win32_Process `
        -Filter "Name='7DaysToDieServer.exe'" |
        Select-Object -First 1
    if ($null -eq $serverProcess) {
        throw '7DTDサーバープロセスが見つかりません。'
    }

    $logPathMatch = [regex]::Match(
        [string]$serverProcess.CommandLine,
        '-logfile\s+"([^"]+)"'
    )
    if (-not $logPathMatch.Success) {
        throw '7DTDプロセスの起動引数からログファイルを特定できません。'
    }
    return $logPathMatch.Groups[1].Value
}

function Test-GameLoginReady {
    try {
        $logPath = Get-RunningGameLogPath
        return [bool](
            Select-String `
                -LiteralPath $logPath `
                -Pattern '\[Steamworks\.NET\] GameServer\.LogOn successful' `
                -Quiet `
                -ErrorAction Stop
        )
    }
    catch {
        return $false
    }
}

function Resolve-MapEntityKind {
    param(
        [Parameter(Mandatory)]
        [string]$EntityType,
        [Parameter(Mandatory)]
        [string]$EntityName
    )

    if ($EntityType -eq 'EntitySupplyCrate') {
        return 'supply'
    }
    if (
        $EntityType -match 'Drone' -or
        $EntityName -match '(?i)drone'
    ) {
        return 'drone'
    }

    switch -Regex ($EntityName) {
        '^vehicleBicycle$' { return 'bicycle' }
        '^vehicleMinibike$' { return 'minibike' }
        '^vehicleMotorcycle$' { return 'motorcycle' }
        '^vehicle4x4Truck$' { return 'four_by_four' }
        '^vehicleGyrocopter$' { return 'gyrocopter' }
        '^vehicle' { return 'vehicle' }
        default { return $null }
    }
}

function New-PublicMapEntity {
    param(
        [Parameter(Mandatory)]
        [string]$EntityId,
        [Parameter(Mandatory)]
        [string]$Kind,
        [Parameter(Mandatory)]
        [double]$X,
        [Parameter(Mandatory)]
        [double]$Y,
        [Parameter(Mandatory)]
        [double]$Z,
        [string]$Label = '',
        [string]$Owner = '',
        [string]$Detail = '',
        [object]$QuestCode = $null
    )

    $entity = [ordered]@{
        entityId = $EntityId
        kind = $Kind
        position = [ordered]@{
            x = $X
            y = $Y
            z = $Z
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($Label)) {
        $entity.label = $Label
    }
    if (-not [string]::IsNullOrWhiteSpace($Owner)) {
        $entity.owner = $Owner
    }
    if (-not [string]::IsNullOrWhiteSpace($Detail)) {
        $entity.detail = $Detail
    }
    if ($null -ne $QuestCode) {
        $entity.questCode = [int]$QuestCode
    }
    return $entity
}

function New-StablePublicEntityId {
    param(
        [Parameter(Mandatory)]
        [string]$Value
    )

    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($Value)
        $hash = $sha256.ComputeHash($bytes)
        $number = [BitConverter]::ToUInt64($hash, 0) % 9000000000000000000
        return $number.ToString([Globalization.CultureInfo]::InvariantCulture)
    }
    finally {
        $sha256.Dispose()
    }
}

function Get-GeneratedWorldTraderEntities {
    $configPath = Join-Path $GameRoot 'serverconfig.xml'
    if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
        throw "現在のサーバー設定が見つかりません: $configPath"
    }

    [xml]$config = Get-Content -LiteralPath $configPath -Raw -Encoding utf8
    $properties = @{}
    foreach ($property in $config.ServerSettings.property) {
        $properties[[string]$property.name] = [string]$property.value
    }

    $gameName = $properties['GameName']
    if ([string]::IsNullOrWhiteSpace($gameName)) {
        throw 'serverconfig.xmlのGameNameが空です。'
    }
    $userDataFolder = $properties['UserDataFolder']
    if ([string]::IsNullOrWhiteSpace($userDataFolder)) {
        $userDataFolder = Join-Path $env:APPDATA '7DaysToDie'
    }

    $savesRoot = Join-Path $userDataFolder 'Saves'
    $activeWorlds = @(
        Get-ChildItem -LiteralPath $savesRoot -Directory |
            Where-Object {
                Test-Path `
                    -LiteralPath (Join-Path $_.FullName $gameName) `
                    -PathType Container
            }
    )
    if ($activeWorlds.Count -ne 1) {
        throw (
            '現在のセーブに対応する生成ワールドを一意に決定できません。' +
            " GameName=$gameName, candidates=$($activeWorlds.Count)"
        )
    }

    $worldName = $activeWorlds[0].Name
    $prefabsPath = Join-Path (
        Join-Path (
            Join-Path $userDataFolder 'GeneratedWorlds'
        ) $worldName
    ) 'prefabs.xml'
    if (-not (Test-Path -LiteralPath $prefabsPath -PathType Leaf)) {
        throw "生成ワールドのprefabs.xmlが見つかりません: $prefabsPath"
    }

    $traderKinds = @{
        trader_joel = 'trader_joel'
        trader_jen = 'trader_jen'
        trader_bob = 'trader_bob'
        trader_hugh = 'trader_hugh'
        trader_rekt = 'trader_rekt'
    }
    [xml]$prefabs = Get-Content -LiteralPath $prefabsPath -Raw -Encoding utf8
    $entities = @(
        foreach ($decoration in $prefabs.prefabs.decoration) {
            $name = [string]$decoration.name
            if (-not $traderKinds.ContainsKey($name)) {
                continue
            }
            $position = @(
                ([string]$decoration.position).Split(',') |
                    ForEach-Object { [int]$_.Trim() }
            )
            if ($position.Count -ne 3) {
                throw "トレーダー座標を解析できません: $name"
            }
            $x = $position[0]
            $y = $position[1]
            $z = $position[2]
            $entityId = '{0:D5}{1:D5}' -f ($x + 50000), ($z + 50000)
            New-PublicMapEntity `
                -EntityId $entityId `
                -Kind $traderKinds[$name] `
                -X $x `
                -Y $y `
                -Z $z
        }
    )
    if ($entities.Count -eq 0) {
        throw "生成ワールド $worldName にトレーダーが見つかりません。"
    }
    return @($entities | Sort-Object kind, entityId)
}

function Get-GameMapEntities {
    param(
        [AllowEmptyCollection()]
        [object[]]$WorldTraderEntities = @()
    )

    $entities = @{}

    foreach ($trader in $WorldTraderEntities) {
        $kind = [string]$trader['kind']
        $entityId = [string]$trader['entityId']
        $entities["${kind}:$entityId"] = $trader
    }

    # VehicleManagerの最新保存スナップショットには、未ロードチャンクの車両も含まれる。
    $logPath = Get-RunningGameLogPath
    $vehiclePattern = [regex]::new(
        'VehicleManager write #(?<number>\d+), id (?<id>\d+), ' +
        '(?<name>[^,]+), \((?<x>-?\d+(?:\.\d+)?), ' +
        '(?<y>-?\d+(?:\.\d+)?), (?<z>-?\d+(?:\.\d+)?)\)'
    )
    $vehicleMatches = @(
        foreach (
            $line in Get-Content `
                -LiteralPath $logPath `
                -Tail 20000 `
                -Encoding utf8
        ) {
            $match = $vehiclePattern.Match($line)
            if ($match.Success) {
                [pscustomobject]@{
                    Number = [int]$match.Groups['number'].Value
                    Id = $match.Groups['id'].Value
                    Name = $match.Groups['name'].Value
                    X = [double]$match.Groups['x'].Value
                    Y = [double]$match.Groups['y'].Value
                    Z = [double]$match.Groups['z'].Value
                }
            }
        }
    )
    $latestSnapshotStart = -1
    for ($index = 0; $index -lt $vehicleMatches.Count; $index++) {
        if ($vehicleMatches[$index].Number -eq 0) {
            $latestSnapshotStart = $index
        }
    }
    if ($latestSnapshotStart -ge 0) {
        for (
            $index = $latestSnapshotStart;
            $index -lt $vehicleMatches.Count;
            $index++
        ) {
            $vehicle = $vehicleMatches[$index]
            $kind = Resolve-MapEntityKind `
                -EntityType 'EntityVehicle' `
                -EntityName $vehicle.Name
            if ($null -ne $kind) {
                $entities["${kind}:$($vehicle.Id)"] = New-PublicMapEntity `
                    -EntityId $vehicle.Id `
                    -Kind $kind `
                    -X $vehicle.X `
                    -Y $vehicle.Y `
                    -Z $vehicle.Z
            }
        }
    }

    # listentsは補給物資・稼働中ドローンと、ロード済み車両の現在位置に使う。
    $entityText = Get-GameCommandResponse -Command 'listents'
    $entityPattern = [regex]::new(
        '\[type=(?<type>[^,\]]+), name=(?<name>[^,\]]+), ' +
        'id=(?<id>\d+)\], pos=\((?<x>-?\d+(?:\.\d+)?), ' +
        '(?<y>-?\d+(?:\.\d+)?), (?<z>-?\d+(?:\.\d+)?)\)'
    )
    foreach ($match in $entityPattern.Matches($entityText)) {
        $kind = Resolve-MapEntityKind `
            -EntityType $match.Groups['type'].Value `
            -EntityName $match.Groups['name'].Value
        if ($null -eq $kind) {
            continue
        }
        $entityId = $match.Groups['id'].Value
        $entities["${kind}:$entityId"] = New-PublicMapEntity `
            -EntityId $entityId `
            -Kind $kind `
            -X ([double]$match.Groups['x'].Value) `
            -Y ([double]$match.Groups['y'].Value) `
            -Z ([double]$match.Groups['z'].Value)
    }

    return @(
        $entities.Values |
            Sort-Object kind, entityId
    )
}

function Publish-GameMapEntities {
    param(
        [Parameter(Mandatory)]
        [hashtable]$Headers,
        [Parameter(Mandatory)]
        [AllowEmptyCollection()]
        [object[]]$Entities
    )

    $body = @{
        entities = @($Entities)
    } | ConvertTo-Json -Depth 5 -Compress
    $response = Invoke-WebRequest `
        -Uri "$ApiBase/internal/map-entities" `
        -Headers $Headers `
        -ContentType 'application/json' `
        -Body $body `
        -Method Post `
        -TimeoutSec 10 `
        -SkipHttpErrorCheck

    if ($response.StatusCode -ne 200) {
        throw "地図エンティティ通知APIが HTTP $($response.StatusCode) を返しました。"
    }
}

function Get-ActiveSaveDirectory {
    $configPath = Join-Path $GameRoot 'serverconfig.xml'
    if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
        throw "現在のサーバー設定が見つかりません: $configPath"
    }

    [xml]$config = Get-Content -LiteralPath $configPath -Raw -Encoding utf8
    $properties = @{}
    foreach ($property in $config.ServerSettings.property) {
        $properties[[string]$property.name] = [string]$property.value
    }
    $gameName = $properties['GameName']
    if ([string]::IsNullOrWhiteSpace($gameName)) {
        throw 'serverconfig.xmlのGameNameが空です。'
    }
    $userDataFolder = $properties['UserDataFolder']
    if ([string]::IsNullOrWhiteSpace($userDataFolder)) {
        $userDataFolder = Join-Path $env:APPDATA '7DaysToDie'
    }

    $activeSaves = @(
        Get-ChildItem -LiteralPath (Join-Path $userDataFolder 'Saves') -Directory |
            ForEach-Object {
                Join-Path $_.FullName $gameName
            } |
            Where-Object {
                Test-Path -LiteralPath $_ -PathType Container
            }
    )
    if ($activeSaves.Count -ne 1) {
        throw (
            '現在のプレイヤー保存先を一意に決定できません。' +
            " GameName=$gameName, candidates=$($activeSaves.Count)"
        )
    }
    return $activeSaves[0]
}

function Get-ActivePlayerDirectory {
    return Join-Path (Get-ActiveSaveDirectory) 'Player'
}

function Get-PlayerProfiles {
    $playerDirectory = Get-ActivePlayerDirectory
    return @(
        foreach (
            $metaFile in Get-ChildItem `
                -LiteralPath $playerDirectory `
                -Filter '*.ttp.meta' `
                -File
        ) {
            [xml]$metadata = Get-Content `
                -LiteralPath $metaFile.FullName `
                -Raw `
                -Encoding utf8
            $name = [string]$metadata.PlayerMetaInfo.name
            $level = 0
            if (
                [string]::IsNullOrWhiteSpace($name) -or
                -not [int]::TryParse(
                    [string]$metadata.PlayerMetaInfo.level,
                    [ref]$level
                )
            ) {
                throw "プレイヤーメタデータを解析できません: $($metaFile.Name)"
            }
            [ordered]@{
                name = $name
                level = $level
                profileSavedAt = [DateTimeOffset]::new(
                    $metaFile.LastWriteTimeUtc
                ).ToUnixTimeSeconds()
            }
        }
    )
}

function ConvertFrom-GamePosition {
    param(
        [Parameter(Mandatory)]
        [string]$Value
    )

    $parts = @(
        $Value.Split(',') |
            ForEach-Object { [double]$_.Trim() }
    )
    if ($parts.Count -ne 3) {
        throw "ゲーム座標を解析できません: $Value"
    }
    return $parts
}

function Get-PrivateMapEntities {
    $saveDirectory = Get-ActiveSaveDirectory
    $playersPath = Join-Path $saveDirectory 'players.xml'
    if (-not (Test-Path -LiteralPath $playersPath -PathType Leaf)) {
        throw "players.xmlが見つかりません: $playersPath"
    }

    [xml]$playersXml = Get-Content `
        -LiteralPath $playersPath `
        -Raw `
        -Encoding utf8
    $questTypes = @(
        '依頼元',
        '目的地',
        'POI',
        'POI範囲',
        '宝の地点',
        '回収地点',
        '隠し箱',
        '起動地点',
        '宝のオフセット',
        'トレーダー'
    )
    $entities = @()
    foreach ($playerNode in $playersXml.SelectNodes('/persistentplayerdata/player')) {
        $playerName = [string]$playerNode.GetAttribute('playername')
        if ([string]::IsNullOrWhiteSpace($playerName)) {
            continue
        }

        $bedroll = $playerNode.SelectSingleNode('bedroll')
        if ($null -ne $bedroll) {
            $position = ConvertFrom-GamePosition `
                -Value ([string]$bedroll.GetAttribute('pos'))
            $entities += New-PublicMapEntity `
                -EntityId (New-StablePublicEntityId "bedroll|$playerName") `
                -Kind 'bedroll' `
                -X $position[0] `
                -Y $position[1] `
                -Z $position[2] `
                -Label "$playerName の寝袋" `
                -Owner $playerName
        }

        foreach ($questNode in $playerNode.SelectNodes('questpositions/position')) {
            $questCode = [int]$questNode.GetAttribute('id')
            $positionType = [int]$questNode.GetAttribute('positiondatatype')
            $position = ConvertFrom-GamePosition `
                -Value ([string]$questNode.GetAttribute('pos'))
            $detail = if (
                $positionType -ge 0 -and
                $positionType -lt $questTypes.Count
            ) {
                $questTypes[$positionType]
            }
            else {
                "種別 $positionType"
            }
            $entities += New-PublicMapEntity `
                -EntityId (
                    New-StablePublicEntityId (
                        "quest|$playerName|$questCode|$positionType"
                    )
                ) `
                -Kind 'quest' `
                -X $position[0] `
                -Y $position[1] `
                -Z $position[2] `
                -Label "$playerName のクエスト地点" `
                -Owner $playerName `
                -Detail $detail `
                -QuestCode $questCode
        }
    }

    $sharedPath = Join-Path (
        Join-Path $GameRoot 'Mods\LiveMapServerTools'
    ) 'shared-waypoints.json'
    if (Test-Path -LiteralPath $sharedPath -PathType Leaf) {
        $sharedWaypoints = @(
            Get-Content -LiteralPath $sharedPath -Raw -Encoding utf8 |
                ConvertFrom-Json
        )
        foreach ($waypoint in $sharedWaypoints) {
            $name = [string]$waypoint.name
            $owner = [string]$waypoint.owner
            $entities += New-PublicMapEntity `
                -EntityId (
                    New-StablePublicEntityId (
                        'waypoint|{0}|{1}|{2}|{3}' -f
                        $owner,
                        $name,
                        $waypoint.position.x,
                        $waypoint.position.z
                    )
                ) `
                -Kind 'shared_waypoint' `
                -X ([double]$waypoint.position.x) `
                -Y ([double]$waypoint.position.y) `
                -Z ([double]$waypoint.position.z) `
                -Label $name `
                -Owner $owner `
                -Detail 'ゲーム内で全員に共有'
        }
    }

    return @($entities | Sort-Object kind, entityId)
}

function Get-OnlinePlayerStats {
    $commandDll = Join-Path (
        Join-Path $GameRoot 'Mods\LiveMapServerTools'
    ) 'LiveMapServerTools.dll'
    $gameProcess = Get-Process `
        -Name '7DaysToDieServer' `
        -ErrorAction SilentlyContinue |
        Select-Object -First 1
    $useDetailedCommand = (
        $null -ne $gameProcess -and
        (Test-Path -LiteralPath $commandDll -PathType Leaf) -and
        $gameProcess.StartTime.ToUniversalTime() -ge
            (Get-Item -LiteralPath $commandDll).LastWriteTimeUtc
    )

    if ($useDetailedCommand) {
        $playerText = Get-GameCommandResponse `
            -Command 'webplayerstats' `
            -StopPattern 'LIVEMAP_PLAYER_STATS_END'
        return @(
            foreach (
                $match in [regex]::Matches(
                    $playerText,
                    '(?m)^LIVEMAP_PLAYER_STATS (?<json>\{.+\})\r?$'
                )
            ) {
                $match.Groups['json'].Value | ConvertFrom-Json
            }
        )
    }

    $playerText = Get-GameCommandResponse `
        -Command 'listplayers' `
        -StopPattern 'Total of \d+ in the game'
    $playerPattern = [regex]::new(
        '(?m)^\d+\.\s+id=\d+,\s+(?<name>.*?),\s+' +
        'pos=\((?<x>-?\d+(?:\.\d+)?),\s*' +
        '(?<y>-?\d+(?:\.\d+)?),\s*' +
        '(?<z>-?\d+(?:\.\d+)?)\),.*?' +
        'health=(?<health>\d+),.*?' +
        'level=(?<level>\d+),.*?' +
        'ping=(?<ping>\d+)\r?$'
    )
    return @(
        foreach ($match in $playerPattern.Matches($playerText)) {
            [ordered]@{
                name = $match.Groups['name'].Value
                level = [int]$match.Groups['level'].Value
                position = [ordered]@{
                    x = [double]$match.Groups['x'].Value
                    y = [double]$match.Groups['y'].Value
                    z = [double]$match.Groups['z'].Value
                }
                health = [int]$match.Groups['health'].Value
                maxHealth = $null
                ping = [int]$match.Groups['ping'].Value
                gameStage = $null
            }
        }
    )
}

function Publish-PlayerSnapshot {
    param(
        [Parameter(Mandatory)]
        [hashtable]$Headers,
        [Parameter(Mandatory)]
        [AllowEmptyCollection()]
        [object[]]$Profiles,
        [Parameter(Mandatory)]
        [AllowEmptyCollection()]
        [object[]]$OnlinePlayers
    )

    $body = @{
        profiles = @($Profiles)
        onlinePlayers = @($OnlinePlayers)
    } | ConvertTo-Json -Depth 6 -Compress
    $response = Invoke-WebRequest `
        -Uri "$ApiBase/internal/player-snapshot" `
        -Headers $Headers `
        -ContentType 'application/json' `
        -Body $body `
        -Method Post `
        -TimeoutSec 10 `
        -SkipHttpErrorCheck
    if ($response.StatusCode -ne 200) {
        throw "プレイヤー情報通知APIが HTTP $($response.StatusCode) を返しました。"
    }
}

function Get-BiomeImagePath {
    $saveDirectory = Get-ActiveSaveDirectory
    $worldName = Split-Path (Split-Path $saveDirectory -Parent) -Leaf
    $configPath = Join-Path $GameRoot 'serverconfig.xml'
    [xml]$config = Get-Content -LiteralPath $configPath -Raw -Encoding utf8
    $userDataProperty = (
        $config.ServerSettings.property |
            Where-Object { $_.name -eq 'UserDataFolder' } |
            Select-Object -First 1
    )
    $userDataFolder = if ($null -ne $userDataProperty) {
        [string]$userDataProperty.value
    }
    else {
        ''
    }
    if ([string]::IsNullOrWhiteSpace($userDataFolder)) {
        $userDataFolder = Join-Path $env:APPDATA '7DaysToDie'
    }
    $path = Join-Path (
        Join-Path (
            Join-Path $userDataFolder 'GeneratedWorlds'
        ) $worldName
    ) 'biomes.png'
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "biomes.pngが見つかりません: $path"
    }
    return $path
}

function Publish-BiomeImage {
    param(
        [Parameter(Mandatory)]
        [hashtable]$Headers,
        [Parameter(Mandatory)]
        [string]$Path
    )

    $body = @{
        pngBase64 = [Convert]::ToBase64String(
            [IO.File]::ReadAllBytes($Path)
        )
    } | ConvertTo-Json -Compress
    $response = Invoke-WebRequest `
        -Uri "$ApiBase/internal/biome" `
        -Headers $Headers `
        -ContentType 'application/json' `
        -Body $body `
        -Method Post `
        -TimeoutSec 15 `
        -SkipHttpErrorCheck
    if ($response.StatusCode -ne 200) {
        throw "バイオーム画像通知APIが HTTP $($response.StatusCode) を返しました。"
    }
}

function Get-GameServerStatus {
    $text = Get-GameCommandResponse `
        -Command 'webserverstats' `
        -StopPattern 'LIVEMAP_SERVER_STATUS_END'
    $match = [regex]::Match(
        $text,
        '(?m)^LIVEMAP_SERVER_STATUS (?<json>\{.+\})\r?$'
    )
    if (-not $match.Success) {
        throw 'ゲームサーバー統計を解析できません。'
    }
    return $match.Groups['json'].Value | ConvertFrom-Json
}

function Publish-GameServerStatus {
    param(
        [Parameter(Mandatory)]
        [hashtable]$Headers,
        [Parameter(Mandatory)]
        [object]$Status
    )

    $body = $Status | ConvertTo-Json -Depth 4 -Compress
    $response = Invoke-WebRequest `
        -Uri "$ApiBase/internal/server-status" `
        -Headers $Headers `
        -ContentType 'application/json' `
        -Body $body `
        -Method Post `
        -TimeoutSec 10 `
        -SkipHttpErrorCheck
    if ($response.StatusCode -ne 200) {
        throw "サーバー統計通知APIが HTTP $($response.StatusCode) を返しました。"
    }
}

function Send-GameChatMessage {
    param(
        [Parameter(Mandatory)]
        [string]$Message
    )

    if ($Message -match '["\r\n]') {
        throw 'チャット通知には引用符や改行を使用できません。'
    }
    $command = 'say "{0}"' -f $Message
    if (
        [System.Text.Encoding]::UTF8.GetByteCount("$command`r`n") -gt 64
    ) {
        throw 'チャット通知がTelnetの1行上限（64バイト）を超えています。'
    }
    Send-GameCommand -Command $command
}

function Get-GameServerVersion {
    $logPath = Get-RunningGameLogPath
    $fileStream = $null
    $reader = $null
    try {
        $fileStream = [System.IO.File]::Open(
            $logPath,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::Read,
            [System.IO.FileShare]::ReadWrite
        )
        $reader = [System.IO.StreamReader]::new(
            $fileStream,
            [System.Text.Encoding]::UTF8,
            $true
        )
        for ($lineNumber = 0; $lineNumber -lt 200; $lineNumber++) {
            $line = $reader.ReadLine()
            if ($null -eq $line) {
                break
            }
            $match = [regex]::Match(
                $line,
                '\bVersion:\s*(V\s+\d+\.\d+\.\d+\s+\(b\d+\))'
            )
            if ($match.Success) {
                return $match.Groups[1].Value
            }
        }

        throw '起動ログからゲーム本体のバージョンを取得できませんでした。'
    }
    finally {
        if ($null -ne $reader) {
            $reader.Dispose()
        }
        elseif ($null -ne $fileStream) {
            $fileStream.Dispose()
        }
    }
}

function Publish-GameServerVersion {
    param(
        [Parameter(Mandatory)]
        [hashtable]$Headers,
        [Parameter(Mandatory)]
        [string]$Version
    )

    $body = @{ version = $Version } | ConvertTo-Json -Compress
    $response = Invoke-WebRequest `
        -Uri "$ApiBase/internal/server-version" `
        -Headers $Headers `
        -ContentType 'application/json' `
        -Body $body `
        -Method Post `
        -TimeoutSec 10 `
        -SkipHttpErrorCheck

    if ($response.StatusCode -ne 200) {
        throw "バージョン通知APIが HTTP $($response.StatusCode) を返しました。"
    }
}

function Get-GameSchedule {
    $configPath = Join-Path $GameRoot 'serverconfig.xml'
    if (-not (Test-Path -LiteralPath $configPath -PathType Leaf)) {
        throw "現在のサーバー設定が見つかりません: $configPath"
    }

    [xml]$config = Get-Content -LiteralPath $configPath -Raw -Encoding utf8
    $properties = @{}
    foreach ($property in $config.ServerSettings.property) {
        $properties[[string]$property.name] = [string]$property.value
    }

    $effectiveDayLength = $DayNightLengthMinutes
    if ($effectiveDayLength -eq 0) {
        if (-not $properties.ContainsKey('DayNightLength')) {
            throw 'DayNightLengthが設定にありません。-DayNightLengthMinutesを指定してください。'
        }
        $effectiveDayLength = [int]$properties['DayNightLength']
    }
    if ($effectiveDayLength -lt 1 -or $effectiveDayLength -gt 1440) {
        throw "DayNightLengthの値が範囲外です: $effectiveDayLength"
    }

    return @{
        mode = $ScheduleMode
        dayNightLengthMinutes = $effectiveDayLength
        bloodMoonFrequencyDays = [int]$properties['BloodMoonFrequency']
        bloodMoonRangeDays = [int]$properties['BloodMoonRange']
        bloodMoonStartHour = 22
    }
}

function Publish-GameSchedule {
    param(
        [Parameter(Mandatory)]
        [hashtable]$Headers,
        [Parameter(Mandatory)]
        [hashtable]$Schedule
    )

    $body = $Schedule | ConvertTo-Json -Compress
    $response = Invoke-WebRequest `
        -Uri "$ApiBase/internal/game-schedule" `
        -Headers $Headers `
        -ContentType 'application/json' `
        -Body $body `
        -Method Post `
        -TimeoutSec 10 `
        -SkipHttpErrorCheck

    if ($response.StatusCode -ne 200) {
        throw "ゲーム設定通知APIが HTTP $($response.StatusCode) を返しました。"
    }
}

function Get-AgentAction {
    param(
        [Parameter(Mandatory)]
        [hashtable]$Headers
    )

    $response = Invoke-WebRequest `
        -Uri "$ApiBase/internal/restart/agent" `
        -Headers $Headers `
        -Method Get `
        -TimeoutSec 10 `
        -SkipHttpErrorCheck

    if ($response.StatusCode -eq 204) {
        return $null
    }
    if ($response.StatusCode -ne 200) {
        throw "エージェントAPIが HTTP $($response.StatusCode) を返しました。"
    }
    return ($response.Content | ConvertFrom-Json).data
}

function Complete-AgentAction {
    param(
        [Parameter(Mandatory)]
        [hashtable]$Headers,
        [Parameter(Mandatory)]
        [string]$JobId,
        [Parameter(Mandatory)]
        [bool]$Success,
        [Parameter(Mandatory)]
        [string]$Result
    )

    $body = @{
        jobId = $JobId
        success = $Success
        result = $Result
    } | ConvertTo-Json -Compress
    $response = Invoke-WebRequest `
        -Uri "$ApiBase/internal/restart/complete" `
        -Headers $Headers `
        -ContentType 'application/json' `
        -Body $body `
        -Method Post `
        -TimeoutSec 10 `
        -SkipHttpErrorCheck

    if ($response.StatusCode -ne 200) {
        throw "完了通知APIが HTTP $($response.StatusCode) を返しました。"
    }
}

function Invoke-Announcement {
    param(
        [Parameter(Mandatory)]
        [string]$Action,
        [Parameter(Mandatory)]
        [string]$JobId
    )

    $message = switch ($Action) {
        'announce_5_minutes' {
            'Restart in 5 min. You can still cancel it.'
        }
        'announce_1_minute' {
            'Server restart scheduled in 1 minute.'
        }
        'announce_30_seconds' {
            'Server restart scheduled in 30 seconds.'
        }
        'announce_10_seconds' {
            'Server restart scheduled in 10 seconds.'
        }
        'announce_cancelled' {
            'The scheduled server restart has been cancelled.'
        }
        default {
            throw "未知の予告アクションです: $Action"
        }
    }

    Send-GameChatMessage -Message $message
    Write-RestartAudit -Event $Action -JobId $JobId -Detail $message
}

function Invoke-GameRestart {
    param(
        [Parameter(Mandatory)]
        [string]$JobId
    )

    if (-not [string]::IsNullOrWhiteSpace($MaintenanceTaskName)) {
        $maintenanceTask = Get-ScheduledTask `
            -TaskName $MaintenanceTaskName `
            -ErrorAction SilentlyContinue
        if ($maintenanceTask -and $maintenanceTask.State -eq 'Running') {
            throw "定期メンテナンス $MaintenanceTaskName が実行中のため中止しました。"
        }
    }
    if (-not (Test-Path -LiteralPath $StartShortcut -PathType Leaf)) {
        throw "起動ショートカットが見つかりません: $StartShortcut"
    }

    Write-RestartAudit -Event 'restart_started' -JobId $JobId
    Send-GameChatMessage -Message 'Server restart is starting now.'
    Send-GameCommand -Command 'shutdown'

    if ($DryRun) {
        Write-RestartAudit -Event 'dry_run_restart_complete' -JobId $JobId
        return
    }

    $shutdownDeadline = (Get-Date).AddSeconds(90)
    do {
        $serverProcesses = @(
            Get-Process -Name '7DaysToDieServer', '7DaysToDie' `
                -ErrorAction SilentlyContinue
        )
        if ($serverProcesses.Count -eq 0) {
            break
        }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $shutdownDeadline)

    $remainingProcesses = @(
        Get-Process -Name '7DaysToDieServer', '7DaysToDie' `
            -ErrorAction SilentlyContinue
    )
    if ($remainingProcesses.Count -gt 0) {
        $remainingProcesses | Stop-Process -Force
        Write-RestartAudit `
            -Event 'forced_process_stop' `
            -JobId $JobId `
            -Detail (($remainingProcesses.Id -join ','))
        Start-Sleep -Seconds 3
    }

    Start-Process -FilePath $StartShortcut
    Write-RestartAudit -Event 'start_shortcut_invoked' -JobId $JobId

    $startupDeadline = (Get-Date).AddSeconds(240)
    do {
        $processReady = $null -ne (
            Get-Process -Name '7DaysToDieServer', '7DaysToDie' `
                -ErrorAction SilentlyContinue |
                Select-Object -First 1
        )
        $telnetReady = Test-TcpPort `
            -HostName '127.0.0.1' `
            -Port 8081 `
            -TimeoutMilliseconds 1000
        $loginReady = Test-GameLoginReady
        if ($processReady -and $telnetReady -and $loginReady) {
            Write-RestartAudit -Event 'server_ready' -JobId $JobId
            return
        }
        Start-Sleep -Seconds 5
    } while ((Get-Date) -lt $startupDeadline)

    throw '起動後240秒以内にプロセス、Telnet、Steamログオンの正常性を確認できませんでした。'
}

if (-not (Test-Path -LiteralPath $TokenPath -PathType Leaf)) {
    throw "エージェントトークンが見つかりません: $TokenPath"
}

$agentToken = (Get-Content -LiteralPath $TokenPath -Raw).Trim()
if ($agentToken.Length -lt 32) {
    throw 'エージェントトークンが短すぎます。'
}
$agentHeaders = @{
    Accept = 'application/json'
    'X-Restart-Agent-Token' = $agentToken
}

Write-RestartAudit -Event 'agent_started'
$nextVersionPublish = Get-Date
$lastPublishedVersion = ''
$nextSchedulePublish = Get-Date
$lastPublishedSchedule = ''
$nextEntityPublish = Get-Date
$lastPublishedEntitySummary = ''
$nextPlayerSnapshotPublish = Get-Date
$lastPublishedPlayerSummary = ''
$nextServerStatusPublish = Get-Date
$lastPublishedServerStatus = ''
$nextBiomePublish = Get-Date
$lastPublishedBiomeHash = ''
$worldTraderEntities = @()
try {
    $worldTraderEntities = @(Get-GeneratedWorldTraderEntities)
    Write-RestartAudit `
        -Event 'map_traders_loaded' `
        -Detail "count=$($worldTraderEntities.Count)"
}
catch {
    Write-RestartAudit `
        -Event 'map_traders_read_error' `
        -Detail $_.Exception.Message
}

do {
    try {
        if ((Get-Date) -ge $nextVersionPublish) {
            try {
                $runtimeVersion = Get-GameServerVersion
                Publish-GameServerVersion `
                    -Headers $agentHeaders `
                    -Version $runtimeVersion
                if ($runtimeVersion -ne $lastPublishedVersion) {
                    Write-RestartAudit `
                        -Event 'server_version_published' `
                        -Detail $runtimeVersion
                    $lastPublishedVersion = $runtimeVersion
                }
                $nextVersionPublish = (Get-Date).AddSeconds(60)
            }
            catch {
                Write-RestartAudit `
                    -Event 'server_version_publish_error' `
                    -Detail $_.Exception.Message
                $nextVersionPublish = (Get-Date).AddSeconds(30)
            }
        }

        if ((Get-Date) -ge $nextSchedulePublish) {
            try {
                $runtimeSchedule = Get-GameSchedule
                Publish-GameSchedule `
                    -Headers $agentHeaders `
                    -Schedule $runtimeSchedule
                $scheduleSummary = (
                    '{0}/{1}min/freq{2}/range{3}' -f
                    $runtimeSchedule.mode,
                    $runtimeSchedule.dayNightLengthMinutes,
                    $runtimeSchedule.bloodMoonFrequencyDays,
                    $runtimeSchedule.bloodMoonRangeDays
                )
                if ($scheduleSummary -ne $lastPublishedSchedule) {
                    Write-RestartAudit `
                        -Event 'game_schedule_published' `
                        -Detail $scheduleSummary
                    $lastPublishedSchedule = $scheduleSummary
                }
                $nextSchedulePublish = (Get-Date).AddSeconds(60)
            }
            catch {
                Write-RestartAudit `
                    -Event 'game_schedule_publish_error' `
                    -Detail $_.Exception.Message
                $nextSchedulePublish = (Get-Date).AddSeconds(30)
            }
        }

        if ((Get-Date) -ge $nextEntityPublish) {
            try {
                $runtimeEntities = @(
                    Get-GameMapEntities `
                        -WorldTraderEntities $worldTraderEntities
                    Get-PrivateMapEntities
                )
                Publish-GameMapEntities `
                    -Headers $agentHeaders `
                    -Entities $runtimeEntities
                $entityKindCounts = @{}
                foreach ($entity in $runtimeEntities) {
                    $kind = [string]$entity['kind']
                    if (-not $entityKindCounts.ContainsKey($kind)) {
                        $entityKindCounts[$kind] = 0
                    }
                    $entityKindCounts[$kind]++
                }
                $entitySummary = (
                    $entityKindCounts.GetEnumerator() |
                        Sort-Object Name |
                        ForEach-Object {
                            '{0}:{1}' -f $_.Name, $_.Value
                        }
                ) -join ','
                if ($entitySummary -ne $lastPublishedEntitySummary) {
                    $publishedSummary = if ($entitySummary) {
                        $entitySummary
                    }
                    else {
                        'none'
                    }
                    Write-RestartAudit `
                        -Event 'map_entities_published' `
                        -Detail $publishedSummary
                    $lastPublishedEntitySummary = $entitySummary
                }
                $nextEntityPublish = (Get-Date).AddSeconds(
                    $MapEntityPublishIntervalSeconds
                )
            }
            catch {
                Write-RestartAudit `
                    -Event 'map_entities_publish_error' `
                    -Detail $_.Exception.Message
                $nextEntityPublish = (Get-Date).AddSeconds(30)
            }
        }

        if ((Get-Date) -ge $nextServerStatusPublish) {
            try {
                $serverStatus = Get-GameServerStatus
                Publish-GameServerStatus `
                    -Headers $agentHeaders `
                    -Status $serverStatus
                $statusSummary = (
                    'uptime={0:F1}m,fps={1:F2},rss={2:F1}MB,players={3}' -f
                    $serverStatus.uptimeMinutes,
                    $serverStatus.fps,
                    $serverStatus.rssMb,
                    $serverStatus.players
                )
                if ($statusSummary -ne $lastPublishedServerStatus) {
                    Write-RestartAudit `
                        -Event 'server_status_published' `
                        -Detail $statusSummary
                    $lastPublishedServerStatus = $statusSummary
                }
                $nextServerStatusPublish = (Get-Date).AddSeconds(30)
            }
            catch {
                Write-RestartAudit `
                    -Event 'server_status_publish_error' `
                    -Detail $_.Exception.Message
                $nextServerStatusPublish = (Get-Date).AddSeconds(30)
            }
        }

        if ((Get-Date) -ge $nextBiomePublish) {
            try {
                $biomePath = Get-BiomeImagePath
                $biomeHash = (
                    Get-FileHash -LiteralPath $biomePath -Algorithm SHA256
                ).Hash
                if ($biomeHash -ne $lastPublishedBiomeHash) {
                    Publish-BiomeImage `
                        -Headers $agentHeaders `
                        -Path $biomePath
                    Write-RestartAudit `
                        -Event 'biome_image_published' `
                        -Detail "sha256=$biomeHash"
                    $lastPublishedBiomeHash = $biomeHash
                }
                $nextBiomePublish = (Get-Date).AddHours(1)
            }
            catch {
                Write-RestartAudit `
                    -Event 'biome_image_publish_error' `
                    -Detail $_.Exception.Message
                $nextBiomePublish = (Get-Date).AddMinutes(5)
            }
        }

        if ((Get-Date) -ge $nextPlayerSnapshotPublish) {
            try {
                $playerProfiles = @(Get-PlayerProfiles)
                $onlinePlayers = @(Get-OnlinePlayerStats)
                Publish-PlayerSnapshot `
                    -Headers $agentHeaders `
                    -Profiles $playerProfiles `
                    -OnlinePlayers $onlinePlayers
                $playerSummary = (
                    'profiles={0},online={1},detailed={2}' -f
                    $playerProfiles.Count,
                    $onlinePlayers.Count,
                    [bool](
                        $onlinePlayers.Count -gt 0 -and
                        $null -ne $onlinePlayers[0].gameStage
                    )
                )
                if ($playerSummary -ne $lastPublishedPlayerSummary) {
                    Write-RestartAudit `
                        -Event 'player_snapshot_published' `
                        -Detail $playerSummary
                    $lastPublishedPlayerSummary = $playerSummary
                }
                $nextPlayerSnapshotPublish = (Get-Date).AddSeconds(
                    $PlayerSnapshotPublishIntervalSeconds
                )
            }
            catch {
                Write-RestartAudit `
                    -Event 'player_snapshot_publish_error' `
                    -Detail $_.Exception.Message
                $nextPlayerSnapshotPublish = (Get-Date).AddSeconds(30)
            }
        }

        if ($EnableRestart) {
            $action = Get-AgentAction -Headers $agentHeaders
            if ($null -ne $action) {
            $actionName = [string]$action.action
            $jobId = [string]$action.jobId
            if ($actionName -eq 'restart') {
                if ($DryRun) {
                    Write-RestartAudit `
                        -Event 'dry_run_restart_claimed' `
                        -JobId $jobId
                }
                else {
                    try {
                        Invoke-GameRestart -JobId $jobId
                        Complete-AgentAction `
                            -Headers $agentHeaders `
                            -JobId $jobId `
                            -Success $true `
                            -Result 'server_ready'
                    }
                    catch {
                        $failure = $_.Exception.Message
                        Write-RestartAudit `
                            -Event 'restart_failed' `
                            -JobId $jobId `
                            -Detail $failure
                        Complete-AgentAction `
                            -Headers $agentHeaders `
                            -JobId $jobId `
                            -Success $false `
                            -Result $failure
                    }
                }
            }
            else {
                Invoke-Announcement -Action $actionName -JobId $jobId
            }
            }
        }
    }
    catch {
        Write-RestartAudit `
            -Event 'poll_error' `
            -Detail $_.Exception.Message
    }

    if (-not $Once) {
        Start-Sleep -Seconds 10
    }
} while (-not $Once)
