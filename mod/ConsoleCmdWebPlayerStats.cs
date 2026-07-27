using System.Collections.Generic;
using Newtonsoft.Json;

namespace LiveMapServerTools;

public sealed class ConsoleCmdWebPlayerStats : ConsoleCmdAbstract
{
    public override string[] getCommands()
    {
        return new[] { "webplayerstats" };
    }

    public override string getDescription()
    {
        return "Webマップ用にオンラインプレイヤーの公開可能な状態を出力します";
    }

    public override void Execute(
        List<string> _params,
        CommandSenderInfo _senderInfo
    )
    {
        foreach (EntityPlayer player in GameManager.Instance.World.Players.list)
        {
            var position = player.GetPosition();
            var publicPlayer = new
            {
                name = player.EntityName,
                level = player.Progression.GetLevel(),
                position = new
                {
                    x = (double)position.x,
                    y = (double)position.y,
                    z = (double)position.z,
                },
                health = player.Health,
                maxHealth = player.GetMaxHealth(),
                ping = player.pingToServer,
                gameStage = (int)player.gameStage,
            };
            SingletonMonoBehaviour<SdtdConsole>.Instance.Output(
                "LIVEMAP_PLAYER_STATS "
                + JsonConvert.SerializeObject(publicPlayer)
            );
        }
        SingletonMonoBehaviour<SdtdConsole>.Instance.Output(
            "LIVEMAP_PLAYER_STATS_END"
        );
    }
}
