using System.Collections.Generic;
using System.Globalization;
using Newtonsoft.Json;

namespace LiveMapServerTools;

public sealed class ConsoleCmdWebServerStats : ConsoleCmdAbstract
{
    public override string[] getCommands()
    {
        return new[] { "webserverstats" };
    }

    public override string getDescription()
    {
        return "Webマップ用に読み取り専用のサーバー統計を出力します";
    }

    public override void Execute(
        List<string> _params,
        CommandSenderInfo _senderInfo
    )
    {
        ConsoleCmdMem.FillStats(false, GameManager.Instance);
        string[] stats = ConsoleCmdMem.Stats;
        var publicStatus = new
        {
            uptimeMinutes = ParseDouble(stats[0]),
            fps = ParseDouble(stats[1]),
            heapMb = ParseDouble(stats[2]),
            maxMemoryMb = ParseDouble(stats[3]),
            chunks = ParseInt(stats[4]),
            players = ParseInt(stats[6]),
            zombies = ParseInt(stats[7]),
            entities = ParseInt(stats[8]),
            rssMb = ParseDouble(stats[11]),
        };
        SingletonMonoBehaviour<SdtdConsole>.Instance.Output(
            "LIVEMAP_SERVER_STATUS "
            + JsonConvert.SerializeObject(publicStatus)
        );
        SingletonMonoBehaviour<SdtdConsole>.Instance.Output(
            "LIVEMAP_SERVER_STATUS_END"
        );
    }

    private static double ParseDouble(string value)
    {
        return double.Parse(value, CultureInfo.InvariantCulture);
    }

    private static int ParseInt(string value)
    {
        return int.Parse(value, CultureInfo.InvariantCulture);
    }
}
