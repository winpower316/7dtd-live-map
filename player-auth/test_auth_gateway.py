import base64
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from auth_gateway import (
    ActivityStore,
    AuthStore,
    MapGatewayHandler,
    MapEntityStore,
    PlayerStore,
    RestartStore,
    credentials_are_valid,
    filtered_player_payload,
    generate_password_hash,
    normalized_client_ip,
    parse_activity_entry,
    parse_activity_payload,
    parse_password_hash,
    player_upstream_headers,
    validate_game_schedule,
    validate_map_entities,
    validate_online_players,
    validate_player_profiles,
    validate_server_status,
    validate_server_version,
    _env_int,
)


class EnvironmentConfigurationTests(unittest.TestCase):
    def test_integer_setting_uses_default_and_override(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(_env_int("TEST_SETTING", 10, 1, 20), 10)
        with patch.dict("os.environ", {"TEST_SETTING": "15"}, clear=True):
            self.assertEqual(_env_int("TEST_SETTING", 10, 1, 20), 15)

    def test_integer_setting_rejects_invalid_or_unsafe_value(self) -> None:
        for value in ("invalid", "0", "21"):
            with self.subTest(value=value):
                with patch.dict(
                    "os.environ",
                    {"TEST_SETTING": value},
                    clear=True,
                ):
                    with self.assertRaises(RuntimeError):
                        _env_int("TEST_SETTING", 10, 1, 20)


class AuthStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self.temporary_directory.name) / "auth-state.sqlite3"
        )
        self.store = AuthStore(
            self.database_path,
            max_failures=5,
            failure_window_seconds=3600,
            block_seconds=86400,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_fifth_failure_blocks_for_24_hours(self) -> None:
        for attempt in range(1, 5):
            decision = self.store.evaluate(
                "198.51.100.10",
                False,
                now=1000 + attempt,
            )
            self.assertEqual(decision.status, "denied")
            self.assertEqual(decision.remaining_attempts, 5 - attempt)

        decision = self.store.evaluate(
            "198.51.100.10",
            False,
            now=1005,
        )
        self.assertEqual(decision.status, "blocked")
        self.assertEqual(decision.retry_after_seconds, 86400)

        decision = self.store.evaluate(
            "198.51.100.10",
            True,
            now=1006,
        )
        self.assertEqual(decision.status, "blocked")

    def test_success_resets_failure_count(self) -> None:
        self.store.evaluate("198.51.100.20", False, now=1000)
        self.store.evaluate("198.51.100.20", False, now=1001)
        decision = self.store.evaluate(
            "198.51.100.20",
            True,
            now=1002,
        )
        self.assertEqual(decision.status, "allowed")

        decision = self.store.evaluate(
            "198.51.100.20",
            False,
            now=1003,
        )
        self.assertEqual(decision.remaining_attempts, 4)

    def test_failure_window_expires(self) -> None:
        for attempt in range(4):
            self.store.evaluate(
                "198.51.100.30",
                False,
                now=1000 + attempt,
            )

        decision = self.store.evaluate(
            "198.51.100.30",
            False,
            now=5000,
        )
        self.assertEqual(decision.status, "denied")
        self.assertEqual(decision.remaining_attempts, 4)

    def test_block_expires(self) -> None:
        for attempt in range(5):
            self.store.evaluate(
                "198.51.100.40",
                False,
                now=1000 + attempt,
            )

        decision = self.store.evaluate(
            "198.51.100.40",
            True,
            now=1004 + 86401,
        )
        self.assertEqual(decision.status, "allowed")

    def test_block_persists_when_store_is_reopened(self) -> None:
        for attempt in range(5):
            self.store.evaluate(
                "198.51.100.50",
                False,
                now=1000 + attempt,
            )

        reopened_store = AuthStore(
            self.database_path,
            max_failures=5,
            failure_window_seconds=3600,
            block_seconds=86400,
        )
        decision = reopened_store.evaluate(
            "198.51.100.50",
            True,
            now=1005,
        )
        self.assertEqual(decision.status, "blocked")


class CredentialTests(unittest.TestCase):
    def setUp(self) -> None:
        self.expected_hash = parse_password_hash(
            generate_password_hash(
                "correct",
                iterations=1000,
                salt=b"0123456789abcdef",
            )
        )

    @staticmethod
    def authorization(username: str, password: str) -> str:
        encoded = base64.b64encode(
            f"{username}:{password}".encode("utf-8")
        ).decode("ascii")
        return f"Basic {encoded}"

    def test_correct_credentials(self) -> None:
        self.assertTrue(
            credentials_are_valid(
                self.authorization("map", "correct"),
                self.expected_hash,
            )
        )

    def test_wrong_password(self) -> None:
        self.assertFalse(
            credentials_are_valid(
                self.authorization("map", "wrong"),
                self.expected_hash,
            )
        )

    def test_wrong_username(self) -> None:
        self.assertFalse(
            credentials_are_valid(
                self.authorization("admin", "correct"),
                self.expected_hash,
            )
        )

    def test_password_hash_uses_salt_and_work_factor(self) -> None:
        encoded_hash = generate_password_hash(
            "correct",
            iterations=600_000,
            salt=b"fedcba9876543210",
        )
        parsed_hash = parse_password_hash(encoded_hash)
        self.assertEqual(parsed_hash.iterations, 600_000)
        self.assertEqual(parsed_hash.salt, b"fedcba9876543210")
        self.assertEqual(len(parsed_hash.digest), 32)

    def test_player_upstream_uses_dedicated_api_token_headers(self) -> None:
        self.assertEqual(
            player_upstream_headers("reader", "secret"),
            {
                "Accept": "application/json",
                "X-SDTD-API-TOKENNAME": "reader",
                "X-SDTD-API-SECRET": "secret",
            },
        )


class RestartStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self.temporary_directory.name) / "state.sqlite3"
        )
        self.store = RestartStore(
            self.database_path,
            delay_seconds=300,
            cooldown_seconds=1800,
            failure_cooldown_seconds=300,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_request_has_five_minute_delay_and_can_be_cancelled(self) -> None:
        outcome, status = self.store.request("198.51.100.10", now=1000)
        self.assertEqual(outcome, "created")
        self.assertEqual(status["state"], "pending")
        self.assertEqual(status["executeAt"], 1300)
        self.assertEqual(status["remainingSeconds"], 300)

        outcome, status = self.store.cancel(now=1100)
        self.assertEqual(outcome, "cancelled")
        self.assertEqual(status["state"], "cancelled")

    def test_duplicate_request_is_rejected(self) -> None:
        self.store.request("198.51.100.10", now=1000)
        outcome, status = self.store.request("198.51.100.20", now=1001)
        self.assertEqual(outcome, "already_active")
        self.assertEqual(status["state"], "pending")

    def test_agent_announces_then_claims_due_restart_once(self) -> None:
        _, requested = self.store.request("198.51.100.10", now=1000)
        job_id = requested["jobId"]

        action = self.store.next_agent_action(now=1000)
        self.assertEqual(action["action"], "announce_5_minutes")
        self.assertIsNone(self.store.next_agent_action(now=1001))

        action = self.store.next_agent_action(now=1240)
        self.assertEqual(action["action"], "announce_1_minute")
        action = self.store.next_agent_action(now=1270)
        self.assertEqual(action["action"], "announce_30_seconds")
        action = self.store.next_agent_action(now=1290)
        self.assertEqual(action["action"], "announce_10_seconds")

        action = self.store.next_agent_action(now=1300)
        self.assertEqual(action, {"action": "restart", "jobId": job_id})
        self.assertIsNone(self.store.next_agent_action(now=1301))

    def test_cancellation_is_announced_only_if_countdown_was_announced(
        self,
    ) -> None:
        self.store.request("198.51.100.10", now=1000)
        self.store.next_agent_action(now=1000)
        self.store.cancel(now=1001)
        action = self.store.next_agent_action(now=1002)
        self.assertEqual(action["action"], "announce_cancelled")
        self.assertIsNone(self.store.next_agent_action(now=1003))

    def test_successful_completion_enforces_thirty_minute_cooldown(
        self,
    ) -> None:
        _, requested = self.store.request("198.51.100.10", now=1000)
        self.store.next_agent_action(now=1300)
        outcome, status = self.store.complete(
            requested["jobId"],
            True,
            "server_ready",
            now=1400,
        )
        self.assertEqual(outcome, "completed")
        self.assertEqual(status["state"], "completed")
        self.assertEqual(status["cooldownRemainingSeconds"], 1800)

        outcome, status = self.store.request(
            "198.51.100.10",
            now=1401,
        )
        self.assertEqual(outcome, "cooldown")
        self.assertEqual(status["cooldownRemainingSeconds"], 1799)

        outcome, status = self.store.request(
            "198.51.100.10",
            now=3201,
        )
        self.assertEqual(outcome, "created")
        self.assertEqual(status["state"], "pending")

    def test_state_persists_when_store_is_reopened(self) -> None:
        _, requested = self.store.request("198.51.100.10", now=1000)
        reopened = RestartStore(self.database_path, delay_seconds=300)
        status = reopened.status(now=1100)
        self.assertEqual(status["jobId"], requested["jobId"])
        self.assertEqual(status["remainingSeconds"], 200)


class ActivityTests(unittest.TestCase):
    def test_chat_login_logout_and_death_are_filtered(self) -> None:
        entries = [
            {
                "id": 1,
                "msg": (
                    "Chat (from 'survivor', entity id '42', "
                    "to 'Global'): hello <script>"
                ),
                "type": "Log",
                "trace": "",
                "isotime": "2026-07-25T15:00:00.1234567+09:00",
                "uptime": 100,
            },
            {
                "id": 2,
                "msg": "GMSG: Player 'survivor' joined the game",
                "type": "Log",
                "trace": "",
                "isotime": "2026-07-25T15:01:00+09:00",
                "uptime": 160,
            },
            {
                "id": 3,
                "msg": "GMSG: Player 'survivor' left the game",
                "type": "Log",
                "trace": "",
                "isotime": "2026-07-25T15:02:00+09:00",
                "uptime": 220,
            },
            {
                "id": 4,
                "msg": "GMSG: Player 'survivor' died",
                "type": "Log",
                "trace": "",
                "isotime": "2026-07-25T15:03:00+09:00",
                "uptime": 280,
            },
        ]
        events = parse_activity_payload({"data": {"entries": entries}})
        self.assertEqual(
            [event["type"] for event in events],
            ["chat", "login", "logout", "death"],
        )
        self.assertEqual(events[0]["player"], "survivor")
        self.assertEqual(events[0]["message"], "hello <script>")
        self.assertNotIn("entity", json.dumps(events))
        self.assertNotIn("trace", json.dumps(events))

    def test_system_chat_is_kept_without_raw_log_fields(self) -> None:
        event = parse_activity_entry(
            {
                "id": 5,
                "msg": (
                    "Chat (from '-non-player-', entity id '-1', "
                    "to 'Global'): Server restart in 5 minutes."
                ),
                "type": "Log",
                "trace": "private trace",
                "isotime": "2026-07-25T15:04:00+09:00",
                "uptime": 340,
            }
        )
        self.assertIsNotNone(event)
        self.assertEqual(event["player"], "SERVER")
        self.assertEqual(
            event["message"],
            "Server restart in 5 minutes.",
        )
        self.assertNotIn("trace", event)

    def test_unrelated_or_invalid_entries_are_ignored(self) -> None:
        self.assertIsNone(
            parse_activity_entry(
                {
                    "id": 6,
                    "msg": "PlayerLogin: survivor/V 3.0.1",
                    "isotime": "2026-07-25T15:05:00+09:00",
                }
            )
        )
        self.assertIsNone(
            parse_activity_entry(
                {
                    "id": 7,
                    "msg": "GMSG: Player 'survivor' died",
                    "isotime": "not-a-time",
                }
            )
        )

    def test_store_deduplicates_persists_and_limits_events(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = (
                Path(temporary_directory) / "activity.sqlite3"
            )
            store = ActivityStore(
                database_path,
                retention_seconds=100,
                max_events=2,
            )
            events = [
                {
                    "eventKey": f"event-{index}",
                    "occurredAt": f"2026-07-25T15:0{index}:00+09:00",
                    "occurredEpoch": 1950 + index * 10,
                    "type": "login",
                    "player": f"player-{index}",
                    "message": "",
                }
                for index in range(3)
            ]
            self.assertEqual(store.ingest(events, now=2000), 3)
            self.assertEqual(store.ingest(events, now=2000), 1)
            stored = ActivityStore(database_path).recent()["events"]
            self.assertEqual(len(stored), 2)
            self.assertEqual(
                [event["player"] for event in stored],
                ["player-2", "player-1"],
            )


class ServerVersionTests(unittest.TestCase):
    def test_telnet_version_is_accepted(self) -> None:
        self.assertEqual(
            validate_server_version(" V 3.0.1 (b4) "),
            "V 3.0.1 (b4)",
        )

    def test_web_api_version_format_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_server_version("V.3.1.4")

    def test_version_is_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = (
                Path(temporary_directory) / "auth-state.sqlite3"
            )
            store = RestartStore(database_path)
            self.assertIsNone(store.server_version())
            published = store.publish_server_version(
                "V 3.0.1 (b4)",
                now=1234,
            )
            self.assertEqual(published["version"], "V 3.0.1 (b4)")
            self.assertEqual(
                RestartStore(database_path).server_version(),
                {
                    "version": "V 3.0.1 (b4)",
                    "updatedAt": 1234.0,
                },
            )


class GameScheduleTests(unittest.TestCase):
    def test_schedule_is_validated_and_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = (
                Path(temporary_directory) / "auth-state.sqlite3"
            )
            store = RestartStore(database_path)
            self.assertIsNone(store.game_schedule())
            schedule = {
                "mode": "weekday",
                "dayNightLengthMinutes": 120,
                "bloodMoonFrequencyDays": 7,
                "bloodMoonRangeDays": 0,
                "bloodMoonStartHour": 22,
            }
            published = store.publish_game_schedule(schedule, now=1234)
            self.assertEqual(published, {**schedule, "updatedAt": 1234})
            self.assertEqual(
                RestartStore(database_path).game_schedule(),
                {**schedule, "updatedAt": 1234.0},
            )

    def test_invalid_schedule_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_game_schedule(
                {
                    "mode": "unknown",
                    "dayNightLengthMinutes": 120,
                    "bloodMoonFrequencyDays": 7,
                    "bloodMoonRangeDays": 0,
                    "bloodMoonStartHour": 22,
                }
            )
        with self.assertRaises(ValueError):
            validate_game_schedule(
                {
                    "mode": "weekday",
                    "dayNightLengthMinutes": True,
                    "bloodMoonFrequencyDays": 7,
                    "bloodMoonRangeDays": 0,
                    "bloodMoonStartHour": 22,
                }
            )


class ServerStatusTests(unittest.TestCase):
    def test_status_is_validated_and_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "status.sqlite3"
            store = RestartStore(database_path)
            status = {
                "uptimeMinutes": 125.5,
                "fps": 20.0,
                "heapMb": 750.1,
                "maxMemoryMb": 1024.0,
                "rssMb": 2048.5,
                "chunks": 321,
                "players": 2,
                "zombies": 18,
                "entities": 140,
            }
            published = store.publish_server_status(status, now=1234)
            self.assertEqual(published["fps"], 20.0)
            self.assertEqual(
                RestartStore(database_path).server_status(),
                {**status, "updatedAt": 1234},
            )

    def test_invalid_status_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_server_status(
                {
                    "uptimeMinutes": 1,
                    "fps": float("nan"),
                    "heapMb": 1,
                    "maxMemoryMb": 1,
                    "rssMb": 1,
                    "chunks": 1,
                    "players": 1,
                    "zombies": 1,
                    "entities": 1,
                }
            )


class MapEntityTests(unittest.TestCase):
    def test_entities_are_filtered_labeled_and_persisted(self) -> None:
        entities = [
            {
                "entityId": 13057,
                "kind": "supply",
                "position": {"x": 1908.5, "y": 137, "z": -1100.2},
                "owner": "private",
            },
            {
                "entityId": "12895",
                "kind": "motorcycle",
                "position": {"x": 1655.3, "y": 38.1, "z": 302.1},
            },
            {
                "entityId": "5203252673",
                "kind": "trader_joel",
                "position": {"x": 2032, "y": 49, "z": 2673},
            },
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "entities.sqlite3"
            store = MapEntityStore(database_path)
            published = store.publish(entities, now=1234)
            self.assertEqual(published["lastCollectedAt"], 1234)
            self.assertNotIn("owner", json.dumps(published))

            current = MapEntityStore(database_path).current()
            self.assertEqual(current["lastCollectedAt"], 1234.0)
            self.assertEqual(
                [entity["label"] for entity in current["entities"]],
                ["オートバイ", "補給物資", "トレーダー・ジョエル"],
            )
            self.assertNotIn("owner", json.dumps(current))

    def test_snapshot_replaces_disappeared_entities(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = MapEntityStore(
                Path(temporary_directory) / "entities.sqlite3"
            )
            store.publish(
                [
                    {
                        "entityId": "1",
                        "kind": "drone",
                        "position": {"x": 1, "y": 2, "z": 3},
                    }
                ],
                now=1000,
            )
            store.publish([], now=1060)
            self.assertEqual(store.current()["entities"], [])

    def test_invalid_or_duplicate_entities_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_map_entities(
                [
                    {
                        "entityId": "1",
                        "kind": "player",
                        "position": {"x": 1, "y": 2, "z": 3},
                    }
                ]
            )

    def test_private_map_metadata_is_limited_to_private_kinds(self) -> None:
        entities = validate_map_entities(
            [
                {
                    "entityId": "1",
                    "kind": "bedroll",
                    "label": "survivor の寝袋",
                    "owner": "survivor",
                    "position": {"x": 1, "y": 2, "z": 3},
                },
                {
                    "entityId": "2",
                    "kind": "quest",
                    "label": "survivor のクエスト地点",
                    "owner": "survivor",
                    "detail": "POI",
                    "questCode": 99,
                    "position": {"x": 4, "y": 5, "z": 6},
                },
            ]
        )
        self.assertEqual(entities[0]["owner"], "survivor")
        self.assertEqual(entities[1]["questCode"], 99)
        with self.assertRaises(ValueError):
            validate_map_entities(
                [
                    {
                        "entityId": "1",
                        "kind": "drone",
                        "position": {"x": 1, "y": 2, "z": 3},
                    },
                    {
                        "entityId": "1",
                        "kind": "drone",
                        "position": {"x": 4, "y": 5, "z": 6},
                    },
                ]
            )


class PlayerPayloadTests(unittest.TestCase):
    def test_only_name_and_position_are_exposed(self) -> None:
        payload = {
            "data": {
                "players": [
                    {
                        "name": "survivor",
                        "position": {"x": 10.5, "y": 42, "z": -20.25},
                        "ip": "198.51.100.10",
                        "platformId": {"combinedString": "secret-id"},
                        "health": 100,
                    }
                ]
            },
            "meta": {"serverTime": "private"},
        }
        self.assertEqual(
            filtered_player_payload(payload),
            {
                "data": {
                    "players": [
                        {
                            "name": "survivor",
                            "position": {
                                "x": 10.5,
                                "y": 42,
                                "z": -20.25,
                            },
                        }
                    ]
                }
            },
        )


class PlayerStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self.temporary_directory.name) / "player-state.sqlite3"
        )
        self.store = PlayerStore(self.database_path)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_offline_profile_keeps_level_and_last_position(self) -> None:
        profiles = [
            {
                "name": "survivor",
                "level": 40,
                "profileSavedAt": 1234,
            }
        ]
        self.store.publish(
            profiles,
            [
                {
                    "name": "survivor",
                    "level": 40,
                    "position": {"x": 10.5, "y": 42, "z": -20.25},
                    "health": 92,
                    "maxHealth": 114,
                    "ping": 18,
                    "gameStage": 73,
                }
            ],
            now=1250,
        )
        current = self.store.publish(profiles, [], now=1300)
        player = current["roster"][0]
        self.assertFalse(player["online"])
        self.assertEqual(player["level"], 40)
        self.assertEqual(
            player["position"],
            {"x": 10.5, "y": 42.0, "z": -20.25},
        )
        self.assertEqual(player["lastPositionAt"], 1250)
        self.assertIsNone(player["health"])
        self.assertIsNone(player["maxHealth"])
        self.assertIsNone(player["ping"])
        self.assertIsNone(player["gameStage"])
        self.assertEqual(current["players"], [])

    def test_online_fields_are_exposed_without_ids(self) -> None:
        current = self.store.publish(
            [
                {
                    "name": "survivor",
                    "level": 40,
                    "profileSavedAt": 1234,
                }
            ],
            [
                {
                    "name": "survivor",
                    "level": 41,
                    "position": {"x": 1, "y": 2, "z": 3},
                    "health": 100,
                    "maxHealth": 120,
                    "ping": 25,
                    "gameStage": 81,
                    "platformId": "secret",
                    "ip": "198.51.100.10",
                }
            ],
            now=1300,
        )
        player = current["players"][0]
        self.assertTrue(player["online"])
        self.assertEqual(player["level"], 41)
        self.assertEqual(player["health"], 100)
        self.assertEqual(player["maxHealth"], 120)
        self.assertEqual(player["ping"], 25)
        self.assertEqual(player["gameStage"], 81)
        self.assertNotIn("platformId", json.dumps(current))
        self.assertNotIn("198.51.100.10", json.dumps(current))

    def test_player_validators_reject_duplicates_and_bad_values(self) -> None:
        with self.assertRaises(ValueError):
            validate_player_profiles(
                [
                    {"name": "same", "level": 1, "profileSavedAt": 1},
                    {"name": "SAME", "level": 2, "profileSavedAt": 2},
                ]
            )
        with self.assertRaises(ValueError):
            validate_online_players(
                [
                    {
                        "name": "survivor",
                        "position": {"x": float("nan"), "y": 2, "z": 3},
                    }
                ]
            )


class ClientIpTests(unittest.TestCase):
    def test_real_ip_is_trusted_from_docker_proxy_network(self) -> None:
        handler = SimpleNamespace(
            client_address=("172.20.0.5", 12345),
            headers={"X-Real-IP": "203.0.113.10"},
        )
        self.assertEqual(normalized_client_ip(handler), "203.0.113.10")

    def test_real_ip_is_ignored_for_direct_lan_connection(self) -> None:
        handler = SimpleNamespace(
            client_address=("192.0.2.10", 12345),
            headers={"X-Real-IP": "203.0.113.10"},
        )
        self.assertEqual(normalized_client_ip(handler), "192.0.2.10")


class HandlerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        database_path = (
            Path(self.temporary_directory.name) / "gateway.sqlite3"
        )
        MapGatewayHandler.auth_store = AuthStore(database_path)
        MapGatewayHandler.activity_store = ActivityStore(database_path)
        MapGatewayHandler.entity_store = MapEntityStore(database_path)
        MapGatewayHandler.player_store = PlayerStore(database_path)
        MapGatewayHandler.restart_store = RestartStore(
            database_path,
            delay_seconds=300,
        )
        MapGatewayHandler.biome_path = (
            Path(self.temporary_directory.name) / "biomes.png"
        )
        MapGatewayHandler.expected_password_hash = parse_password_hash(
            generate_password_hash(
                "correct",
                iterations=1000,
                salt=b"0123456789abcdef",
            )
        )
        MapGatewayHandler.agent_token = "a" * 64
        MapGatewayHandler.restart_enabled = True
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            MapGatewayHandler,
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        self.base_url = (
            f"http://127.0.0.1:{self.server.server_address[1]}"
        )
        self.authorization = CredentialTests.authorization(
            "map",
            "correct",
        )

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary_directory.cleanup()

    def request(
        self,
        path: str,
        method: str = "GET",
        payload: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, object]]:
        request_headers = {"Accept": "application/json"}
        request_headers.update(headers or {})
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers=request_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.loads(error.read())
            finally:
                error.close()

    def test_authenticated_request_and_cancel_flow(self) -> None:
        headers = {"Authorization": self.authorization}
        code, payload = self.request(
            "/api/auth/check",
            headers=headers,
        )
        self.assertEqual(code, 200)
        self.assertTrue(payload["data"]["authenticated"])

        code, payload = self.request(
            "/api/restart/request",
            method="POST",
            payload={"confirmation": "RESTART"},
            headers=headers,
        )
        self.assertEqual(code, 201)
        self.assertEqual(payload["data"]["state"], "pending")

        code, payload = self.request(
            "/api/restart/cancel",
            method="POST",
            payload={},
            headers=headers,
        )
        self.assertEqual(code, 200)
        self.assertEqual(payload["data"]["state"], "cancelled")

    def test_restart_is_disabled_by_default_configuration(self) -> None:
        MapGatewayHandler.restart_enabled = False
        try:
            code, payload = self.request("/api/features")
            self.assertEqual(code, 200)
            self.assertFalse(payload["data"]["restart"])

            code, payload = self.request(
                "/api/restart/request",
                method="POST",
                payload={"confirmation": "RESTART"},
                headers={"Authorization": self.authorization},
            )
            self.assertEqual(code, 404)
            self.assertEqual(payload["error"], "not_found")

            code, payload = self.request(
                "/internal/restart/agent",
                headers={"X-Restart-Agent-Token": "a" * 64},
            )
            self.assertEqual(code, 404)
            self.assertEqual(payload["error"], "not_found")
        finally:
            MapGatewayHandler.restart_enabled = True

    def test_restart_requires_exact_confirmation(self) -> None:
        code, payload = self.request(
            "/api/restart/request",
            method="POST",
            payload={"confirmation": "restart"},
            headers={"Authorization": self.authorization},
        )
        self.assertEqual(code, 400)
        self.assertEqual(payload["error"], "confirmation_required")
        self.assertEqual(
            MapGatewayHandler.restart_store.status()["state"],
            "idle",
        )

    def test_internal_agent_rejects_wrong_token(self) -> None:
        code, payload = self.request(
            "/internal/restart/agent",
            headers={"X-Restart-Agent-Token": "wrong"},
        )
        self.assertEqual(code, 401)
        self.assertEqual(payload["error"], "unauthorized")

    def test_runtime_version_publish_and_public_read(self) -> None:
        code, payload = self.request("/api/server-version")
        self.assertEqual(code, 503)
        self.assertEqual(payload["error"], "version_unavailable")

        code, payload = self.request(
            "/internal/server-version",
            method="POST",
            payload={"version": "V 3.0.1 (b4)"},
            headers={"X-Restart-Agent-Token": "a" * 64},
        )
        self.assertEqual(code, 200)
        self.assertEqual(payload["data"]["version"], "V 3.0.1 (b4)")

        code, payload = self.request("/api/server-version")
        self.assertEqual(code, 200)
        self.assertEqual(payload["data"]["version"], "V 3.0.1 (b4)")

    def test_runtime_version_rejects_wrong_token_and_format(self) -> None:
        code, payload = self.request(
            "/internal/server-version",
            method="POST",
            payload={"version": "V 3.0.1 (b4)"},
            headers={"X-Restart-Agent-Token": "wrong"},
        )
        self.assertEqual(code, 401)
        self.assertEqual(payload["error"], "unauthorized")

        code, payload = self.request(
            "/internal/server-version",
            method="POST",
            payload={"version": "V.3.1.4"},
            headers={"X-Restart-Agent-Token": "a" * 64},
        )
        self.assertEqual(code, 400)
        self.assertEqual(payload["error"], "invalid_server_version")

    def test_runtime_schedule_publish_and_public_read(self) -> None:
        code, payload = self.request("/api/game-schedule")
        self.assertEqual(code, 503)
        self.assertEqual(payload["error"], "schedule_unavailable")

        schedule = {
            "mode": "weekday",
            "dayNightLengthMinutes": 120,
            "bloodMoonFrequencyDays": 7,
            "bloodMoonRangeDays": 0,
            "bloodMoonStartHour": 22,
        }
        code, payload = self.request(
            "/internal/game-schedule",
            method="POST",
            payload=schedule,
            headers={"X-Restart-Agent-Token": "a" * 64},
        )
        self.assertEqual(code, 200)
        self.assertEqual(payload["data"]["mode"], "weekday")

        code, payload = self.request("/api/game-schedule")
        self.assertEqual(code, 200)
        self.assertEqual(
            payload["data"]["dayNightLengthMinutes"],
            120,
        )

    def test_runtime_schedule_rejects_invalid_payload(self) -> None:
        code, payload = self.request(
            "/internal/game-schedule",
            method="POST",
            payload={
                "mode": "holiday",
                "dayNightLengthMinutes": 0,
                "bloodMoonFrequencyDays": 7,
                "bloodMoonRangeDays": 0,
                "bloodMoonStartHour": 22,
            },
            headers={"X-Restart-Agent-Token": "a" * 64},
        )
        self.assertEqual(code, 400)
        self.assertEqual(payload["error"], "invalid_game_schedule")

    def test_server_status_publish_and_authenticated_read(self) -> None:
        status = {
            "uptimeMinutes": 125.5,
            "fps": 20.0,
            "heapMb": 750.1,
            "maxMemoryMb": 1024.0,
            "rssMb": 2048.5,
            "chunks": 321,
            "players": 2,
            "zombies": 18,
            "entities": 140,
        }
        code, _ = self.request(
            "/internal/server-status",
            method="POST",
            payload=status,
            headers={"X-Restart-Agent-Token": "a" * 64},
        )
        self.assertEqual(code, 200)

        code, payload = self.request("/api/server-status")
        self.assertEqual(code, 401)
        code, payload = self.request(
            "/api/server-status",
            headers={"Authorization": self.authorization},
        )
        self.assertEqual(code, 200)
        self.assertEqual(payload["data"]["fps"], 20.0)

    def test_biome_publish_and_authenticated_read(self) -> None:
        image = (
            b"\x89PNG\r\n\x1a\n"
            + b"\x00\x00\x00\rIHDR"
            + (768).to_bytes(4, "big")
            + (768).to_bytes(4, "big")
            + b"\x08\x06\x00\x00\x00"
        )
        code, payload = self.request(
            "/internal/biome",
            method="POST",
            payload={"pngBase64": base64.b64encode(image).decode("ascii")},
            headers={"X-Restart-Agent-Token": "a" * 64},
        )
        self.assertEqual(code, 200)
        self.assertEqual(payload["data"]["width"], 768)

        request = urllib.request.Request(
            self.base_url + "/api/biome",
            headers={"Authorization": self.authorization},
        )
        with urllib.request.urlopen(request, timeout=2) as response:
            self.assertEqual(response.headers["Content-Type"], "image/png")
            self.assertEqual(response.read(), image)

    def test_map_entities_require_auth_and_hide_internal_fields(self) -> None:
        code, payload = self.request("/api/map-entities")
        self.assertEqual(code, 401)
        self.assertEqual(payload["error"], "invalid_passphrase")

        code, payload = self.request(
            "/internal/map-entities",
            method="POST",
            payload={
                "entities": [
                    {
                        "entityId": "13057",
                        "kind": "supply",
                        "position": {
                            "x": 1908.5,
                            "y": 137,
                            "z": -1100.2,
                        },
                        "rawType": "EntitySupplyCrate",
                    }
                ]
            },
            headers={"X-Restart-Agent-Token": "a" * 64},
        )
        self.assertEqual(code, 200)
        self.assertNotIn("rawType", json.dumps(payload))

        code, payload = self.request(
            "/api/map-entities",
            headers={"Authorization": self.authorization},
        )
        self.assertEqual(code, 200)
        self.assertEqual(payload["data"]["entities"][0]["label"], "補給物資")
        self.assertNotIn("rawType", json.dumps(payload))

    def test_map_entities_reject_wrong_token_and_invalid_kind(self) -> None:
        code, payload = self.request(
            "/internal/map-entities",
            method="POST",
            payload={"entities": []},
            headers={"X-Restart-Agent-Token": "wrong"},
        )
        self.assertEqual(code, 401)
        self.assertEqual(payload["error"], "unauthorized")

        code, payload = self.request(
            "/internal/map-entities",
            method="POST",
            payload={
                "entities": [
                    {
                        "entityId": "1",
                        "kind": "player",
                        "position": {"x": 1, "y": 2, "z": 3},
                    }
                ]
            },
            headers={"X-Restart-Agent-Token": "a" * 64},
        )
        self.assertEqual(code, 400)
        self.assertEqual(payload["error"], "invalid_map_entities")

    def test_player_snapshot_requires_agent_and_public_read_requires_auth(
        self,
    ) -> None:
        snapshot = {
            "profiles": [
                {
                    "name": "survivor",
                    "level": 40,
                    "profileSavedAt": 1234,
                }
            ],
            "onlinePlayers": [
                {
                    "name": "survivor",
                    "level": 40,
                    "position": {"x": 1, "y": 2, "z": 3},
                    "health": 100,
                    "maxHealth": 120,
                    "ping": 25,
                    "gameStage": 75,
                    "platformId": "secret",
                }
            ],
        }
        code, payload = self.request(
            "/internal/player-snapshot",
            method="POST",
            payload=snapshot,
            headers={"X-Restart-Agent-Token": "wrong"},
        )
        self.assertEqual(code, 401)
        self.assertEqual(payload["error"], "unauthorized")

        code, payload = self.request(
            "/internal/player-snapshot",
            method="POST",
            payload=snapshot,
            headers={"X-Restart-Agent-Token": "a" * 64},
        )
        self.assertEqual(code, 200)
        self.assertNotIn("platformId", json.dumps(payload))

        code, payload = self.request("/api/player")
        self.assertEqual(code, 401)
        self.assertEqual(payload["error"], "invalid_passphrase")

        code, payload = self.request(
            "/api/player",
            headers={"Authorization": self.authorization},
        )
        self.assertEqual(code, 200)
        self.assertEqual(payload["data"]["roster"][0]["level"], 40)
        self.assertEqual(payload["data"]["players"][0]["gameStage"], 75)

    def test_activity_requires_auth_and_returns_filtered_history(self) -> None:
        MapGatewayHandler.activity_store.ingest(
            [
                {
                    "eventKey": "event-1",
                    "occurredAt": "2026-07-25T15:00:00+09:00",
                    "occurredEpoch": 1784959200,
                    "type": "death",
                    "player": "survivor",
                    "message": "",
                }
            ],
            now=1784959200,
        )
        code, payload = self.request("/api/activity")
        self.assertEqual(code, 401)
        self.assertEqual(payload["error"], "invalid_passphrase")

        code, payload = self.request(
            "/api/activity",
            headers={"Authorization": self.authorization},
        )
        self.assertEqual(code, 200)
        self.assertEqual(
            payload["data"]["events"],
            [
                {
                    "occurredAt": "2026-07-25T15:00:00+09:00",
                    "type": "death",
                    "player": "survivor",
                    "message": "",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
