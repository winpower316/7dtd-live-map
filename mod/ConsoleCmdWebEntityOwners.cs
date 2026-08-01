using System;
using System.Collections.Generic;
using Newtonsoft.Json;

namespace LiveMapServerTools;

public sealed class ConsoleCmdWebEntityOwners : ConsoleCmdAbstract
{
    private static readonly TimeSpan CacheDuration = TimeSpan.FromMinutes(1);
    private static readonly List<PublicEntityOwner> CachedOwners = new();
    private static DateTime cacheExpiresAtUtc = DateTime.MinValue;

    public override string[] getCommands()
    {
        return new[] { "webentityowners" };
    }

    public override string getDescription()
    {
        return "Webマップ用に所有エンティティとプレイヤー名を出力します";
    }

    public override void Execute(
        List<string> _params,
        CommandSenderInfo _senderInfo
    )
    {
        RefreshCacheIfNeeded();
        foreach (PublicEntityOwner publicOwner in CachedOwners)
        {
            SingletonMonoBehaviour<SdtdConsole>.Instance.Output(
                "LIVEMAP_ENTITY_OWNER "
                + JsonConvert.SerializeObject(publicOwner)
            );
        }

        SingletonMonoBehaviour<SdtdConsole>.Instance.Output(
            "LIVEMAP_ENTITY_OWNER_END"
        );
    }

    private static void RefreshCacheIfNeeded()
    {
        DateTime now = DateTime.UtcNow;
        if (now < cacheExpiresAtUtc)
        {
            return;
        }

        var owners = new Dictionary<int, string>();
        PersistentPlayerList players =
            GameManager.Instance.GetPersistentPlayerList();
        if (players != null)
        {
            foreach (
                KeyValuePair<PlatformUserIdentifierAbs, PersistentPlayerData>
                    playerEntry in players.Players
            )
            {
                string owner = playerEntry.Value?.PlayerName?.SafeDisplayName;
                if (string.IsNullOrWhiteSpace(owner))
                {
                    continue;
                }

                var playerFile = new PlayerDataFile();
                playerFile.Load(
                    GameIO.GetPlayerDataDir(),
                    playerEntry.Key.CombinedString
                );
                if (!playerFile.bLoaded)
                {
                    continue;
                }

                foreach (OwnedEntityData ownedEntity in playerFile.ownedEntities)
                {
                    owners[ownedEntity.Id] = owner;
                }
            }
        }

        CachedOwners.Clear();
        foreach (KeyValuePair<int, string> owner in owners)
        {
            CachedOwners.Add(
                new PublicEntityOwner
                {
                    entityId = owner.Key.ToString(),
                    owner = owner.Value,
                }
            );
        }
        CachedOwners.Sort(
            (left, right) => string.CompareOrdinal(
                left.entityId,
                right.entityId
            )
        );
        cacheExpiresAtUtc = now.Add(CacheDuration);
    }

    private sealed class PublicEntityOwner
    {
        public string entityId { get; set; }

        public string owner { get; set; }
    }
}
