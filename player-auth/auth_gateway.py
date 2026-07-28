#!/usr/bin/env python3
"""Webマップ用の認証、バージョン表示、再起動予約ゲートウェイ。"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import ipaddress
import json
import math
import os
import re
import secrets
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


def _env_int(
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exception:
        raise RuntimeError(f"{name} must be an integer") from exception
    if value < minimum or value > maximum:
        raise RuntimeError(
            f"{name} must be between {minimum} and {maximum}"
        )
    return value


LISTEN_HOST = os.getenv("LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = _env_int("LISTEN_PORT", 8080, 1, 65535)
PASSWORD_HASH_FILE = Path(
    os.getenv("PASSWORD_HASH_FILE", "/run/secrets/player_map_password_hash")
)
AGENT_TOKEN_FILE = Path(
    os.getenv("AGENT_TOKEN_FILE", "/run/secrets/restart_agent_token")
)
PLAYER_API_TOKEN_FILE = Path(
    os.getenv("PLAYER_API_TOKEN_FILE", "/run/secrets/player_api_token")
)
ACTIVITY_API_TOKEN_FILE = Path(
    os.getenv("ACTIVITY_API_TOKEN_FILE", "/run/secrets/activity_api_token")
)
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", "/data/auth-state.sqlite3"))
PLAYER_UPSTREAM_URL = os.getenv(
    "PLAYER_UPSTREAM_URL",
    os.getenv("UPSTREAM_URL", "http://7dtd-server:8080/api/player"),
)
PLAYER_API_TOKEN_NAME = os.getenv(
    "PLAYER_API_TOKEN_NAME",
    "map-player-reader",
)
ACTIVITY_UPSTREAM_URL = os.getenv(
    "ACTIVITY_UPSTREAM_URL",
    "http://7dtd-server:8080/api/log?count=-500",
)
ACTIVITY_API_TOKEN_NAME = os.getenv(
    "ACTIVITY_API_TOKEN_NAME",
    "map-activity-reader",
)
ACTIVITY_POLL_SECONDS = _env_int(
    "ACTIVITY_POLL_SECONDS", 10, 1, 3600
)
ACTIVITY_RETENTION_SECONDS = _env_int(
    "ACTIVITY_RETENTION_SECONDS", 604800, 60, 31536000
)
ACTIVITY_MAX_EVENTS = _env_int(
    "ACTIVITY_MAX_EVENTS", 2000, 1, 100000
)
ACTIVITY_PUBLIC_LIMIT = _env_int(
    "ACTIVITY_PUBLIC_LIMIT", 200, 1, 10000
)
MAX_FAILURES = _env_int("MAX_FAILURES", 5, 1, 100)
FAILURE_WINDOW_SECONDS = _env_int(
    "FAILURE_WINDOW_SECONDS", 3600, 1, 604800
)
BLOCK_SECONDS = _env_int("BLOCK_SECONDS", 86400, 1, 31536000)
RESTART_ENABLED = os.getenv(
    "RESTART_ENABLED",
    "false",
).strip().lower() in {"1", "true", "yes", "on"}
RESTART_DELAY_SECONDS = _env_int(
    "RESTART_DELAY_SECONDS", 300, 10, 86400
)
RESTART_COOLDOWN_SECONDS = _env_int(
    "RESTART_COOLDOWN_SECONDS", 1800, 0, 604800
)
RESTART_FAILURE_COOLDOWN_SECONDS = _env_int(
    "RESTART_FAILURE_COOLDOWN_SECONDS", 300, 0, 604800
)
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "map")
PBKDF2_ITERATIONS = _env_int(
    "PBKDF2_ITERATIONS", 600000, 100000, 10000000
)
MAX_REQUEST_BODY_BYTES = _env_int(
    "MAX_REQUEST_BODY_BYTES", 262144, 1024, 16777216
)
MAX_MAP_ENTITIES = _env_int("MAX_MAP_ENTITIES", 500, 1, 5000)
MAX_PLAYER_PROFILES = _env_int(
    "MAX_PLAYER_PROFILES", 100, 1, 1000
)
SERVER_VERSION_PATTERN = re.compile(
    r"^V \d+\.\d+\.\d+ \(b\d+\)$"
)
GAME_MODES = frozenset(("weekday", "holiday", "custom"))
MAP_ENTITY_LABELS = {
    "supply": "補給物資",
    "drone": "ドローン",
    "trader_joel": "トレーダー・ジョエル",
    "trader_jen": "トレーダー・ジェン",
    "trader_bob": "トレーダー・ボブ",
    "trader_hugh": "トレーダー・ヒュー",
    "trader_rekt": "トレーダー・レクト",
    "bicycle": "自転車",
    "minibike": "ミニバイク",
    "motorcycle": "オートバイ",
    "four_by_four": "4x4トラック",
    "gyrocopter": "ジャイロコプター",
    "vehicle": "車両",
    "bedroll": "寝袋",
    "quest": "クエスト地点",
    "shared_waypoint": "共有地点",
}
CHAT_PATTERN = re.compile(
    r"^Chat \(from '(.+)', entity id '[^']+', to '([^']+)'\): (.*)$"
)
PLAYER_EVENT_PATTERN = re.compile(
    r"^GMSG: Player '(.+)' (joined the game|left the game|died)$"
)
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True)
class AuthDecision:
    status: str
    remaining_attempts: int = 0
    retry_after_seconds: int = 0


@dataclass(frozen=True)
class PasswordHash:
    iterations: int
    salt: bytes
    digest: bytes


class AuthStore:
    """IPごとの認証失敗とブロック期限をSQLiteへ保存する。"""

    def __init__(
        self,
        database_path: Path,
        max_failures: int = MAX_FAILURES,
        failure_window_seconds: int = FAILURE_WINDOW_SECONDS,
        block_seconds: int = BLOCK_SECONDS,
    ) -> None:
        self.database_path = database_path
        self.max_failures = max_failures
        self.failure_window_seconds = failure_window_seconds
        self.block_seconds = block_seconds
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_state (
                    client_ip TEXT PRIMARY KEY,
                    failure_count INTEGER NOT NULL,
                    first_failure REAL NOT NULL,
                    last_failure REAL NOT NULL,
                    blocked_until REAL NOT NULL
                )
                """
            )

    def evaluate(
        self,
        client_ip: str,
        credentials_valid: bool,
        now: float | None = None,
    ) -> AuthDecision:
        current_time = time.time() if now is None else now

        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT failure_count, first_failure, blocked_until
                FROM auth_state
                WHERE client_ip = ?
                """,
                (client_ip,),
            ).fetchone()

            if row and row[2] > current_time:
                retry_after = max(1, math.ceil(row[2] - current_time))
                return AuthDecision("blocked", retry_after_seconds=retry_after)

            if credentials_valid:
                connection.execute(
                    "DELETE FROM auth_state WHERE client_ip = ?",
                    (client_ip,),
                )
                return AuthDecision("allowed")

            if (
                row
                and row[2] <= current_time
                and current_time - row[1] <= self.failure_window_seconds
            ):
                failure_count = row[0] + 1
                first_failure = row[1]
            else:
                failure_count = 1
                first_failure = current_time

            if failure_count >= self.max_failures:
                blocked_until = current_time + self.block_seconds
                connection.execute(
                    """
                    INSERT INTO auth_state (
                        client_ip, failure_count, first_failure,
                        last_failure, blocked_until
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(client_ip) DO UPDATE SET
                        failure_count = excluded.failure_count,
                        first_failure = excluded.first_failure,
                        last_failure = excluded.last_failure,
                        blocked_until = excluded.blocked_until
                    """,
                    (
                        client_ip,
                        failure_count,
                        first_failure,
                        current_time,
                        blocked_until,
                    ),
                )
                return AuthDecision(
                    "blocked",
                    retry_after_seconds=self.block_seconds,
                )

            connection.execute(
                """
                INSERT INTO auth_state (
                    client_ip, failure_count, first_failure,
                    last_failure, blocked_until
                )
                VALUES (?, ?, ?, ?, 0)
                ON CONFLICT(client_ip) DO UPDATE SET
                    failure_count = excluded.failure_count,
                    first_failure = excluded.first_failure,
                    last_failure = excluded.last_failure,
                    blocked_until = 0
                """,
                (client_ip, failure_count, first_failure, current_time),
            )
            return AuthDecision(
                "denied",
                remaining_attempts=self.max_failures - failure_count,
            )


class ActivityStore:
    """公開可能なゲームイベントだけをSQLiteへ保存する。"""

    def __init__(
        self,
        database_path: Path,
        retention_seconds: int = ACTIVITY_RETENTION_SECONDS,
        max_events: int = ACTIVITY_MAX_EVENTS,
    ) -> None:
        self.database_path = database_path
        self.retention_seconds = retention_seconds
        self.max_events = max_events
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS activity_events (
                    event_key TEXT PRIMARY KEY,
                    occurred_at TEXT NOT NULL,
                    occurred_epoch REAL NOT NULL,
                    event_type TEXT NOT NULL,
                    player TEXT NOT NULL,
                    message TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    activity_events_occurred_epoch
                ON activity_events (occurred_epoch DESC)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS activity_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

    def ingest(
        self,
        events: list[dict[str, object]],
        now: float | None = None,
    ) -> int:
        current_time = time.time() if now is None else now
        inserted = 0
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            for event in events:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO activity_events (
                        event_key,
                        occurred_at,
                        occurred_epoch,
                        event_type,
                        player,
                        message
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event["eventKey"],
                        event["occurredAt"],
                        event["occurredEpoch"],
                        event["type"],
                        event["player"],
                        event["message"],
                    ),
                )
                inserted += cursor.rowcount
            connection.execute(
                """
                DELETE FROM activity_events
                WHERE occurred_epoch < ?
                """,
                (current_time - self.retention_seconds,),
            )
            connection.execute(
                """
                DELETE FROM activity_events
                WHERE event_key NOT IN (
                    SELECT event_key
                    FROM activity_events
                    ORDER BY occurred_epoch DESC, event_key DESC
                    LIMIT ?
                )
                """,
                (self.max_events,),
            )
        return inserted

    def mark_collection(
        self,
        success: bool,
        now: float | None = None,
    ) -> None:
        current_time = time.time() if now is None else now
        key = (
            "activity_last_success"
            if success
            else "activity_last_failure"
        )
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO activity_meta (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, str(current_time)),
            )

    def recent(self, limit: int = ACTIVITY_PUBLIC_LIMIT) -> dict[str, object]:
        safe_limit = max(1, min(limit, ACTIVITY_PUBLIC_LIMIT))
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT
                    occurred_at,
                    event_type,
                    player,
                    message
                FROM activity_events
                ORDER BY occurred_epoch DESC, event_key DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
            meta_rows = connection.execute(
                """
                SELECT key, value
                FROM activity_meta
                WHERE key IN (
                    'activity_last_success',
                    'activity_last_failure'
                )
                """
            ).fetchall()
        meta = {row["key"]: float(row["value"]) for row in meta_rows}
        last_success = meta.get("activity_last_success")
        last_failure = meta.get("activity_last_failure")
        return {
            "events": [
                {
                    "occurredAt": row["occurred_at"],
                    "type": row["event_type"],
                    "player": row["player"],
                    "message": row["message"],
                }
                for row in rows
            ],
            "lastCollectedAt": last_success,
            "collectorHealthy": (
                last_success is not None
                and (
                    last_failure is None
                    or last_success >= last_failure
                )
            ),
        }


class MapEntityStore:
    """認証済み地図へ公開する物資・ドローン・車両の最新位置を保存する。"""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS map_entities (
                    entity_key TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL,
                    entity_kind TEXT NOT NULL,
                    position_x REAL NOT NULL,
                    position_y REAL NOT NULL,
                    position_z REAL NOT NULL,
                    observed_at REAL NOT NULL,
                    public_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS map_entity_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(map_entities)"
                ).fetchall()
            }
            if "public_json" not in columns:
                connection.execute(
                    """
                    ALTER TABLE map_entities
                    ADD COLUMN public_json TEXT NOT NULL DEFAULT '{}'
                    """
                )

    def publish(
        self,
        entities: object,
        now: float | None = None,
    ) -> dict[str, object]:
        validated = validate_map_entities(entities)
        observed_at = time.time() if now is None else now
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM map_entities")
            connection.executemany(
                """
                INSERT INTO map_entities (
                    entity_key,
                    entity_id,
                    entity_kind,
                    position_x,
                    position_y,
                    position_z,
                    observed_at,
                    public_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        f"{entity['kind']}:{entity['entityId']}",
                        entity["entityId"],
                        entity["kind"],
                        entity["position"]["x"],
                        entity["position"]["y"],
                        entity["position"]["z"],
                        observed_at,
                        json.dumps(
                            {
                                key: entity[key]
                                for key in (
                                    "label",
                                    "owner",
                                    "detail",
                                    "questCode",
                                )
                                if key in entity
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    )
                    for entity in validated
                ),
            )
            connection.execute(
                """
                INSERT INTO map_entity_meta (key, value)
                VALUES ('last_collected_at', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(observed_at),),
            )
        return {
            "entities": validated,
            "lastCollectedAt": observed_at,
        }

    def current(self) -> dict[str, object] | None:
        with closing(self._connect()) as connection:
            meta = connection.execute(
                """
                SELECT value
                FROM map_entity_meta
                WHERE key = 'last_collected_at'
                """
            ).fetchone()
            if meta is None:
                return None
            rows = connection.execute(
                """
                SELECT
                    entity_id,
                    entity_kind,
                    position_x,
                    position_y,
                    position_z,
                    observed_at,
                    public_json
                FROM map_entities
                ORDER BY entity_kind, entity_id
                """
            ).fetchall()
        return {
            "entities": [
                {
                    "entityId": row["entity_id"],
                    "kind": row["entity_kind"],
                    "label": MAP_ENTITY_LABELS[row["entity_kind"]],
                    "position": {
                        "x": row["position_x"],
                        "y": row["position_y"],
                        "z": row["position_z"],
                    },
                    **json.loads(row["public_json"]),
                }
                for row in rows
            ],
            "lastCollectedAt": float(meta["value"]),
        }


class PlayerStore:
    """プレイヤーの公開可能なプロフィールと最新オンライン状態を保存する。"""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS player_roster (
                    name TEXT PRIMARY KEY,
                    level INTEGER,
                    profile_saved_at REAL,
                    position_x REAL,
                    position_y REAL,
                    position_z REAL,
                    last_position_at REAL,
                    online INTEGER NOT NULL DEFAULT 0,
                    health INTEGER,
                    max_health INTEGER,
                    ping INTEGER,
                    game_stage INTEGER
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS player_roster_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

    def publish(
        self,
        profiles: object,
        online_players: object,
        now: float | None = None,
    ) -> dict[str, object]:
        validated_profiles = validate_player_profiles(profiles)
        validated_online = validate_online_players(online_players)
        observed_at = time.time() if now is None else now

        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE player_roster
                SET
                    online = 0,
                    health = NULL,
                    max_health = NULL,
                    ping = NULL,
                    game_stage = NULL
                """
            )
            for profile in validated_profiles:
                connection.execute(
                    """
                    INSERT INTO player_roster (
                        name,
                        level,
                        profile_saved_at
                    )
                    VALUES (?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        level = excluded.level,
                        profile_saved_at = excluded.profile_saved_at
                    """,
                    (
                        profile["name"],
                        profile["level"],
                        profile["profileSavedAt"],
                    ),
                )
            for player in validated_online:
                position = player["position"]
                connection.execute(
                    """
                    INSERT INTO player_roster (
                        name,
                        level,
                        profile_saved_at,
                        position_x,
                        position_y,
                        position_z,
                        last_position_at,
                        online,
                        health,
                        max_health,
                        ping,
                        game_stage
                    )
                    VALUES (?, ?, NULL, ?, ?, ?, ?, 1, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        level = COALESCE(excluded.level, player_roster.level),
                        position_x = excluded.position_x,
                        position_y = excluded.position_y,
                        position_z = excluded.position_z,
                        last_position_at = excluded.last_position_at,
                        online = 1,
                        health = excluded.health,
                        max_health = excluded.max_health,
                        ping = excluded.ping,
                        game_stage = excluded.game_stage
                    """,
                    (
                        player["name"],
                        player["level"],
                        position["x"],
                        position["y"],
                        position["z"],
                        observed_at,
                        player["health"],
                        player["maxHealth"],
                        player["ping"],
                        player["gameStage"],
                    ),
                )
            online_names = tuple(player["name"] for player in validated_online)
            if online_names:
                placeholders = ", ".join("?" for _ in online_names)
                connection.execute(
                    f"""
                    DELETE FROM player_roster
                    WHERE
                        profile_saved_at IS NULL
                        AND name NOT IN ({placeholders})
                    """,
                    online_names,
                )
            else:
                connection.execute(
                    """
                    DELETE FROM player_roster
                    WHERE profile_saved_at IS NULL
                    """
                )
            connection.execute(
                """
                INSERT INTO player_roster_meta (key, value)
                VALUES ('last_collected_at', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(observed_at),),
            )
        return self.current()

    def current(self) -> dict[str, object] | None:
        with closing(self._connect()) as connection:
            meta = connection.execute(
                """
                SELECT value
                FROM player_roster_meta
                WHERE key = 'last_collected_at'
                """
            ).fetchone()
            if meta is None:
                return None
            rows = connection.execute(
                """
                SELECT
                    name,
                    level,
                    profile_saved_at,
                    position_x,
                    position_y,
                    position_z,
                    last_position_at,
                    online,
                    health,
                    max_health,
                    ping,
                    game_stage
                FROM player_roster
                ORDER BY online DESC, name COLLATE NOCASE
                """
            ).fetchall()

        roster = []
        online_players = []
        for row in rows:
            position = None
            if (
                row["position_x"] is not None
                and row["position_y"] is not None
                and row["position_z"] is not None
            ):
                position = {
                    "x": row["position_x"],
                    "y": row["position_y"],
                    "z": row["position_z"],
                }
            online = bool(row["online"])
            player = {
                "name": row["name"],
                "online": online,
                "level": row["level"],
                "gameStage": row["game_stage"] if online else None,
                "health": row["health"] if online else None,
                "maxHealth": row["max_health"] if online else None,
                "ping": row["ping"] if online else None,
                "position": position,
                "lastPositionAt": row["last_position_at"],
                "profileSavedAt": row["profile_saved_at"],
            }
            roster.append(player)
            if online and position is not None:
                online_players.append(player)
        return {
            "players": online_players,
            "roster": roster,
            "lastCollectedAt": float(meta["value"]),
        }


class RestartStore:
    """再起動予約とエージェントへの一度限りの指示を管理する。"""

    def __init__(
        self,
        database_path: Path,
        delay_seconds: int = RESTART_DELAY_SECONDS,
        cooldown_seconds: int = RESTART_COOLDOWN_SECONDS,
        failure_cooldown_seconds: int = RESTART_FAILURE_COOLDOWN_SECONDS,
    ) -> None:
        self.database_path = database_path
        self.delay_seconds = delay_seconds
        self.cooldown_seconds = cooldown_seconds
        self.failure_cooldown_seconds = failure_cooldown_seconds
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS restart_jobs (
                    job_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    requested_at REAL NOT NULL,
                    execute_at REAL NOT NULL,
                    requested_by TEXT NOT NULL,
                    announcement_stage INTEGER NOT NULL DEFAULT 0,
                    cancellation_announced INTEGER NOT NULL DEFAULT 0,
                    claimed_at REAL,
                    completed_at REAL,
                    result TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS restart_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def _row_payload(
        row: sqlite3.Row | None,
        now: float,
        cooldown_until: float,
    ) -> dict[str, object]:
        cooldown_remaining = max(0, math.ceil(cooldown_until - now))
        if row is None:
            return {
                "state": "idle",
                "cooldownRemainingSeconds": cooldown_remaining,
            }

        payload: dict[str, object] = {
            "jobId": row["job_id"],
            "state": row["state"],
            "requestedAt": row["requested_at"],
            "executeAt": row["execute_at"],
            "remainingSeconds": max(0, math.ceil(row["execute_at"] - now)),
            "cooldownRemainingSeconds": cooldown_remaining,
        }
        if row["completed_at"] is not None:
            payload["completedAt"] = row["completed_at"]
        if row["result"]:
            payload["result"] = row["result"]
        return payload

    @staticmethod
    def _cooldown_until(connection: sqlite3.Connection) -> float:
        row = connection.execute(
            "SELECT value FROM restart_meta WHERE key = 'cooldown_until'"
        ).fetchone()
        return float(row["value"]) if row else 0.0

    @staticmethod
    def _latest_job(connection: sqlite3.Connection) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT *
            FROM restart_jobs
            ORDER BY requested_at DESC
            LIMIT 1
            """
        ).fetchone()

    def status(self, now: float | None = None) -> dict[str, object]:
        current_time = time.time() if now is None else now
        with closing(self._connect()) as connection:
            row = self._latest_job(connection)
            return self._row_payload(
                row,
                current_time,
                self._cooldown_until(connection),
            )

    def publish_server_version(
        self,
        version: str,
        now: float | None = None,
    ) -> dict[str, object]:
        validated_version = validate_server_version(version)
        current_time = time.time() if now is None else now
        with closing(self._connect()) as connection, connection:
            connection.executemany(
                """
                INSERT INTO restart_meta (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (
                    ("server_version", validated_version),
                    ("server_version_updated_at", str(current_time)),
                ),
            )
        return {
            "version": validated_version,
            "updatedAt": current_time,
        }

    def server_version(self) -> dict[str, object] | None:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT key, value
                FROM restart_meta
                WHERE key IN (
                    'server_version',
                    'server_version_updated_at'
                )
                """
            ).fetchall()
        values = {row["key"]: row["value"] for row in rows}
        if (
            "server_version" not in values
            or "server_version_updated_at" not in values
        ):
            return None
        return {
            "version": validate_server_version(values["server_version"]),
            "updatedAt": float(values["server_version_updated_at"]),
        }

    def publish_game_schedule(
        self,
        schedule: object,
        now: float | None = None,
    ) -> dict[str, object]:
        validated = validate_game_schedule(schedule)
        current_time = time.time() if now is None else now
        values = {
            "game_mode": validated["mode"],
            "day_night_length_minutes": str(
                validated["dayNightLengthMinutes"]
            ),
            "blood_moon_frequency_days": str(
                validated["bloodMoonFrequencyDays"]
            ),
            "blood_moon_range_days": str(
                validated["bloodMoonRangeDays"]
            ),
            "blood_moon_start_hour": str(
                validated["bloodMoonStartHour"]
            ),
            "game_schedule_updated_at": str(current_time),
        }
        with closing(self._connect()) as connection, connection:
            connection.executemany(
                """
                INSERT INTO restart_meta (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                tuple(values.items()),
            )
        return {**validated, "updatedAt": current_time}

    def game_schedule(self) -> dict[str, object] | None:
        keys = (
            "game_mode",
            "day_night_length_minutes",
            "blood_moon_frequency_days",
            "blood_moon_range_days",
            "blood_moon_start_hour",
            "game_schedule_updated_at",
        )
        placeholders = ",".join("?" for _ in keys)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                f"""
                SELECT key, value
                FROM restart_meta
                WHERE key IN ({placeholders})
                """,
                keys,
            ).fetchall()
        values = {row["key"]: row["value"] for row in rows}
        if not all(key in values for key in keys):
            return None
        validated = validate_game_schedule(
            {
                "mode": values["game_mode"],
                "dayNightLengthMinutes": int(
                    values["day_night_length_minutes"]
                ),
                "bloodMoonFrequencyDays": int(
                    values["blood_moon_frequency_days"]
                ),
                "bloodMoonRangeDays": int(
                    values["blood_moon_range_days"]
                ),
                "bloodMoonStartHour": int(
                    values["blood_moon_start_hour"]
                ),
            }
        )
        return {
            **validated,
            "updatedAt": float(values["game_schedule_updated_at"]),
        }

    def publish_server_status(
        self,
        status: object,
        now: float | None = None,
    ) -> dict[str, object]:
        validated = validate_server_status(status)
        current_time = time.time() if now is None else now
        with closing(self._connect()) as connection, connection:
            connection.executemany(
                """
                INSERT INTO restart_meta (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (
                    (
                        "server_status_json",
                        json.dumps(
                            validated,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    ),
                    ("server_status_updated_at", str(current_time)),
                ),
            )
        return {**validated, "updatedAt": current_time}

    def server_status(self) -> dict[str, object] | None:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT key, value
                FROM restart_meta
                WHERE key IN (
                    'server_status_json',
                    'server_status_updated_at'
                )
                """
            ).fetchall()
        values = {row["key"]: row["value"] for row in rows}
        if not all(
            key in values
            for key in ("server_status_json", "server_status_updated_at")
        ):
            return None
        validated = validate_server_status(
            json.loads(values["server_status_json"])
        )
        return {
            **validated,
            "updatedAt": float(values["server_status_updated_at"]),
        }

    def request(
        self,
        requested_by: str,
        now: float | None = None,
    ) -> tuple[str, dict[str, object]]:
        current_time = time.time() if now is None else now
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            active = connection.execute(
                """
                SELECT *
                FROM restart_jobs
                WHERE state IN ('pending', 'executing')
                ORDER BY requested_at DESC
                LIMIT 1
                """
            ).fetchone()
            cooldown_until = self._cooldown_until(connection)

            if active is not None:
                return (
                    "already_active",
                    self._row_payload(active, current_time, cooldown_until),
                )
            if cooldown_until > current_time:
                return (
                    "cooldown",
                    self._row_payload(
                        self._latest_job(connection),
                        current_time,
                        cooldown_until,
                    ),
                )

            job_id = secrets.token_hex(16)
            execute_at = current_time + self.delay_seconds
            connection.execute(
                """
                INSERT INTO restart_jobs (
                    job_id, state, requested_at, execute_at, requested_by
                )
                VALUES (?, 'pending', ?, ?, ?)
                """,
                (job_id, current_time, execute_at, requested_by),
            )
            row = connection.execute(
                "SELECT * FROM restart_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            return (
                "created",
                self._row_payload(row, current_time, cooldown_until),
            )

    def cancel(
        self,
        now: float | None = None,
    ) -> tuple[str, dict[str, object]]:
        current_time = time.time() if now is None else now
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT *
                FROM restart_jobs
                WHERE state IN ('pending', 'executing')
                ORDER BY requested_at DESC
                LIMIT 1
                """
            ).fetchone()
            cooldown_until = self._cooldown_until(connection)
            if row is None:
                return (
                    "not_pending",
                    self._row_payload(
                        self._latest_job(connection),
                        current_time,
                        cooldown_until,
                    ),
                )
            if row["state"] == "executing":
                return (
                    "too_late",
                    self._row_payload(row, current_time, cooldown_until),
                )

            connection.execute(
                """
                UPDATE restart_jobs
                SET state = 'cancelled',
                    completed_at = ?,
                    result = 'cancelled_by_user'
                WHERE job_id = ?
                """,
                (current_time, row["job_id"]),
            )
            updated = connection.execute(
                "SELECT * FROM restart_jobs WHERE job_id = ?",
                (row["job_id"],),
            ).fetchone()
            return (
                "cancelled",
                self._row_payload(updated, current_time, cooldown_until),
            )

    def next_agent_action(
        self,
        now: float | None = None,
    ) -> dict[str, object] | None:
        current_time = time.time() if now is None else now
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._latest_job(connection)
            if row is None:
                return None

            if (
                row["state"] == "cancelled"
                and row["announcement_stage"] > 0
                and not row["cancellation_announced"]
            ):
                connection.execute(
                    """
                    UPDATE restart_jobs
                    SET cancellation_announced = 1
                    WHERE job_id = ?
                    """,
                    (row["job_id"],),
                )
                return {
                    "action": "announce_cancelled",
                    "jobId": row["job_id"],
                }

            if row["state"] != "pending":
                return None

            remaining = row["execute_at"] - current_time
            if remaining <= 0:
                connection.execute(
                    """
                    UPDATE restart_jobs
                    SET state = 'executing', claimed_at = ?
                    WHERE job_id = ? AND state = 'pending'
                    """,
                    (current_time, row["job_id"]),
                )
                return {"action": "restart", "jobId": row["job_id"]}

            stages = (
                (10, 4, "announce_10_seconds"),
                (30, 3, "announce_30_seconds"),
                (60, 2, "announce_1_minute"),
                (self.delay_seconds, 1, "announce_scheduled"),
            )
            for threshold, stage, action in stages:
                if remaining <= threshold and row["announcement_stage"] < stage:
                    connection.execute(
                        """
                        UPDATE restart_jobs
                        SET announcement_stage = ?
                        WHERE job_id = ?
                        """,
                        (stage, row["job_id"]),
                    )
                    return {
                        "action": action,
                        "jobId": row["job_id"],
                        "remainingSeconds": max(0, math.ceil(remaining)),
                    }
            return None

    def complete(
        self,
        job_id: str,
        success: bool,
        result: str,
        now: float | None = None,
    ) -> tuple[str, dict[str, object]]:
        current_time = time.time() if now is None else now
        safe_result = result[:500]
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM restart_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            cooldown_until = self._cooldown_until(connection)
            if row is None:
                return (
                    "not_found",
                    self._row_payload(
                        self._latest_job(connection),
                        current_time,
                        cooldown_until,
                    ),
                )
            if row["state"] != "executing":
                return (
                    "not_executing",
                    self._row_payload(row, current_time, cooldown_until),
                )

            state = "completed" if success else "failed"
            cooldown = (
                self.cooldown_seconds
                if success
                else self.failure_cooldown_seconds
            )
            cooldown_until = current_time + cooldown
            connection.execute(
                """
                UPDATE restart_jobs
                SET state = ?, completed_at = ?, result = ?
                WHERE job_id = ?
                """,
                (state, current_time, safe_result, job_id),
            )
            connection.execute(
                """
                INSERT INTO restart_meta (key, value)
                VALUES ('cooldown_until', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(cooldown_until),),
            )
            updated = connection.execute(
                "SELECT * FROM restart_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            return (
                "completed",
                self._row_payload(updated, current_time, cooldown_until),
            )


def generate_password_hash(
    passphrase: str,
    iterations: int = PBKDF2_ITERATIONS,
    salt: bytes | None = None,
) -> str:
    password_salt = secrets.token_bytes(16) if salt is None else salt
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        passphrase.encode("utf-8"),
        password_salt,
        iterations,
    )
    return "$".join(
        (
            "pbkdf2_sha256",
            str(iterations),
            base64.b64encode(password_salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        )
    )


def parse_password_hash(encoded_hash: str) -> PasswordHash:
    try:
        algorithm, iterations_text, salt_text, digest_text = (
            encoded_hash.strip().split("$")
        )
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_text, validate=True)
        digest = base64.b64decode(digest_text, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("invalid password hash format") from error

    if algorithm != "pbkdf2_sha256":
        raise ValueError("unsupported password hash algorithm")
    if iterations <= 0:
        raise ValueError("password hash iterations must be positive")
    if len(salt) < 16:
        raise ValueError("password hash salt is too short")
    if len(digest) != 32:
        raise ValueError("password hash digest has an invalid length")
    return PasswordHash(iterations, salt, digest)


def load_expected_password_hash(path: Path) -> PasswordHash:
    return parse_password_hash(path.read_text(encoding="ascii"))


def load_agent_token(path: Path) -> str:
    token = path.read_text(encoding="ascii").strip()
    if len(token) < 32:
        raise ValueError("restart agent token must have at least 32 characters")
    return token


def player_upstream_headers(
    token_name: str,
    token_secret: str,
) -> dict[str, str]:
    return {
        "Accept": "application/json",
        "X-SDTD-API-TOKENNAME": token_name,
        "X-SDTD-API-SECRET": token_secret,
    }


def clean_activity_text(value: object, max_length: int) -> str:
    if not isinstance(value, str):
        raise ValueError("activity text must be a string")
    cleaned = CONTROL_CHARACTERS.sub("", value).strip()
    if not cleaned:
        raise ValueError("activity text is empty")
    return cleaned[:max_length]


def parse_activity_entry(entry: object) -> dict[str, object] | None:
    if not isinstance(entry, dict):
        return None
    isotime = entry.get("isotime")
    message = entry.get("msg")
    if not isinstance(isotime, str) or not isinstance(message, str):
        return None
    try:
        occurred_epoch = datetime.fromisoformat(isotime).timestamp()
    except ValueError:
        return None

    event_type = ""
    player = ""
    public_message = ""
    chat_match = CHAT_PATTERN.fullmatch(message)
    if chat_match:
        sender, channel, body = chat_match.groups()
        try:
            player = (
                "SERVER"
                if sender == "-non-player-"
                else clean_activity_text(sender, 64)
            )
            public_message = clean_activity_text(body, 500)
            clean_activity_text(channel, 32)
        except ValueError:
            return None
        event_type = "chat"
    else:
        player_match = PLAYER_EVENT_PATTERN.fullmatch(message)
        if not player_match:
            return None
        raw_player, action = player_match.groups()
        try:
            player = clean_activity_text(raw_player, 64)
        except ValueError:
            return None
        event_type = {
            "joined the game": "login",
            "left the game": "logout",
            "died": "death",
        }[action]

    event_key_source = "\x00".join(
        (
            isotime,
            str(entry.get("id", "")),
            str(entry.get("uptime", "")),
            event_type,
            player,
            public_message,
        )
    )
    event_key = hashlib.sha256(
        event_key_source.encode("utf-8")
    ).hexdigest()
    return {
        "eventKey": event_key,
        "occurredAt": isotime,
        "occurredEpoch": occurred_epoch,
        "type": event_type,
        "player": player,
        "message": public_message,
    }


def parse_activity_payload(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        raise ValueError("invalid activity response")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("invalid activity response data")
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise ValueError("invalid activity entries")
    return [
        event
        for entry in entries
        if (event := parse_activity_entry(entry)) is not None
    ]


class ActivityCollector(threading.Thread):
    """7DTDの生ログを収集し、公開可能なイベントだけを保存する。"""

    def __init__(
        self,
        store: ActivityStore,
        upstream_url: str,
        token_name: str,
        token_secret: str,
        poll_seconds: int = ACTIVITY_POLL_SECONDS,
    ) -> None:
        super().__init__(name="activity-collector", daemon=True)
        self.store = store
        self.upstream_url = upstream_url
        self.token_name = token_name
        self.token_secret = token_secret
        self.poll_seconds = max(2, poll_seconds)
        self.stop_event = threading.Event()

    def collect_once(self) -> int:
        request = urllib.request.Request(
            self.upstream_url,
            headers=player_upstream_headers(
                self.token_name,
                self.token_secret,
            ),
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=7) as response:
            payload = json.loads(response.read())
        events = parse_activity_payload(payload)
        inserted = self.store.ingest(events)
        self.store.mark_collection(True)
        return inserted

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self.collect_once()
            except (
                json.JSONDecodeError,
                ValueError,
                urllib.error.URLError,
                TimeoutError,
            ):
                self.store.mark_collection(False)
            self.stop_event.wait(self.poll_seconds)

    def stop(self) -> None:
        self.stop_event.set()


def filtered_player_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("invalid player response")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("invalid player response data")
    players = data.get("players")
    if not isinstance(players, list):
        raise ValueError("invalid player list")

    filtered_players: list[dict[str, object]] = []
    for player in players:
        if not isinstance(player, dict):
            continue
        name = player.get("name")
        position = player.get("position")
        if not isinstance(name, str) or not isinstance(position, dict):
            continue
        coordinates = {
            axis: position.get(axis)
            for axis in ("x", "y", "z")
        }
        if not all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in coordinates.values()
        ):
            continue
        filtered_players.append(
            {
                "name": name,
                "position": coordinates,
            }
        )
    return {"data": {"players": filtered_players}}


def credentials_are_valid(
    authorization: str | None,
    expected_password_hash: PasswordHash,
    username: str = AUTH_USERNAME,
) -> bool:
    if not authorization:
        return False

    try:
        scheme, encoded = authorization.split(" ", 1)
        if scheme.lower() != "basic":
            return False
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
        supplied_username, supplied_password = decoded.split(":", 1)
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False

    supplied_hash = hashlib.pbkdf2_hmac(
        "sha256",
        supplied_password.encode("utf-8"),
        expected_password_hash.salt,
        expected_password_hash.iterations,
        dklen=len(expected_password_hash.digest),
    )
    return hmac.compare_digest(supplied_username, username) and (
        hmac.compare_digest(
            supplied_hash,
            expected_password_hash.digest,
        )
    )


def normalized_client_ip(handler: BaseHTTPRequestHandler) -> str:
    remote_ip = ipaddress.ip_address(handler.client_address[0])
    trusted_proxy_network = ipaddress.ip_network("172.16.0.0/12")
    if remote_ip not in trusted_proxy_network:
        return str(remote_ip)

    supplied_ip = handler.headers.get("X-Real-IP", "").strip()
    try:
        return str(ipaddress.ip_address(supplied_ip))
    except ValueError:
        return str(remote_ip)


def validate_server_version(version: object) -> str:
    if not isinstance(version, str):
        raise ValueError("server version must be a string")
    normalized = version.strip()
    if not SERVER_VERSION_PATTERN.fullmatch(normalized):
        raise ValueError("invalid server version")
    return normalized


def validate_game_schedule(schedule: object) -> dict[str, object]:
    if not isinstance(schedule, dict):
        raise ValueError("game schedule must be an object")
    mode = schedule.get("mode")
    if mode not in GAME_MODES:
        raise ValueError("invalid game mode")

    ranges = {
        "dayNightLengthMinutes": (1, 1440),
        "bloodMoonFrequencyDays": (1, 100),
        "bloodMoonRangeDays": (0, 20),
        "bloodMoonStartHour": (0, 23),
    }
    validated: dict[str, object] = {"mode": mode}
    for key, (minimum, maximum) in ranges.items():
        value = schedule.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < minimum
            or value > maximum
        ):
            raise ValueError(f"invalid {key}")
        validated[key] = value
    return validated


def validate_server_status(status: object) -> dict[str, object]:
    if not isinstance(status, dict):
        raise ValueError("server status must be an object")

    ranges = {
        "uptimeMinutes": (0.0, 10_000_000.0),
        "fps": (0.0, 10_000.0),
        "heapMb": (0.0, 10_000_000.0),
        "maxMemoryMb": (0.0, 10_000_000.0),
        "rssMb": (0.0, 10_000_000.0),
        "chunks": (0, 10_000_000),
        "players": (0, 10_000),
        "zombies": (0, 10_000_000),
        "entities": (0, 10_000_000),
    }
    validated: dict[str, object] = {}
    for key, (minimum, maximum) in ranges.items():
        value = status.get(key)
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value < minimum
            or value > maximum
        ):
            raise ValueError(f"invalid {key}")
        validated[key] = int(value) if key in {
            "chunks",
            "players",
            "zombies",
            "entities",
        } else float(value)
    return validated


def _validate_public_text(
    value: object,
    field: str,
    maximum_length: int,
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"invalid {field}")
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > maximum_length
        or CONTROL_CHARACTERS.search(normalized)
    ):
        raise ValueError(f"invalid {field}")
    return normalized


def validate_map_entities(entities: object) -> list[dict[str, object]]:
    if not isinstance(entities, list) or len(entities) > MAX_MAP_ENTITIES:
        raise ValueError("invalid entities")

    validated: list[dict[str, object]] = []
    entity_keys: set[str] = set()
    for entity in entities:
        if not isinstance(entity, dict):
            raise ValueError("invalid entity")

        entity_id = entity.get("entityId")
        if isinstance(entity_id, int) and not isinstance(entity_id, bool):
            entity_id = str(entity_id)
        if (
            not isinstance(entity_id, str)
            or not entity_id.isascii()
            or not entity_id.isdigit()
            or len(entity_id) > 20
        ):
            raise ValueError("invalid entityId")

        kind = entity.get("kind")
        if not isinstance(kind, str) or kind not in MAP_ENTITY_LABELS:
            raise ValueError("invalid entity kind")

        position = entity.get("position")
        if not isinstance(position, dict):
            raise ValueError("invalid entity position")
        coordinates: dict[str, float] = {}
        for axis in ("x", "y", "z"):
            value = position.get(axis)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or abs(value) > 100_000
            ):
                raise ValueError(f"invalid entity position {axis}")
            coordinates[axis] = float(value)

        entity_key = f"{kind}:{entity_id}"
        if entity_key in entity_keys:
            raise ValueError("duplicate entity")
        entity_keys.add(entity_key)
        validated.append(
            {
                "entityId": entity_id,
                "kind": kind,
                "label": MAP_ENTITY_LABELS[kind],
                "position": coordinates,
            }
        )
        public_entity = validated[-1]
        accepts_private_metadata = kind in {
            "bedroll",
            "quest",
            "shared_waypoint",
        }
        if accepts_private_metadata and "label" in entity:
            public_entity["label"] = _validate_public_text(
                entity["label"],
                "entity label",
                100,
            )
        if accepts_private_metadata and "owner" in entity:
            public_entity["owner"] = _validate_public_text(
                entity["owner"],
                "entity owner",
                64,
            )
        if accepts_private_metadata and "detail" in entity:
            public_entity["detail"] = _validate_public_text(
                entity["detail"],
                "entity detail",
                100,
            )
        if kind == "quest" and "questCode" in entity:
            quest_code = entity["questCode"]
            if (
                isinstance(quest_code, bool)
                or not isinstance(quest_code, int)
                or quest_code < -2_147_483_648
                or quest_code > 2_147_483_647
            ):
                raise ValueError("invalid questCode")
            public_entity["questCode"] = quest_code

    return sorted(
        validated,
        key=lambda entity: (str(entity["kind"]), str(entity["entityId"])),
    )


def _validate_player_name(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("invalid player name")
    name = CONTROL_CHARACTERS.sub("", value).strip()
    if not name or len(name) > 64:
        raise ValueError("invalid player name")
    return name


def _optional_bounded_integer(
    value: object,
    minimum: int,
    maximum: int,
    field: str,
) -> int | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or value > maximum
    ):
        raise ValueError(f"invalid {field}")
    return value


def validate_player_profiles(
    profiles: object,
) -> list[dict[str, object]]:
    if not isinstance(profiles, list) or len(profiles) > MAX_PLAYER_PROFILES:
        raise ValueError("invalid player profiles")

    validated = []
    names: set[str] = set()
    for profile in profiles:
        if not isinstance(profile, dict):
            raise ValueError("invalid player profile")
        name = _validate_player_name(profile.get("name"))
        normalized_name = name.casefold()
        if normalized_name in names:
            raise ValueError("duplicate player profile")
        names.add(normalized_name)
        level = _optional_bounded_integer(
            profile.get("level"),
            0,
            1000,
            "player level",
        )
        saved_at = profile.get("profileSavedAt")
        if (
            isinstance(saved_at, bool)
            or not isinstance(saved_at, (int, float))
            or not math.isfinite(saved_at)
            or saved_at <= 0
        ):
            raise ValueError("invalid player profile timestamp")
        validated.append(
            {
                "name": name,
                "level": level,
                "profileSavedAt": float(saved_at),
            }
        )
    return sorted(validated, key=lambda profile: str(profile["name"]).casefold())


def validate_online_players(
    players: object,
) -> list[dict[str, object]]:
    if not isinstance(players, list) or len(players) > MAX_PLAYER_PROFILES:
        raise ValueError("invalid online players")

    validated = []
    names: set[str] = set()
    for player in players:
        if not isinstance(player, dict):
            raise ValueError("invalid online player")
        name = _validate_player_name(player.get("name"))
        normalized_name = name.casefold()
        if normalized_name in names:
            raise ValueError("duplicate online player")
        names.add(normalized_name)

        position = player.get("position")
        if not isinstance(position, dict):
            raise ValueError("invalid player position")
        coordinates: dict[str, float] = {}
        for axis in ("x", "y", "z"):
            value = position.get(axis)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or abs(value) > 100_000
            ):
                raise ValueError(f"invalid player position {axis}")
            coordinates[axis] = float(value)

        validated.append(
            {
                "name": name,
                "position": coordinates,
                "level": _optional_bounded_integer(
                    player.get("level"),
                    0,
                    1000,
                    "player level",
                ),
                "health": _optional_bounded_integer(
                    player.get("health"),
                    0,
                    100_000,
                    "player health",
                ),
                "maxHealth": _optional_bounded_integer(
                    player.get("maxHealth"),
                    1,
                    100_000,
                    "player max health",
                ),
                "ping": _optional_bounded_integer(
                    player.get("ping"),
                    0,
                    60_000,
                    "player ping",
                ),
                "gameStage": _optional_bounded_integer(
                    player.get("gameStage"),
                    0,
                    10_000_000,
                    "player game stage",
                ),
            }
        )
    return sorted(validated, key=lambda player: str(player["name"]).casefold())


class MapGatewayHandler(BaseHTTPRequestHandler):
    server_version = "MapGateway"
    sys_version = ""
    auth_store: AuthStore
    activity_store: ActivityStore
    entity_store: MapEntityStore
    player_store: PlayerStore
    restart_store: RestartStore
    biome_path: Path
    expected_password_hash: PasswordHash
    agent_token: str
    player_api_token_name: str
    player_api_token: str
    restart_enabled: bool = RESTART_ENABLED

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._send_json(200, {"status": "ok"})
            return
        if path == "/api/features":
            self._send_json(
                200,
                {"data": {"restart": self.restart_enabled}},
            )
            return
        if path == "/api/server-version":
            self._server_version()
            return
        if path == "/api/game-schedule":
            self._game_schedule()
            return
        if path == "/internal/restart/agent":
            if not self.restart_enabled:
                self._send_json(404, {"error": "not_found"})
                return
            if not self._agent_is_valid():
                self._send_json(401, {"error": "unauthorized"})
                return
            action = self.restart_store.next_agent_action()
            if action is None:
                self.send_response(204)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
            else:
                self._send_json(200, {"data": action})
            return
        if path not in (
            "/api/auth/check",
            "/api/activity",
            "/api/map-entities",
            "/api/biome",
            "/api/player",
            "/api/restart/status",
            "/api/server-status",
        ):
            self._send_json(404, {"error": "not_found"})
            return

        client_ip = normalized_client_ip(self)
        if not self._authenticate(client_ip):
            return
        if path == "/api/auth/check":
            self._send_json(200, {"data": {"authenticated": True}})
        elif path == "/api/activity":
            self._send_json(200, {"data": self.activity_store.recent()})
        elif path == "/api/map-entities":
            entities = self.entity_store.current()
            if entities is None:
                self._send_json(503, {"error": "entities_unavailable"})
            else:
                self._send_json(200, {"data": entities})
        elif path == "/api/biome":
            self._biome_image()
        elif path == "/api/player":
            players = self.player_store.current()
            if players is None:
                self._send_json(503, {"error": "players_unavailable"})
            else:
                self._send_json(200, {"data": players})
        elif path == "/api/restart/status":
            if not self.restart_enabled:
                self._send_json(404, {"error": "not_found"})
            else:
                self._send_json(200, {"data": self.restart_store.status()})
        elif path == "/api/server-status":
            status = self.restart_store.server_status()
            if status is None:
                self._send_json(503, {"error": "status_unavailable"})
            else:
                self._send_json(200, {"data": status})

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/internal/server-version":
            if not self._agent_is_valid():
                self._send_json(401, {"error": "unauthorized"})
                return
            payload = self._read_json()
            if payload is None:
                return
            try:
                runtime_version = self.restart_store.publish_server_version(
                    payload.get("version")
                )
            except ValueError:
                self._send_json(400, {"error": "invalid_server_version"})
                return
            self._send_json(200, {"data": runtime_version})
            return

        if path == "/internal/game-schedule":
            if not self._agent_is_valid():
                self._send_json(401, {"error": "unauthorized"})
                return
            payload = self._read_json()
            if payload is None:
                return
            try:
                schedule = self.restart_store.publish_game_schedule(payload)
            except (TypeError, ValueError):
                self._send_json(400, {"error": "invalid_game_schedule"})
                return
            self._send_json(200, {"data": schedule})
            return

        if path == "/internal/server-status":
            if not self._agent_is_valid():
                self._send_json(401, {"error": "unauthorized"})
                return
            payload = self._read_json()
            if payload is None:
                return
            try:
                status = self.restart_store.publish_server_status(payload)
            except (TypeError, ValueError):
                self._send_json(400, {"error": "invalid_server_status"})
                return
            self._send_json(200, {"data": status})
            return

        if path == "/internal/biome":
            if not self._agent_is_valid():
                self._send_json(401, {"error": "unauthorized"})
                return
            payload = self._read_json()
            if payload is None:
                return
            try:
                encoded = payload.get("pngBase64")
                if not isinstance(encoded, str):
                    raise ValueError("missing png")
                image = base64.b64decode(encoded, validate=True)
                if (
                    len(image) < 24
                    or len(image) > 200_000
                    or image[:8] != b"\x89PNG\r\n\x1a\n"
                    or image[12:16] != b"IHDR"
                ):
                    raise ValueError("invalid png")
                width = int.from_bytes(image[16:20], "big")
                height = int.from_bytes(image[20:24], "big")
                if width < 1 or height < 1 or width > 4096 or height > 4096:
                    raise ValueError("invalid dimensions")
                temporary_path = self.biome_path.with_suffix(".png.new")
                temporary_path.write_bytes(image)
                temporary_path.replace(self.biome_path)
            except (binascii.Error, OSError, ValueError):
                self._send_json(400, {"error": "invalid_biome"})
                return
            self._send_json(
                200,
                {
                    "data": {
                        "width": width,
                        "height": height,
                        "sha256": hashlib.sha256(image).hexdigest(),
                    }
                },
            )
            return

        if path == "/internal/map-entities":
            if not self._agent_is_valid():
                self._send_json(401, {"error": "unauthorized"})
                return
            payload = self._read_json()
            if payload is None:
                return
            try:
                entities = self.entity_store.publish(
                    payload.get("entities")
                )
            except (TypeError, ValueError):
                self._send_json(400, {"error": "invalid_map_entities"})
                return
            self._send_json(200, {"data": entities})
            return

        if path == "/internal/player-snapshot":
            if not self._agent_is_valid():
                self._send_json(401, {"error": "unauthorized"})
                return
            payload = self._read_json()
            if payload is None:
                return
            try:
                players = self.player_store.publish(
                    payload.get("profiles"),
                    payload.get("onlinePlayers"),
                )
            except (TypeError, ValueError):
                self._send_json(400, {"error": "invalid_player_snapshot"})
                return
            self._send_json(200, {"data": players})
            return

        if path == "/internal/restart/complete":
            if not self.restart_enabled:
                self._send_json(404, {"error": "not_found"})
                return
            if not self._agent_is_valid():
                self._send_json(401, {"error": "unauthorized"})
                return
            payload = self._read_json()
            if payload is None:
                return
            job_id = payload.get("jobId")
            success = payload.get("success")
            result = payload.get("result", "")
            if (
                not isinstance(job_id, str)
                or not isinstance(success, bool)
                or not isinstance(result, str)
            ):
                self._send_json(400, {"error": "invalid_request"})
                return
            outcome, status = self.restart_store.complete(
                job_id,
                success,
                result,
            )
            code = 200 if outcome == "completed" else 409
            self._send_json(code, {"data": status, "outcome": outcome})
            return

        if path not in ("/api/restart/request", "/api/restart/cancel"):
            self._send_json(404, {"error": "not_found"})
            return
        if not self.restart_enabled:
            self._send_json(404, {"error": "not_found"})
            return

        client_ip = normalized_client_ip(self)
        if not self._authenticate(client_ip):
            return

        payload = self._read_json()
        if payload is None:
            return
        if path == "/api/restart/request":
            if payload.get("confirmation") != "RESTART":
                self._send_json(400, {"error": "confirmation_required"})
                return
            outcome, status = self.restart_store.request(client_ip)
            code = 201 if outcome == "created" else 409
        else:
            outcome, status = self.restart_store.cancel()
            code = 200 if outcome == "cancelled" else 409
        self._send_json(code, {"data": status, "outcome": outcome})

    def _authenticate(self, client_ip: str) -> bool:
        valid = credentials_are_valid(
            self.headers.get("Authorization"),
            self.expected_password_hash,
        )
        decision = self.auth_store.evaluate(client_ip, valid)
        if decision.status == "blocked":
            self._send_json(
                429,
                {
                    "error": "temporarily_blocked",
                    "retryAfterSeconds": decision.retry_after_seconds,
                },
                {"Retry-After": str(decision.retry_after_seconds)},
            )
            self._log_result(client_ip, "blocked")
            return False
        if decision.status == "denied":
            self._send_json(
                401,
                {
                    "error": "invalid_passphrase",
                    "remainingAttempts": decision.remaining_attempts,
                },
                {
                    "WWW-Authenticate": (
                        'Basic realm="Map access", charset="UTF-8"'
                    )
                },
            )
            self._log_result(client_ip, "denied")
            return False
        self._log_result(client_ip, "allowed")
        return True

    def _agent_is_valid(self) -> bool:
        supplied = self.headers.get("X-Restart-Agent-Token", "")
        return hmac.compare_digest(supplied, self.agent_token)

    def _server_version(self) -> None:
        try:
            runtime_version = self.restart_store.server_version()
        except (ValueError, TypeError):
            self._send_json(503, {"error": "version_unavailable"})
            return
        if runtime_version is None:
            self._send_json(503, {"error": "version_unavailable"})
            return
        self._send_json(200, {"data": runtime_version})

    def _game_schedule(self) -> None:
        try:
            schedule = self.restart_store.game_schedule()
        except (TypeError, ValueError):
            self._send_json(503, {"error": "schedule_unavailable"})
            return
        if schedule is None:
            self._send_json(503, {"error": "schedule_unavailable"})
            return
        self._send_json(200, {"data": schedule})

    def _biome_image(self) -> None:
        try:
            body = self.biome_path.read_bytes()
        except OSError:
            self._send_json(503, {"error": "biome_unavailable"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Cache-Control", "private, max-age=3600")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("ETag", f'"{hashlib.sha256(body).hexdigest()}"')
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any] | None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send_json(400, {"error": "invalid_content_length"})
            return None
        if content_length <= 0 or content_length > MAX_REQUEST_BODY_BYTES:
            self._send_json(400, {"error": "invalid_request_size"})
            return None
        try:
            payload = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send_json(400, {"error": "invalid_json"})
            return None
        if not isinstance(payload, dict):
            self._send_json(400, {"error": "invalid_request"})
            return None
        return payload

    def _send_json(
        self,
        status: int,
        payload: dict[str, object],
        headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _log_result(self, client_ip: str, result: str) -> None:
        print(
            f'client_ip="{client_ip}" auth_result="{result}"',
            flush=True,
        )

    def log_message(self, _format: str, *_args: object) -> None:
        return


# 旧テストや外部参照との互換性を維持する。
PlayerAuthHandler = MapGatewayHandler


def main() -> None:
    expected_password_hash = load_expected_password_hash(PASSWORD_HASH_FILE)
    agent_token = load_agent_token(AGENT_TOKEN_FILE)
    player_api_token = load_agent_token(PLAYER_API_TOKEN_FILE)
    activity_api_token = load_agent_token(ACTIVITY_API_TOKEN_FILE)
    auth_store = AuthStore(DATABASE_PATH)
    activity_store = ActivityStore(DATABASE_PATH)
    entity_store = MapEntityStore(DATABASE_PATH)
    player_store = PlayerStore(DATABASE_PATH)
    restart_store = RestartStore(DATABASE_PATH)
    activity_collector = ActivityCollector(
        activity_store,
        ACTIVITY_UPSTREAM_URL,
        ACTIVITY_API_TOKEN_NAME,
        activity_api_token,
    )
    MapGatewayHandler.expected_password_hash = expected_password_hash
    MapGatewayHandler.agent_token = agent_token
    MapGatewayHandler.player_api_token_name = PLAYER_API_TOKEN_NAME
    MapGatewayHandler.player_api_token = player_api_token
    MapGatewayHandler.restart_enabled = RESTART_ENABLED
    MapGatewayHandler.auth_store = auth_store
    MapGatewayHandler.activity_store = activity_store
    MapGatewayHandler.entity_store = entity_store
    MapGatewayHandler.player_store = player_store
    MapGatewayHandler.restart_store = restart_store
    MapGatewayHandler.biome_path = DATABASE_PATH.parent / "biomes.png"
    server = ThreadingHTTPServer(
        (LISTEN_HOST, LISTEN_PORT),
        MapGatewayHandler,
    )
    activity_collector.start()
    try:
        server.serve_forever()
    finally:
        activity_collector.stop()
        activity_collector.join(timeout=2)
        server.server_close()


if __name__ == "__main__":
    main()
