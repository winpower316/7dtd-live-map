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
        SharedWaypointStore.Initialize(
            Path.Combine(_modInstance.Path, "shared-waypoints.json")
        );
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
    private const int MaximumEntries = 200;
    private static readonly object SyncRoot = new object();
    private static string storePath;

    public static void Initialize(string path)
    {
        lock (SyncRoot)
        {
            storePath = path;
            if (!File.Exists(storePath))
            {
                File.WriteAllText(storePath, "[]");
            }
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
            if (entries.Count > MaximumEntries)
            {
                entries.RemoveRange(0, entries.Count - MaximumEntries);
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
