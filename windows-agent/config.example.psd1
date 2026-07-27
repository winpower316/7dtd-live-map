@{
    ApiBase = 'http://DOCKER_HOST_LAN_IP:18081'
    TokenPath = 'C:\ProgramData\7dtd-web-restart\agent.token'
    StartShortcut = 'C:\7dtd-server\startdedicated.bat.lnk'
    AuditPath = 'C:\ProgramData\7dtd-web-map\agent-audit.jsonl'
    GameRoot = 'C:\Program Files (x86)\Steam\steamapps\common\7 Days To Die'
    TelnetHost = '127.0.0.1'
    TelnetPort = 8081
    ScheduleMode = 'custom'
    DayNightLengthMinutes = 0
    MaintenanceTaskName = ''
    MapEntityPublishIntervalSeconds = 10
    PlayerSnapshotPublishIntervalSeconds = 10
    VersionPublishIntervalSeconds = 60
    SchedulePublishIntervalSeconds = 60
    ServerStatusPublishIntervalSeconds = 30
    BiomePublishIntervalMinutes = 60
    RetryIntervalSeconds = 30
    PollIntervalSeconds = 10
    RequestTimeoutSeconds = 10
    BiomeUploadTimeoutSeconds = 15
    ShutdownTimeoutSeconds = 90
    StartupTimeoutSeconds = 240
    EnableRestart = $false
    Once = $false
    DryRun = $false
}
