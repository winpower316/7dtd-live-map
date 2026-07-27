using System;
using System.Collections.Generic;
using System.IO;
using HarmonyLib;
using Newtonsoft.Json;
using UnityEngine;

namespace LiveMapServerTools;

public sealed class ModApi : IModApi
{
    public void InitMod(Mod _modInstance)
    {
        SharedWaypointStore.Initialize(_modInstance.Path);
        new Harmony("org.7dtdlivemap.servertools").PatchAll();
        Debug.Log("[LiveMapServerTools] shared waypoint capture enabled");
    }
}

[HarmonyPatch(
    typeof(GameManager),
    nameof(GameManager.WaypointInviteServer)
)]
public static class WaypointInviteServerPatch
{
    public static void Prefix(
        Waypoint _waypoint,
        EnumWaypointInviteMode _inviteMode,
        int _inviterEntityId
    )
    {
        if (
            _inviteMode != EnumWaypointInviteMode.Everyone
            || !SingletonMonoBehaviour<ConnectionManager>.Instance.IsServer
            || _waypoint == null
        )
        {
            return;
        }

        EntityPlayer player = (
            GameManager.Instance.World.GetEntity(_inviterEntityId)
            as EntityPlayer
        );
        if (player == null)
        {
            return;
        }

        SharedWaypointStore.Record(
            player.EntityName,
            _waypoint.name?.Text,
            _waypoint.icon,
            _waypoint.pos
        );
    }
}

public static class SharedWaypointStore
{
    private const int DefaultMaximumEntries = 200;
    private const int HighestMaximumEntries = 5000;
    private static readonly object SyncRoot = new object();
    private static string storePath;
    private static int maximumEntries = DefaultMaximumEntries;

    public static void Initialize(string modPath)
    {
        lock (SyncRoot)
        {
            storePath = Path.Combine(modPath, "shared-waypoints.json");
            maximumEntries = LoadMaximumEntries(modPath);
            if (!File.Exists(storePath))
            {
                File.WriteAllText(storePath, "[]");
            }
            Debug.Log(
                "[LiveMapServerTools] sharedWaypointMaximumEntries="
                + maximumEntries
            );
        }
    }

    public static void Record(
        string owner,
        string name,
        string icon,
        Vector3i position
    )
    {
        lock (SyncRoot)
        {
            if (string.IsNullOrWhiteSpace(storePath))
            {
                return;
            }

            List<SharedWaypointEntry> entries;
            try
            {
                entries = JsonConvert.DeserializeObject<
                    List<SharedWaypointEntry>
                >(File.ReadAllText(storePath)) ?? new List<SharedWaypointEntry>();
            }
            catch (Exception exception)
            {
                Debug.LogError(
                    "[LiveMapServerTools] cannot read shared waypoints: "
                    + exception.Message
                );
                return;
            }

            string normalizedOwner = Normalize(owner, "UNKNOWN", 64);
            string normalizedName = Normalize(name, "共有地点", 100);
            entries.RemoveAll(entry =>
                entry.owner == normalizedOwner
                && entry.name == normalizedName
                && entry.position != null
                && entry.position.x == position.x
                && entry.position.z == position.z
            );
            entries.Add(new SharedWaypointEntry
            {
                owner = normalizedOwner,
                name = normalizedName,
                icon = Normalize(icon, "map_marker", 64),
                sharedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
                position = new SharedWaypointPosition
                {
                    x = position.x,
                    y = position.y,
                    z = position.z,
                },
            });
            if (entries.Count > maximumEntries)
            {
                entries.RemoveRange(0, entries.Count - maximumEntries);
            }

            string temporaryPath = storePath + ".new";
            File.WriteAllText(
                temporaryPath,
                JsonConvert.SerializeObject(entries)
            );
            if (File.Exists(storePath))
            {
                File.Replace(temporaryPath, storePath, null);
            }
            else
            {
                File.Move(temporaryPath, storePath);
            }
            Debug.Log(
                "[LiveMapServerTools] shared waypoint captured: "
                + normalizedOwner
                + " / "
                + normalizedName
            );
        }
    }

    private static string Normalize(
        string value,
        string fallback,
        int maximumLength
    )
    {
        string normalized = string.IsNullOrWhiteSpace(value)
            ? fallback
            : value.Trim();
        return normalized.Length <= maximumLength
            ? normalized
            : normalized.Substring(0, maximumLength);
    }

    private static int LoadMaximumEntries(string modPath)
    {
        string configPath = Path.Combine(modPath, "config.json");
        if (!File.Exists(configPath))
        {
            return DefaultMaximumEntries;
        }

        try
        {
            LiveMapServerToolsConfig config = JsonConvert.DeserializeObject<
                LiveMapServerToolsConfig
            >(File.ReadAllText(configPath));
            int configuredValue = config?.sharedWaypointMaximumEntries
                ?? DefaultMaximumEntries;
            if (
                configuredValue < 1
                || configuredValue > HighestMaximumEntries
            )
            {
                throw new InvalidDataException(
                    "sharedWaypointMaximumEntries must be between 1 and "
                    + HighestMaximumEntries
                );
            }
            return configuredValue;
        }
        catch (Exception exception)
        {
            Debug.LogError(
                "[LiveMapServerTools] cannot read config.json; using default: "
                + exception.Message
            );
            return DefaultMaximumEntries;
        }
    }

    private sealed class LiveMapServerToolsConfig
    {
        public int? sharedWaypointMaximumEntries { get; set; }
    }

    private sealed class SharedWaypointEntry
    {
        public string owner { get; set; }
        public string name { get; set; }
        public string icon { get; set; }
        public long sharedAt { get; set; }
        public SharedWaypointPosition position { get; set; }
    }

    private sealed class SharedWaypointPosition
    {
        public int x { get; set; }
        public int y { get; set; }
        public int z { get; set; }
    }
}
