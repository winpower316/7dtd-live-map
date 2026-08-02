using System;
using System.Collections.Generic;
using System.IO;
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
        var playerNamesByEntityId = new Dictionary<int, string>();
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

                if (playerEntry.Value.EntityId >= 0)
                {
                    playerNamesByEntityId[playerEntry.Value.EntityId] = owner;
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

            List<EntityCreationData> vehicles =
                VehicleManager.Instance?.GetVehiclesECDList();
            AddManagedOwners(owners, playerNamesByEntityId, vehicles);
            AddSavedVehicleOwners(owners, players, vehicles);
            AddManagedOwners(
                owners,
                playerNamesByEntityId,
                DroneManager.Instance?.GetAllDronesECD()
            );
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

    private static void AddSavedVehicleOwners(
        Dictionary<int, string> owners,
        PersistentPlayerList players,
        List<EntityCreationData> vehicles
    )
    {
        if (vehicles == null)
        {
            return;
        }

        foreach (EntityCreationData vehicle in vehicles)
        {
            if (
                vehicle == null
                || vehicle.id < 0
            )
            {
                continue;
            }

            PlatformUserIdentifierAbs ownerId =
                TryReadSavedVehicleOwner(vehicle);
            string owner = players
                .GetPlayerData(ownerId)
                ?.PlayerName
                ?.SafeDisplayName;
            if (!string.IsNullOrWhiteSpace(owner))
            {
                owners[vehicle.id] = owner;
            }
        }
    }

    private static PlatformUserIdentifierAbs TryReadSavedVehicleOwner(
        EntityCreationData vehicle
    )
    {
        try
        {
            using var stream = new MemoryStream(
                vehicle.entityData.ToArray(),
                writable: false
            );
            using var reader = new BinaryReader(stream);

            EnumSpawnerSource spawnerSource =
                (EnumSpawnerSource)reader.ReadByte();
            if (spawnerSource == EnumSpawnerSource.Biome)
            {
                reader.ReadInt32();
                reader.ReadInt64();
            }

            if (vehicle.readFileVersion >= 15)
            {
                reader.ReadUInt64();
            }
            if (vehicle.readFileVersion > 24)
            {
                reader.ReadInt32();
            }
            if (vehicle.readFileVersion >= 36)
            {
                reader.ReadSingle();
            }
            if (vehicle.readFileVersion < 26)
            {
                return null;
            }

            ushort syncFlags = reader.ReadUInt16();
            reader.ReadByte();
            if ((syncFlags & 0x8001) != 0)
            {
                return null;
            }
            if ((syncFlags & 0x4000) != 0)
            {
                reader.ReadBoolean();
            }
            if ((syncFlags & 2) == 0)
            {
                return null;
            }

            reader.ReadByte();
            return PlatformUserIdentifierAbs.FromStream(reader);
        }
        catch
        {
            return null;
        }
    }

    private static void AddManagedOwners(
        Dictionary<int, string> owners,
        Dictionary<int, string> playerNamesByEntityId,
        List<EntityCreationData> entities
    )
    {
        if (entities == null)
        {
            return;
        }

        foreach (EntityCreationData entity in entities)
        {
            if (
                entity == null
                || entity.id < 0
                || entity.belongsPlayerId < 0
                || !playerNamesByEntityId.TryGetValue(
                    entity.belongsPlayerId,
                    out string owner
                )
            )
            {
                continue;
            }

            owners[entity.id] = owner;
        }
    }

    private sealed class PublicEntityOwner
    {
        public string entityId { get; set; }

        public string owner { get; set; }
    }
}
