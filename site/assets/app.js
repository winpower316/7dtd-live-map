(() => {
  "use strict";

  const runtimeConfig = window.LIVE_MAP_CONFIG || {};
  const configNumber = (name, fallback, minimum = 0) => {
    const value = Number(runtimeConfig[name]);
    return Number.isFinite(value) && value >= minimum ? value : fallback;
  };
  const configInteger = (name, fallback, minimum = 0) => {
    const value = configNumber(name, fallback, minimum);
    return Number.isInteger(value) ? value : fallback;
  };
  const configIntegerList = (name, fallback) => {
    const rawValue = runtimeConfig[name];
    const values = Array.isArray(rawValue)
      ? rawValue
      : String(rawValue || "").split(",");
    const normalized = values.map(Number);
    return normalized.length > 0
      && normalized.every((value) => Number.isInteger(value) && value >= 0)
      ? normalized
      : fallback;
  };
  const configString = (name, fallback = "") => {
    const value = String(runtimeConfig[name] || "").trim();
    return value || fallback;
  };

  const MAP_NATIVE_MAX_ZOOM = configInteger("mapNativeMaxZoom", 4);
  const MAP_TILE_SIZE = configInteger("mapTileSize", 128, 32);
  const MAP_SCALE_DIVISOR = 2 ** MAP_NATIVE_MAX_ZOOM;
  const CONFIG_URL = "/api/map/config";
  const STATS_URL = "/api/serverstats";
  const PLAYERS_URL = "/api/player";
  const ACTIVITY_URL = "/api/activity";
  const MAP_ENTITIES_URL = "/api/map-entities";
  const BIOME_URL = "/api/biome";
  const SERVER_STATUS_URL = "/api/server-status";
  const AUTH_CHECK_URL = "/api/auth/check";
  const FEATURES_URL = "/api/features";
  const SERVER_VERSION_URL = "/api/server-version";
  const GAME_SCHEDULE_URL = "/api/game-schedule";
  const RESTART_STATUS_URL = "/api/restart/status";
  const RESTART_REQUEST_URL = "/api/restart/request";
  const RESTART_CANCEL_URL = "/api/restart/cancel";
  const APP_VERSION_URL = "/version.json";
  const APP_VERSION = "0.2.1";
  const GAME_TIME_REFRESH_MS = configInteger(
    "gameTimeRefreshMs", 10_000, 1_000
  );
  const PLAYER_REFRESH_MS = configInteger(
    "playerRefreshMs", 10_000, 1_000
  );
  const ACTIVITY_REFRESH_MS = configInteger(
    "activityRefreshMs", 10_000, 1_000
  );
  const MAP_ENTITY_REFRESH_MS = configInteger(
    "mapEntityRefreshMs", 10_000, 1_000
  );
  const TRADER_EXPLORATION_REFRESH_MS = configInteger(
    "traderExplorationRefreshMs", 5_000, 1_000
  );
  const SERVER_VERSION_REFRESH_MS = configInteger(
    "serverVersionRefreshMs", 60_000, 1_000
  );
  const APP_VERSION_REFRESH_MS = configInteger(
    "appVersionRefreshMs", 60_000, 1_000
  );
  const GAME_SCHEDULE_REFRESH_MS = configInteger(
    "gameScheduleRefreshMs", 60_000, 1_000
  );
  const RESTART_STATUS_REFRESH_MS = configInteger(
    "restartStatusRefreshMs", 5_000, 1_000
  );
  const PLAYER_AUTH_STORAGE_KEY = "7dtd-map-player-auth";
  const PLAYER_FOLLOW_STORAGE_KEY = "7dtd-map-player-follow";
  const APP_RELOAD_VIEW_STORAGE_KEY = "7dtd-map-reload-view";
  const GUIDE_SEEN_STORAGE_KEY = "7dtd-map-guide-seen-v1";
  const UNEXPLORED_TILE_MAX_BYTES = configInteger(
    "unexploredTileMaxBytes", 400, 1
  );
  const TILE_RETRY_DELAYS_MS = configIntegerList(
    "tileRetryDelaysMs", [0, 250, 750, 1500]
  );
  const CONFIG_RETRY_DELAYS_MS = configIntegerList(
    "configRetryDelaysMs", [0, 300, 900]
  );
  const UNEXPLORED_TILE_REFRESH_MS = configInteger(
    "unexploredTileRefreshMs", 5_000, 1_000
  );
  const MOVING_PLAYER_MIN_SPEED_MPS = configNumber(
    "movingPlayerMinSpeedMps", 4
  );
  const MOVING_VEHICLE_MATCH_RADIUS = configNumber(
    "movingVehicleMatchRadius", 160, 1
  );
  const MOVING_VEHICLE_RELEASE_MS = configInteger(
    "movingVehicleReleaseMs", 20_000, 1_000
  );
  const MAINTENANCE_TIME_ZONE = configString(
    "maintenanceTimeZone", "UTC"
  );
  const MAINTENANCE_WINDOWS = runtimeConfig.maintenanceWindows || "";
  const TRANSPARENT_TILE = "data:image/gif;base64,R0lGODlhAQABAAD/ACwAAAAAAQABAAACADs=";
  const BICYCLE_ICON = `
    <svg class="map-entity-symbol" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="5" cy="17" r="3.2"></circle>
      <circle cx="19" cy="17" r="3.2"></circle>
      <path d="M5 17l4-7 4 7m-8 0h8l-4-7h6l4 7M8 7h3"></path>
    </svg>`;
  const MOTORCYCLE_ICON = `
    <svg class="map-entity-symbol" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="5" cy="17" r="3.2"></circle>
      <circle cx="19" cy="17" r="3.2"></circle>
      <path d="M5 17h6l3-5h3l2 5M9 17l-2-5h5l2 2M15 9h3"></path>
    </svg>`;
  const FOUR_BY_FOUR_ICON = `
    <svg class="map-entity-symbol" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3 9h12l3 3h3v5H3zM6 9l2-4h7v4"></path>
      <circle cx="7" cy="18" r="2"></circle>
      <circle cx="18" cy="18" r="2"></circle>
    </svg>`;
  const GYROCOPTER_ICON = `
    <svg class="map-entity-symbol" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3 5h18M12 5v8m-5 4h10l3-4h-8l-3 4-4-1"></path>
      <circle cx="8" cy="19" r="1.7"></circle>
      <circle cx="17" cy="19" r="1.7"></circle>
    </svg>`;
  const VEHICLE_ICON = `
    <svg class="map-entity-symbol" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M3 11l3-5h11l4 5v6H3zM6 11h12"></path>
      <circle cx="7" cy="18" r="2"></circle>
      <circle cx="18" cy="18" r="2"></circle>
    </svg>`;
  const TRADER_ICON = `
    <svg class="map-entity-symbol" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 10h16l-2-5H6zM6 10v9h12v-9M9 19v-5h6v5"></path>
      <path d="M5 10c0 2 3 2 3 0 0 2 4 2 4 0 0 2 4 2 4 0 0 2 3 2 3 0"></path>
    </svg>`;
  const MAP_ENTITY_SPECS = Object.freeze({
    supply: { symbol: "▣", label: "補給物資" },
    drone: { symbol: "✦", label: "ドローン" },
    trader_joel: { icon: TRADER_ICON, label: "トレーダー・ジョエル" },
    trader_jen: { icon: TRADER_ICON, label: "トレーダー・ジェン" },
    trader_bob: { icon: TRADER_ICON, label: "トレーダー・ボブ" },
    trader_hugh: { icon: TRADER_ICON, label: "トレーダー・ヒュー" },
    trader_rekt: { icon: TRADER_ICON, label: "トレーダー・レクト" },
    bicycle: { icon: BICYCLE_ICON, label: "自転車" },
    minibike: { icon: MOTORCYCLE_ICON, label: "ミニバイク" },
    motorcycle: { icon: MOTORCYCLE_ICON, label: "オートバイ" },
    four_by_four: { icon: FOUR_BY_FOUR_ICON, label: "4x4トラック" },
    gyrocopter: { icon: GYROCOPTER_ICON, label: "ジャイロコプター" },
    vehicle: { icon: VEHICLE_ICON, label: "車両" },
    bedroll: { symbol: "⌂", label: "寝袋" },
    quest: { symbol: "!", label: "クエスト地点" },
    shared_waypoint: { symbol: "◆", label: "共有地点" },
  });
  const VEHICLE_ENTITY_KINDS = new Set([
    "bicycle",
    "minibike",
    "motorcycle",
    "four_by_four",
    "gyrocopter",
    "vehicle",
  ]);
  const TRADER_ENTITY_KINDS = new Set([
    "trader_joel",
    "trader_jen",
    "trader_bob",
    "trader_hugh",
    "trader_rekt",
  ]);
  const OPTIONAL_ENTITY_KINDS = new Set([
    "bedroll",
    "quest",
    "shared_waypoint",
  ]);

  const elements = {
    statusDot: document.querySelector("#status-dot"),
    statusText: document.querySelector("#status-text"),
    serverVersion: document.querySelector("#server-version"),
    serverStatusControl: document.querySelector("#server-status-control"),
    serverStatusDialog: document.querySelector("#server-status-dialog"),
    serverStatusClose: document.querySelector("#server-status-close"),
    serverDetailState: document.querySelector("#server-detail-state"),
    serverDetailVersion: document.querySelector("#server-detail-version"),
    serverDetailTime: document.querySelector("#server-detail-time"),
    serverDetailPlayers: document.querySelector("#server-detail-players"),
    serverDetailUptime: document.querySelector("#server-detail-uptime"),
    serverDetailFps: document.querySelector("#server-detail-fps"),
    serverDetailMemory: document.querySelector("#server-detail-memory"),
    serverDetailEntities: document.querySelector("#server-detail-entities"),
    serverDetailUpdated: document.querySelector("#server-detail-updated"),
    gameTime: document.querySelector(".game-time"),
    gameDay: document.querySelector("#game-day"),
    gameClock: document.querySelector("#game-clock"),
    gameMode: document.querySelector("#game-mode"),
    hordeDay: document.querySelector("#horde-day"),
    hordeCountdown: document.querySelector("#horde-countdown"),
    hordeEta: document.querySelector("#horde-eta"),
    playerAccess: document.querySelector("#player-access"),
    playerFollowShell: document.querySelector("#player-follow-shell"),
    playerFollow: document.querySelector("#player-follow"),
    playerDialog: document.querySelector("#player-dialog"),
    playerForm: document.querySelector("#player-form"),
    playerPassphrase: document.querySelector("#player-passphrase"),
    playerError: document.querySelector("#player-error"),
    playerCancel: document.querySelector("#player-cancel"),
    activityControl: document.querySelector("#activity-control"),
    activityDialog: document.querySelector("#activity-dialog"),
    activityClose: document.querySelector("#activity-close"),
    activityRefresh: document.querySelector("#activity-refresh"),
    activityStatus: document.querySelector("#activity-status"),
    activityList: document.querySelector("#activity-list"),
    activityEmpty: document.querySelector("#activity-empty"),
    activityFilters: document.querySelectorAll("[data-activity-filter]"),
    playerInfoControl: document.querySelector("#player-info-control"),
    playerInfoDialog: document.querySelector("#player-info-dialog"),
    playerInfoClose: document.querySelector("#player-info-close"),
    playerInfoStatus: document.querySelector("#player-info-status"),
    playerInfoBody: document.querySelector("#player-info-body"),
    playerInfoEmpty: document.querySelector("#player-info-empty"),
    layersControl: document.querySelector("#layers-control"),
    layersDialog: document.querySelector("#layers-dialog"),
    layersClose: document.querySelector("#layers-close"),
    layerInputs: document.querySelectorAll("[data-map-layer]"),
    layerPlayerFilter: document.querySelector("#layer-player-filter"),
    biomeOpacity: document.querySelector("#biome-opacity"),
    layersStatus: document.querySelector("#layers-status"),
    restartControl: document.querySelector("#restart-control"),
    restartDialog: document.querySelector("#restart-dialog"),
    restartForm: document.querySelector("#restart-form"),
    restartConfirmation: document.querySelector("#restart-confirmation"),
    restartError: document.querySelector("#restart-error"),
    restartDialogCancel: document.querySelector("#restart-dialog-cancel"),
    loadingPanel: document.querySelector("#loading-panel"),
    loadingTitle: document.querySelector("#loading-title"),
    loadingMessage: document.querySelector("#loading-message"),
    retryButton: document.querySelector("#retry-button"),
    coordinates: document.querySelector("#coordinates"),
    zoomIn: document.querySelector("#zoom-in"),
    zoomOut: document.querySelector("#zoom-out"),
    resetView: document.querySelector("#reset-view"),
    guideControl: document.querySelector("#guide-control"),
    guideDialog: document.querySelector("#guide-dialog"),
    guideClose: document.querySelector("#guide-close"),
    guideStart: document.querySelector("#guide-start"),
  };

  let map = null;
  let worldBounds = null;
  let gameTimeTimer = null;
  let gameScheduleTimer = null;
  let serverVersionTimer = null;
  let appVersionTimer = null;
  let appVersionCheckInFlight = false;
  let appReloadRequested = false;
  let playerLayer = null;
  let mapEntityLayer = null;
  let biomeLayer = null;
  let biomeImage = null;
  let biomeObjectUrl = null;
  let worldWidth = 6144;
  let worldDepth = 6144;
  let playerTimer = null;
  let mapEntityTimer = null;
  let traderExplorationTimer = null;
  let traderExplorationCheckInFlight = false;
  let activityTimer = null;
  let restartTimer = null;
  let playerAuth = sessionStorage.getItem(PLAYER_AUTH_STORAGE_KEY);
  let authValidated = false;
  let playerCount = 0;
  let playersVisible = false;
  let activityEvents = [];
  let activityFilter = "all";
  let restartState = "idle";
  let restartEnabled = false;
  let latestGameTime = null;
  let gameSchedule = null;
  let latestPlayers = [];
  let latestPlayerRoster = [];
  let latestPlayerRosterCollectedAt = null;
  let latestMapEntities = [];
  let latestMapEntitiesCollectedAt = null;
  let latestServerStatus = null;
  const mapLayerVisibility = {
    shared_waypoint: false,
    quest: false,
    bedroll: false,
    biome: false,
  };
  const movingVehicleAssociations = new Map();
  const traderExplorationStates = new Map();
  const unexploredTileRefreshTimers = new WeakMap();
  let followedPlayerName = sessionStorage.getItem(
    PLAYER_FOLLOW_STORAGE_KEY,
  ) || "";

  const projection = {
    project(latlng) {
      return L.point(
        latlng.lat / MAP_SCALE_DIVISOR,
        latlng.lng / MAP_SCALE_DIVISOR,
      );
    },
    unproject(point) {
      return L.latLng(
        point.x * MAP_SCALE_DIVISOR,
        point.y * MAP_SCALE_DIVISOR,
      );
    },
  };

  const gameCrs = L.extend({}, L.CRS.Simple, {
    projection,
    transformation: new L.Transformation(1, 0, -1, 0),
    scale(zoom) {
      return 2 ** zoom;
    },
    zoom(scale) {
      return Math.log(scale) / Math.LN2;
    },
  });

  function setStatus(state, message) {
    elements.statusDot.className = `status-dot is-${state}`;
    elements.statusText.textContent = message;
  }

  function showError(
    message,
    title = "地図を取得できません",
    status = "MAP OFFLINE",
  ) {
    setStatus("offline", status);
    elements.loadingPanel.classList.remove("is-hidden");
    elements.loadingTitle.textContent = title;
    elements.loadingMessage.textContent = message;
    elements.retryButton.hidden = false;
  }

  function formatCoordinate(value, positive, negative) {
    const rounded = Math.floor(value);
    return `${Math.abs(rounded).toLocaleString("ja-JP")} ${rounded >= 0 ? positive : negative}`;
  }

  function updateCoordinates(latlng) {
    if (!latlng) {
      elements.coordinates.textContent = "E — / N —";
      return;
    }

    const eastWest = formatCoordinate(latlng.lat, "E", "W");
    const northSouth = formatCoordinate(latlng.lng, "N", "S");
    elements.coordinates.textContent = `${eastWest} / ${northSouth}`;
  }

  function formatRealDuration(totalMinutes) {
    const minutes = Math.max(0, Math.ceil(totalMinutes));
    const days = Math.floor(minutes / 1440);
    const hours = Math.floor((minutes % 1440) / 60);
    const remainder = minutes % 60;

    if (days > 0) {
      return `あと${days}日${hours}時間`;
    }
    if (hours > 0) {
      return `あと${hours}時間${remainder}分`;
    }
    return `あと${remainder}分`;
  }

  function renderHordeEstimate() {
    if (!latestGameTime || !gameSchedule) {
      return;
    }

    const day = Number(latestGameTime.days);
    const hours = Number(latestGameTime.hours);
    const minutes = Number(latestGameTime.minutes);
    const dayLength = Number(gameSchedule.dayNightLengthMinutes);
    const frequency = Number(gameSchedule.bloodMoonFrequencyDays);
    const range = Number(gameSchedule.bloodMoonRangeDays);
    const startHour = Number(gameSchedule.bloodMoonStartHour);

    if (
      ![day, hours, minutes, dayLength, frequency, range, startHour]
        .every(Number.isFinite)
      || day < 0
      || dayLength <= 0
      || frequency <= 0
    ) {
      return;
    }

    const currentGameMinute = hours * 60 + minutes;
    const hordeStartMinute = startHour * 60;
    let nextHordeDay = Math.max(
      frequency,
      Math.ceil(day / frequency) * frequency,
    );
    if (
      nextHordeDay === day
      && currentGameMinute >= hordeStartMinute
    ) {
      nextHordeDay += frequency;
    }

    const remainingGameMinutes = (
      (nextHordeDay - day) * 1440
      + hordeStartMinute
      - currentGameMinute
    );
    const remainingRealMinutes = (
      remainingGameMinutes * dayLength / 1440
    );
    const estimatedAt = new Date(
      Date.now() + remainingRealMinutes * 60_000,
    );
    const modeLabel = gameSchedule.mode === "holiday"
      ? "休日モード"
      : gameSchedule.mode === "weekday"
        ? "平日モード"
        : "カスタム";
    const rangeLabel = range > 0 ? ` ±${range}` : "";

    elements.gameMode.textContent = `${modeLabel} · 1日${dayLength}分`;
    elements.hordeDay.textContent = `DAY ${nextHordeDay}${rangeLabel}`;
    elements.hordeCountdown.textContent = formatRealDuration(
      remainingRealMinutes,
    );
    elements.hordeEta.textContent = `${
      new Intl.DateTimeFormat("ja-JP", {
        month: "numeric",
        day: "numeric",
        weekday: "short",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(estimatedAt)
    }ごろ`;
  }

  function renderGameTime(gameTime) {
    const day = Number(gameTime?.days);
    const hours = Number(gameTime?.hours);
    const minutes = Number(gameTime?.minutes);

    if (![day, hours, minutes].every(Number.isFinite)) {
      throw new Error("Invalid game time");
    }

    elements.gameDay.textContent = `DAY ${day}`;
    elements.gameClock.textContent = `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
    elements.serverDetailTime.textContent = (
      `DAY ${day} · ${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`
    );
    latestGameTime = { days: day, hours, minutes };
    renderHordeEstimate();
    elements.gameTime.classList.remove("is-stale");
  }

  async function updateGameTime() {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 5000);

    try {
      const response = await fetch(STATS_URL, {
        headers: { Accept: "application/json" },
        cache: "no-store",
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const payload = await response.json();
      renderGameTime(payload?.data?.gameTime);
      const publicPlayers = Number(payload?.data?.players);
      if (Number.isFinite(publicPlayers)) {
        elements.serverDetailPlayers.textContent = String(publicPlayers);
      }
      elements.serverDetailState.textContent = "オンライン";
    } catch {
      elements.gameTime.classList.add("is-stale");
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function startGameTimeUpdates() {
    if (gameTimeTimer !== null) {
      return;
    }

    updateGameTime();
    gameTimeTimer = window.setInterval(updateGameTime, GAME_TIME_REFRESH_MS);
  }

  async function updateGameSchedule() {
    try {
      const response = await fetch(GAME_SCHEDULE_URL, {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = await response.json();
      gameSchedule = payload?.data || null;
      renderHordeEstimate();
    } catch {
      elements.gameMode.textContent = "MODE —";
      elements.hordeDay.textContent = "DAY —";
      elements.hordeCountdown.textContent = "計算できません";
      elements.hordeEta.textContent = "設定取得待機中";
    }
  }

  function startGameScheduleUpdates() {
    if (gameScheduleTimer !== null) {
      return;
    }
    updateGameSchedule();
    gameScheduleTimer = window.setInterval(
      updateGameSchedule,
      GAME_SCHEDULE_REFRESH_MS,
    );
  }

  async function updateServerVersion() {
    try {
      const response = await fetch(SERVER_VERSION_URL, {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = await response.json();
      const version = String(payload?.data?.version || "").trim();
      if (!version) {
        throw new Error("Version is missing");
      }
      elements.serverVersion.textContent = `SERVER ${version}`;
      elements.serverDetailVersion.textContent = version;
      elements.serverVersion.classList.remove("is-stale");
    } catch {
      elements.serverVersion.textContent = "SERVER V—";
      elements.serverVersion.classList.add("is-stale");
    }
  }

  function startServerVersionUpdates() {
    if (serverVersionTimer !== null) {
      return;
    }
    updateServerVersion();
    serverVersionTimer = window.setInterval(
      updateServerVersion,
      SERVER_VERSION_REFRESH_MS,
    );
  }

  function formatStatusDuration(minutesValue) {
    const minutes = Number(minutesValue);
    if (!Number.isFinite(minutes)) {
      return "—";
    }
    const days = Math.floor(minutes / 1440);
    const hours = Math.floor((minutes % 1440) / 60);
    const remainder = Math.floor(minutes % 60);
    return `${days > 0 ? `${days}日 ` : ""}${hours}時間 ${remainder}分`;
  }

  function renderServerStatus(status) {
    latestServerStatus = status;
    elements.serverDetailUptime.textContent = formatStatusDuration(
      status?.uptimeMinutes,
    );
    elements.serverDetailFps.textContent = Number.isFinite(Number(status?.fps))
      ? `${Number(status.fps).toFixed(2)} FPS`
      : "—";
    elements.serverDetailMemory.textContent = (
      Number.isFinite(Number(status?.rssMb))
        ? `RSS ${Number(status.rssMb).toFixed(1)} MB · HEAP ${Number(status.heapMb).toFixed(1)} MB`
        : "—"
    );
    elements.serverDetailPlayers.textContent = Number.isFinite(
      Number(status?.players),
    ) ? String(Number(status.players)) : elements.serverDetailPlayers.textContent;
    elements.serverDetailEntities.textContent = (
      Number.isFinite(Number(status?.zombies))
      && Number.isFinite(Number(status?.entities))
        ? `${Number(status.zombies)} / ${Number(status.entities)}`
        : "—"
    );
    elements.serverDetailUpdated.textContent = formatPlayerTimestamp(
      status?.updatedAt,
    );
  }

  async function updateDetailedServerStatus() {
    if (!playerAuth || !authValidated) {
      return;
    }
    try {
      const response = await fetch(SERVER_STATUS_URL, {
        headers: {
          Accept: "application/json",
          Authorization: playerAuth,
        },
        cache: "no-store",
      });
      if (await handleAuthenticationFailure(response, false)) {
        return;
      }
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = await response.json();
      renderServerStatus(payload?.data || null);
    } catch {
      elements.serverDetailUpdated.textContent = "詳細統計を取得できません";
    }
  }

  async function checkAppVersion() {
    if (appVersionCheckInFlight || appReloadRequested) {
      return;
    }
    appVersionCheckInFlight = true;
    try {
      const response = await fetch(APP_VERSION_URL, {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = await response.json();
      const availableVersion = String(payload?.version || "").trim();
      if (!availableVersion || availableVersion === APP_VERSION) {
        return;
      }

      appReloadRequested = true;
      try {
        if (map) {
          const center = map.getCenter();
          const zoom = map.getZoom();
          if (
            Number.isFinite(center?.lat)
            && Number.isFinite(center?.lng)
            && Number.isFinite(zoom)
          ) {
            sessionStorage.setItem(
              APP_RELOAD_VIEW_STORAGE_KEY,
              JSON.stringify({
                center: [center.lat, center.lng],
                zoom,
              }),
            );
          }
        }
      } catch {
        // Reload even when session storage is unavailable.
      }
      window.location.reload();
    } catch {
      // A temporary version-check failure must not interrupt the live map.
    } finally {
      appVersionCheckInFlight = false;
    }
  }

  function encodeBasicAuth(passphrase) {
    const bytes = new TextEncoder().encode(`map:${passphrase}`);
    let binary = "";

    for (const byte of bytes) {
      binary += String.fromCharCode(byte);
    }

    return `Basic ${window.btoa(binary)}`;
  }

  function setPlayerButton(state) {
    elements.playerAccess.classList.remove("is-on", "is-off", "is-error");

    if (!playerAuth) {
      elements.playerAccess.textContent = state === "error"
        ? "PLAYERS DENIED"
        : "PLAYERS LOCKED";
      elements.playerAccess.classList.toggle("is-error", state === "error");
      elements.playerAccess.setAttribute("aria-pressed", "false");
      return;
    }

    elements.playerAccess.textContent = playersVisible
      ? `PLAYERS ON · ${playerCount}`
      : `PLAYERS OFF · ${playerCount}`;
    elements.playerAccess.classList.add(playersVisible ? "is-on" : "is-off");
    elements.playerAccess.setAttribute("aria-pressed", String(playersVisible));
  }

  function clearPlayerAccess(state = "locked") {
    playerAuth = null;
    authValidated = false;
    playerCount = 0;
    playersVisible = false;
    latestPlayers = [];
    latestPlayerRoster = [];
    latestPlayerRosterCollectedAt = null;
    latestMapEntities = [];
    latestMapEntitiesCollectedAt = null;
    movingVehicleAssociations.clear();
    followedPlayerName = "";
    sessionStorage.removeItem(PLAYER_AUTH_STORAGE_KEY);
    sessionStorage.removeItem(PLAYER_FOLLOW_STORAGE_KEY);
    elements.restartControl.hidden = true;
    elements.activityControl.hidden = true;
    elements.playerInfoControl.hidden = true;
    elements.layersControl.hidden = true;
    elements.playerFollowShell.hidden = true;
    elements.restartControl.disabled = false;
    restartState = "idle";

    if (restartTimer !== null) {
      window.clearInterval(restartTimer);
      restartTimer = null;
    }

    if (playerTimer !== null) {
      window.clearInterval(playerTimer);
      playerTimer = null;
    }

    if (mapEntityTimer !== null) {
      window.clearInterval(mapEntityTimer);
      mapEntityTimer = null;
    }
    if (traderExplorationTimer !== null) {
      window.clearInterval(traderExplorationTimer);
      traderExplorationTimer = null;
    }

    if (activityTimer !== null) {
      window.clearInterval(activityTimer);
      activityTimer = null;
    }
    activityEvents = [];
    if (elements.activityDialog.open) {
      elements.activityDialog.close();
    }
    if (elements.playerInfoDialog.open) {
      elements.playerInfoDialog.close();
    }
    elements.playerInfoBody.replaceChildren();
    for (const input of elements.layerInputs) {
      input.checked = false;
      mapLayerVisibility[input.dataset.mapLayer] = false;
    }
    if (biomeLayer && map?.hasLayer(biomeLayer)) {
      map.removeLayer(biomeLayer);
    }

    if (playerLayer) {
      playerLayer.clearLayers();
      if (map?.hasLayer(playerLayer)) {
        map.removeLayer(playerLayer);
      }
    }
    if (mapEntityLayer) {
      mapEntityLayer.clearLayers();
      if (map?.hasLayer(mapEntityLayer)) {
        map.removeLayer(mapEntityLayer);
      }
    }
    const mapElement = document.querySelector("#map");
    if (mapElement) {
      mapElement.dataset.hiddenMovingVehicles = "0";
      mapElement.dataset.hiddenUnexploredTraders = "0";
    }

    setPlayerButton(state);
  }

  async function handleAuthenticationFailure(response, showDialogError) {
    if (response.status === 429) {
      clearPlayerAccess("error");
      elements.playerAccess.textContent = "PLAYERS BLOCKED";
      if (showDialogError) {
        elements.playerError.textContent = "誤入力が規定回数に達したため、この接続元は24時間ブロックされています。";
      }
      return true;
    }

    if (response.status === 401) {
      const errorPayload = await response.json().catch(() => null);
      const remainingAttempts = Number(errorPayload?.remainingAttempts);
      clearPlayerAccess("error");
      if (showDialogError) {
        elements.playerError.textContent = Number.isFinite(remainingAttempts)
          ? `合い言葉が違います。あと${remainingAttempts}回間違えると24時間ブロックされます。`
          : "合い言葉が違います。";
      }
      return true;
    }
    return false;
  }

  async function checkAuthentication({ showDialogError = false } = {}) {
    if (!playerAuth) {
      return false;
    }

    try {
      const response = await fetch(AUTH_CHECK_URL, {
        headers: {
          Accept: "application/json",
          Authorization: playerAuth,
        },
        cache: "no-store",
      });
      if (await handleAuthenticationFailure(response, showDialogError)) {
        return false;
      }
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      authValidated = true;
      sessionStorage.setItem(PLAYER_AUTH_STORAGE_KEY, playerAuth);
      elements.restartControl.hidden = !restartEnabled;
      elements.activityControl.hidden = false;
      elements.playerInfoControl.hidden = false;
      elements.layersControl.hidden = false;
      elements.playerFollowShell.hidden = false;
      if (restartEnabled) {
        startRestartUpdates();
      }
      return true;
    } catch {
      if (showDialogError) {
        elements.playerError.textContent = "認証サービスへ接続できません。";
      }
      return false;
    }
  }

  function updatePlayerFollowOptions(players) {
    const options = [];
    const onlineNames = new Set(players.map((player) => player.name));

    if (players.length === 0 && !followedPlayerName) {
      options.push({ value: "", label: "FOLLOW · NO PLAYERS" });
      elements.playerFollow.disabled = true;
    } else {
      options.push({ value: "", label: "FOLLOW · OFF" });
      for (const player of players) {
        options.push({
          value: player.name,
          label: `FOLLOW · ${player.name}`,
        });
      }
      if (
        followedPlayerName
        && !onlineNames.has(followedPlayerName)
      ) {
        options.push({
          value: followedPlayerName,
          label: `FOLLOW · ${followedPlayerName}（待機中）`,
        });
      }
      elements.playerFollow.disabled = false;
    }

    elements.playerFollow.replaceChildren();
    for (const item of options) {
      const option = document.createElement("option");
      option.value = item.value;
      option.textContent = item.label;
      elements.playerFollow.append(option);
    }
    elements.playerFollow.value = followedPlayerName;
  }

  function moveToFollowedPlayer() {
    if (!map || !followedPlayerName) {
      return;
    }
    const player = latestPlayers.find(
      (candidate) => candidate.name === followedPlayerName,
    );
    if (!player) {
      return;
    }
    playersVisible = true;
    if (playerLayer && !map.hasLayer(playerLayer)) {
      playerLayer.addTo(map);
    }
    map.panTo([player.x, player.z], {
      animate: true,
      duration: 0.6,
    });
    refreshVisibleUnexploredTiles(true);
    setPlayerButton();
  }

  function selectFollowedPlayer(name) {
    followedPlayerName = name;
    if (followedPlayerName) {
      sessionStorage.setItem(
        PLAYER_FOLLOW_STORAGE_KEY,
        followedPlayerName,
      );
    } else {
      sessionStorage.removeItem(PLAYER_FOLLOW_STORAGE_KEY);
    }
    renderPlayers([...latestPlayers], { trackMovement: false });
    refreshVisibleUnexploredTiles(true);
  }

  function horizontalDistance(first, second) {
    return Math.hypot(first.x - second.x, first.z - second.z);
  }

  function updateMovingVehicleAssociations(
    previousPlayers,
    nextPlayers,
    sampledAt,
  ) {
    const onlinePlayerNames = new Set(
      nextPlayers.map((player) => player.name),
    );
    const currentEntityIds = new Set(
      latestMapEntities.map((entity) => String(entity?.entityId || "")),
    );

    for (const [entityId, association] of movingVehicleAssociations) {
      if (
        !onlinePlayerNames.has(association.playerName)
        || !currentEntityIds.has(entityId)
      ) {
        movingVehicleAssociations.delete(entityId);
      }
    }

    const movementByPlayer = new Map();
    for (const player of nextPlayers) {
      const previous = previousPlayers.get(player.name);
      if (!previous) {
        continue;
      }
      const elapsedSeconds = Math.max(
        (sampledAt - previous.sampledAt) / 1000,
        1,
      );
      movementByPlayer.set(player.name, {
        previous,
        speed: horizontalDistance(previous, player) / elapsedSeconds,
      });
    }

    for (const [entityId, association] of movingVehicleAssociations) {
      const movement = movementByPlayer.get(association.playerName);
      if (movement?.speed >= MOVING_PLAYER_MIN_SPEED_MPS) {
        association.lastMovingAt = sampledAt;
      } else if (
        sampledAt - association.lastMovingAt
        >= MOVING_VEHICLE_RELEASE_MS
      ) {
        movingVehicleAssociations.delete(entityId);
      }
    }

    const associatedPlayers = new Set(
      [...movingVehicleAssociations.values()].map(
        (association) => association.playerName,
      ),
    );
    const associatedEntities = new Set(movingVehicleAssociations.keys());

    for (const player of nextPlayers) {
      const movement = movementByPlayer.get(player.name);
      if (
        !movement
        || movement.speed < MOVING_PLAYER_MIN_SPEED_MPS
        || associatedPlayers.has(player.name)
      ) {
        continue;
      }

      let closestEntityId = "";
      let closestDistance = Number.POSITIVE_INFINITY;
      for (const entity of latestMapEntities) {
        const kind = String(entity?.kind || "");
        const entityId = String(entity?.entityId || "");
        const position = {
          x: Number(entity?.position?.x),
          z: Number(entity?.position?.z),
        };
        if (
          !VEHICLE_ENTITY_KINDS.has(kind)
          || !entityId
          || associatedEntities.has(entityId)
          || !Number.isFinite(position.x)
          || !Number.isFinite(position.z)
        ) {
          continue;
        }

        const distance = Math.min(
          horizontalDistance(position, movement.previous),
          horizontalDistance(position, player),
        );
        if (distance < closestDistance) {
          closestDistance = distance;
          closestEntityId = entityId;
        }
      }

      if (
        closestEntityId
        && closestDistance <= MOVING_VEHICLE_MATCH_RADIUS
      ) {
        movingVehicleAssociations.set(closestEntityId, {
          playerName: player.name,
          lastMovingAt: sampledAt,
        });
        associatedPlayers.add(player.name);
        associatedEntities.add(closestEntityId);
      }
    }
  }

  function renderPlayers(players, { trackMovement = true } = {}) {
    if (!playerLayer) {
      return;
    }

    const previousPlayers = new Map(
      latestPlayers.map((player) => [player.name, player]),
    );
    const sampledAt = Date.now();
    const nextPlayers = [];
    for (const player of players) {
      const x = Number(player?.position?.x ?? player?.x);
      const z = Number(player?.position?.z ?? player?.z);
      if (!Number.isFinite(x) || !Number.isFinite(z)) {
        continue;
      }
      nextPlayers.push({
        name: String(player?.name || "Unknown survivor"),
        x,
        z,
        sampledAt: trackMovement
          ? sampledAt
          : Number(player?.sampledAt) || sampledAt,
      });
    }
    if (trackMovement) {
      updateMovingVehicleAssociations(
        previousPlayers,
        nextPlayers,
        sampledAt,
      );
    }

    playerLayer.clearLayers();
    latestPlayers = nextPlayers;

    for (const { name, x, z } of latestPlayers) {
      const playerIcon = L.divIcon({
        className: name === followedPlayerName
          ? "player-marker-wrap is-followed"
          : "player-marker-wrap",
        html: '<span class="player-marker" aria-hidden="true"></span>',
        iconSize: [18, 18],
        iconAnchor: [9, 9],
      });
      const marker = L.marker([x, z], {
        icon: playerIcon,
        keyboard: false,
        title: name,
      });
      const label = document.createElement("span");
      label.textContent = name;
      marker.bindTooltip(label, {
        permanent: true,
        direction: "top",
        offset: [0, -8],
        className: "player-label",
      });
      marker.addTo(playerLayer);
    }
    playerCount = latestPlayers.length;
    updatePlayerFollowOptions(latestPlayers);
    if (latestMapEntities.length > 0) {
      renderMapEntities(
        latestMapEntities,
        latestMapEntitiesCollectedAt,
      );
    }

    if (playersVisible && !map.hasLayer(playerLayer)) {
      playerLayer.addTo(map);
    }

    moveToFollowedPlayer();
    setPlayerButton();
  }

  function formatPlayerTimestamp(value) {
    const timestamp = Number(value);
    if (!Number.isFinite(timestamp) || timestamp <= 0) {
      return "—";
    }
    return new Date(timestamp * 1000).toLocaleString("ja-JP", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function formatPlayerCoordinate(position) {
    const x = Number(position?.x);
    const y = Number(position?.y);
    const z = Number(position?.z);
    if (![x, y, z].every(Number.isFinite)) {
      return "—";
    }
    const coordinate = (value) => Math.round(value).toLocaleString("ja-JP");
    return `X ${coordinate(x)} / Y ${coordinate(y)} / Z ${coordinate(z)}`;
  }

  function addPlayerInfoCell(row, label, value, className = "") {
    const cell = document.createElement("td");
    cell.dataset.label = label;
    cell.textContent = value;
    if (className) {
      cell.className = className;
    }
    row.append(cell);
    return cell;
  }

  function renderPlayerRoster(roster, collectedAt) {
    latestPlayerRoster = Array.isArray(roster) ? roster : [];
    latestPlayerRosterCollectedAt = Number(collectedAt) || null;
    elements.playerInfoBody.replaceChildren();

    for (const player of latestPlayerRoster) {
      const online = player?.online === true;
      const row = document.createElement("tr");
      row.classList.toggle("is-online", online);

      const nameCell = document.createElement("td");
      nameCell.dataset.label = "プレイヤー";
      const name = document.createElement("span");
      name.className = "player-info-name";
      const presence = document.createElement("span");
      presence.className = online
        ? "player-info-presence is-online"
        : "player-info-presence";
      presence.setAttribute("aria-hidden", "true");
      const nameText = document.createElement("span");
      nameText.textContent = String(player?.name || "UNKNOWN");
      name.append(presence, nameText);
      nameCell.append(name);
      row.append(nameCell);

      const optionalInteger = (value) => (
        value === null || value === undefined ? null : Number(value)
      );
      const level = optionalInteger(player?.level);
      const gameStage = optionalInteger(player?.gameStage);
      const health = optionalInteger(player?.health);
      const maxHealth = optionalInteger(player?.maxHealth);
      const ping = optionalInteger(player?.ping);
      addPlayerInfoCell(
        row,
        "LEVEL",
        Number.isInteger(level) ? String(level) : "—",
      );
      addPlayerInfoCell(
        row,
        "GAME STAGE",
        online && Number.isInteger(gameStage) ? String(gameStage) : "—",
        online ? "player-info-online" : "",
      );
      addPlayerInfoCell(
        row,
        "HP",
        online && Number.isInteger(health)
          ? (
            Number.isInteger(maxHealth)
              ? `${health} / ${maxHealth}`
              : String(health)
          )
          : "—",
        online ? "player-info-online" : "",
      );
      addPlayerInfoCell(
        row,
        "PING",
        online && Number.isInteger(ping) ? `${ping} ms` : "—",
      );
      addPlayerInfoCell(
        row,
        "最終座標",
        formatPlayerCoordinate(player?.position),
        "player-info-coordinate",
      );
      addPlayerInfoCell(
        row,
        "最終保存",
        formatPlayerTimestamp(player?.profileSavedAt),
      );
      elements.playerInfoBody.append(row);
    }

    const onlineCount = latestPlayerRoster.filter(
      (player) => player?.online === true,
    ).length;
    const collectedText = latestPlayerRosterCollectedAt
      ? formatPlayerTimestamp(latestPlayerRosterCollectedAt)
      : "—";
    elements.playerInfoStatus.textContent = (
      `ONLINE ${onlineCount} / ALL ${latestPlayerRoster.length}`
      + ` · 更新 ${collectedText}`
    );
    elements.playerInfoEmpty.hidden = latestPlayerRoster.length > 0;

    const selectedOwner = elements.layerPlayerFilter.value;
    const ownerNames = [...new Set(
      latestPlayerRoster
        .map((player) => String(player?.name || "").trim())
        .filter(Boolean),
    )].sort((first, second) => first.localeCompare(second, "ja"));
    elements.layerPlayerFilter.replaceChildren();
    const allOption = document.createElement("option");
    allOption.value = "";
    allOption.textContent = "全員";
    elements.layerPlayerFilter.append(allOption);
    for (const ownerName of ownerNames) {
      const option = document.createElement("option");
      option.value = ownerName;
      option.textContent = ownerName;
      elements.layerPlayerFilter.append(option);
    }
    elements.layerPlayerFilter.value = ownerNames.includes(selectedOwner)
      ? selectedOwner
      : "";
  }

  async function openPlayerInfoDialog() {
    if (!restartEnabled || !playerAuth || !authValidated) {
      return;
    }
    renderPlayerRoster(
      latestPlayerRoster,
      latestPlayerRosterCollectedAt,
    );
    elements.playerInfoDialog.showModal();
    await updatePlayers();
  }

  function closePlayerInfoDialog() {
    elements.playerInfoDialog.close();
  }

  async function updatePlayers({ showDialogError = false } = {}) {
    if (!playerAuth || !playerLayer) {
      return false;
    }

    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 5000);

    try {
      const response = await fetch(PLAYERS_URL, {
        headers: {
          Accept: "application/json",
          Authorization: playerAuth,
        },
        cache: "no-store",
        signal: controller.signal,
      });

      if (await handleAuthenticationFailure(response, showDialogError)) {
        return false;
      }

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const payload = await response.json();
      const players = Array.isArray(payload?.data?.players)
        ? payload.data.players
        : [];
      renderPlayerRoster(
        payload?.data?.roster,
        payload?.data?.lastCollectedAt,
      );
      renderPlayers(players);
      return true;
    } catch {
      if (showDialogError) {
        elements.playerError.textContent = "プレイヤー情報を取得できません。";
      }
      return false;
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function startPlayerUpdates() {
    if (playerTimer !== null) {
      return;
    }

    playerTimer = window.setInterval(updatePlayers, PLAYER_REFRESH_MS);
  }

  function renderMapEntities(entities, lastCollectedAt) {
    if (!mapEntityLayer) {
      return;
    }

    mapEntityLayer.clearLayers();
    const collectedAt = Number(lastCollectedAt);
    const collectedLabel = Number.isFinite(collectedAt)
      ? new Intl.DateTimeFormat("ja-JP", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }).format(new Date(collectedAt * 1000))
      : "不明";

    let hiddenMovingVehicles = 0;
    let hiddenUnexploredTraders = 0;
    for (const entity of entities) {
      const kind = String(entity?.kind || "");
      const entityId = String(entity?.entityId || "");
      const spec = MAP_ENTITY_SPECS[kind];
      const x = Number(entity?.position?.x);
      const y = Number(entity?.position?.y);
      const z = Number(entity?.position?.z);
      if (
        !spec
        || !Number.isFinite(x)
        || !Number.isFinite(y)
        || !Number.isFinite(z)
      ) {
        continue;
      }
      if (
        VEHICLE_ENTITY_KINDS.has(kind)
        && movingVehicleAssociations.has(entityId)
      ) {
        hiddenMovingVehicles += 1;
        continue;
      }
      if (
        TRADER_ENTITY_KINDS.has(kind)
        && traderExplorationStates.get(entityId) !== true
      ) {
        hiddenUnexploredTraders += 1;
        continue;
      }
      if (
        OPTIONAL_ENTITY_KINDS.has(kind)
        && !mapLayerVisibility[kind]
      ) {
        continue;
      }
      const owner = String(entity?.owner || "");
      if (
        OPTIONAL_ENTITY_KINDS.has(kind)
        && elements.layerPlayerFilter.value
        && owner !== elements.layerPlayerFilter.value
      ) {
        continue;
      }

      const label = String(entity?.label || spec.label);
      const icon = L.divIcon({
        className: `map-entity-marker-wrap is-${kind}`,
        html: `<span class="map-entity-marker" aria-hidden="true">${spec.icon || spec.symbol}</span>`,
        iconSize: [24, 24],
        iconAnchor: [12, 12],
      });
      const marker = L.marker([x, z], {
        icon,
        keyboard: true,
        title: label,
      });

      const tooltip = document.createElement("span");
      tooltip.textContent = label;
      marker.bindTooltip(tooltip, {
        direction: "top",
        offset: [0, -10],
        className: "entity-label",
      });

      const popup = document.createElement("section");
      popup.className = "entity-popup";
      const heading = document.createElement("strong");
      heading.textContent = label;
      const coordinates = document.createElement("span");
      coordinates.textContent = (
        `X ${Math.round(x)} / Y ${Math.round(y)} / Z ${Math.round(z)}`
      );
      const updated = document.createElement("span");
      updated.textContent = `最終確認 ${collectedLabel}`;
      popup.append(heading);
      if (owner) {
        const ownerLine = document.createElement("span");
        ownerLine.textContent = `プレイヤー ${owner}`;
        popup.append(ownerLine);
      }
      if (entity?.detail) {
        const detail = document.createElement("span");
        detail.textContent = String(entity.detail);
        popup.append(detail);
      }
      popup.append(coordinates, updated);
      marker.bindPopup(popup, {
        className: "entity-popup-shell",
        closeButton: true,
      });
      marker.addTo(mapEntityLayer);
    }
    const enabledOptional = Object.entries(mapLayerVisibility)
      .filter(([kind, visible]) => kind !== "biome" && visible)
      .map(([kind]) => MAP_ENTITY_SPECS[kind]?.label)
      .filter(Boolean);
    elements.layersStatus.textContent = enabledOptional.length > 0
      ? `表示中: ${enabledOptional.join(" / ")}`
      : (mapLayerVisibility.biome ? "表示中: バイオーム" : "追加レイヤーは非表示です");
    const mapElement = document.querySelector("#map");
    if (mapElement) {
      mapElement.dataset.hiddenMovingVehicles = String(
        hiddenMovingVehicles,
      );
      mapElement.dataset.hiddenUnexploredTraders = String(
        hiddenUnexploredTraders,
      );
    }

    if (map && !map.hasLayer(mapEntityLayer)) {
      mapEntityLayer.addTo(map);
    }
  }

  function getTraderTileSample(entity) {
    if (!map) {
      return null;
    }
    const x = Number(entity?.position?.x);
    const z = Number(entity?.position?.z);
    if (!Number.isFinite(x) || !Number.isFinite(z)) {
      return null;
    }

    const point = map.project(
      L.latLng(x, z),
      MAP_NATIVE_MAX_ZOOM,
    );
    const leafletTileX = Math.floor(point.x / MAP_TILE_SIZE);
    const leafletTileY = Math.floor(point.y / MAP_TILE_SIZE);
    return {
      url: (
        `/map/${MAP_NATIVE_MAX_ZOOM}/${leafletTileX}/`
        + `${-leafletTileY - 1}.png?live=1`
      ),
      pixelX: Math.floor(point.x - leafletTileX * MAP_TILE_SIZE),
      pixelY: Math.floor(point.y - leafletTileY * MAP_TILE_SIZE),
    };
  }

  async function isTraderPositionExplored(entity) {
    const sample = getTraderTileSample(entity);
    if (!sample) {
      return false;
    }

    const blob = await fetchTileBlob(sample.url, {
      cache: "no-store",
    });
    if (blob.size <= UNEXPLORED_TILE_MAX_BYTES) {
      return false;
    }

    const bitmap = await createImageBitmap(blob);
    try {
      const canvas = document.createElement("canvas");
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      const context = canvas.getContext("2d", {
        willReadFrequently: true,
      });
      if (!context) {
        return false;
      }
      context.drawImage(bitmap, 0, 0);

      const left = Math.max(0, sample.pixelX - 1);
      const top = Math.max(0, sample.pixelY - 1);
      const width = Math.min(3, bitmap.width - left);
      const height = Math.min(3, bitmap.height - top);
      const pixels = context.getImageData(
        left,
        top,
        width,
        height,
      ).data;
      for (let index = 0; index < pixels.length; index += 4) {
        if (
          pixels[index + 3] > 0
          && pixels[index] + pixels[index + 1] + pixels[index + 2] > 24
        ) {
          return true;
        }
      }
      return false;
    } finally {
      bitmap.close();
    }
  }

  async function refreshTraderExplorationStates() {
    if (
      traderExplorationCheckInFlight
      || !playerAuth
      || !map
    ) {
      return;
    }
    const traders = latestMapEntities.filter((entity) => (
      TRADER_ENTITY_KINDS.has(String(entity?.kind || ""))
      && traderExplorationStates.get(String(entity?.entityId || ""))
        !== true
    ));
    if (traders.length === 0) {
      return;
    }

    traderExplorationCheckInFlight = true;
    let changed = false;
    try {
      await Promise.all(traders.map(async (entity) => {
        const entityId = String(entity?.entityId || "");
        try {
          const explored = await isTraderPositionExplored(entity);
          if (traderExplorationStates.get(entityId) !== explored) {
            traderExplorationStates.set(entityId, explored);
            changed = true;
          }
        } catch {
          // 通信失敗時は位置を公開せず、次の周期に再確認する。
        }
      }));
    } finally {
      traderExplorationCheckInFlight = false;
    }

    if (changed && playerAuth && mapEntityLayer) {
      renderMapEntities(
        latestMapEntities,
        latestMapEntitiesCollectedAt,
      );
    }
  }

  async function updateMapEntities() {
    if (!playerAuth || !mapEntityLayer) {
      return false;
    }

    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch(MAP_ENTITIES_URL, {
        headers: {
          Accept: "application/json",
          Authorization: playerAuth,
        },
        cache: "no-store",
        signal: controller.signal,
      });
      if (await handleAuthenticationFailure(response, false)) {
        return false;
      }
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const payload = await response.json();
      const entities = Array.isArray(payload?.data?.entities)
        ? payload.data.entities
        : [];
      latestMapEntities = entities;
      latestMapEntitiesCollectedAt = payload?.data?.lastCollectedAt;
      renderMapEntities(
        latestMapEntities,
        latestMapEntitiesCollectedAt,
      );
      refreshTraderExplorationStates();
      return true;
    } catch {
      return false;
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function startMapEntityUpdates() {
    if (mapEntityTimer === null) {
      mapEntityTimer = window.setInterval(
        updateMapEntities,
        MAP_ENTITY_REFRESH_MS,
      );
    }
    if (traderExplorationTimer === null) {
      traderExplorationTimer = window.setInterval(
        refreshTraderExplorationStates,
        TRADER_EXPLORATION_REFRESH_MS,
      );
    }
  }

  async function ensureBiomeLayer() {
    if (biomeLayer || !map || !playerAuth || !authValidated) {
      return;
    }
    elements.layersStatus.textContent = "バイオーム画像を読み込んでいます";
    const response = await fetch(BIOME_URL, {
      headers: {
        Accept: "image/png",
        Authorization: playerAuth,
      },
      cache: "force-cache",
    });
    if (await handleAuthenticationFailure(response, false)) {
      return;
    }
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const blob = await response.blob();
    biomeObjectUrl = URL.createObjectURL(blob);
    biomeImage = new Image();
    biomeImage.src = biomeObjectUrl;
    await biomeImage.decode();

    const BiomeGridLayer = L.GridLayer.extend({
      createTile(coordinates, done) {
        const tileSize = this.getTileSize();
        const canvas = document.createElement("canvas");
        canvas.width = tileSize.x;
        canvas.height = tileSize.y;
        canvas.setAttribute("role", "presentation");
        const context = canvas.getContext("2d", { alpha: true });
        const nativeMaxZoom = Number(this.options.nativeMaxZoom);
        const worldUnitsPerTile = (
          tileSize.x * (2 ** (nativeMaxZoom - coordinates.z))
        );
        const metersPerPixelX = worldWidth / biomeImage.naturalWidth;
        const metersPerPixelY = worldDepth / biomeImage.naturalHeight;
        const sourceX = (
          coordinates.x * worldUnitsPerTile + worldWidth / 2
        ) / metersPerPixelX;
        const sourceY = (
          coordinates.y * worldUnitsPerTile + worldDepth / 2
        ) / metersPerPixelY;
        const sourceWidth = worldUnitsPerTile / metersPerPixelX;
        const sourceHeight = worldUnitsPerTile / metersPerPixelY;

        if (
          sourceX < biomeImage.naturalWidth
          && sourceY < biomeImage.naturalHeight
          && sourceX + sourceWidth > 0
          && sourceY + sourceHeight > 0
        ) {
          context.imageSmoothingEnabled = false;
          context.drawImage(
            biomeImage,
            sourceX,
            sourceY,
            sourceWidth,
            sourceHeight,
            0,
            0,
            tileSize.x,
            tileSize.y,
          );
        }
        window.setTimeout(() => done(null, canvas), 0);
        return canvas;
      },
    });
    biomeLayer = new BiomeGridLayer({
      tileSize: MAP_TILE_SIZE,
      nativeMaxZoom: MAP_NATIVE_MAX_ZOOM,
      minZoom: 0,
      maxZoom: MAP_NATIVE_MAX_ZOOM + 1,
      noWrap: true,
      bounds: worldBounds,
      opacity: Number(elements.biomeOpacity.value) / 100,
      updateWhenIdle: false,
    });
  }

  async function updateBiomeVisibility() {
    if (!mapLayerVisibility.biome) {
      if (biomeLayer && map?.hasLayer(biomeLayer)) {
        map.removeLayer(biomeLayer);
      }
      renderMapEntities(
        latestMapEntities,
        latestMapEntitiesCollectedAt,
      );
      return;
    }
    try {
      await ensureBiomeLayer();
      if (biomeLayer && !map.hasLayer(biomeLayer)) {
        biomeLayer.addTo(map);
        if (mapEntityLayer && map.hasLayer(mapEntityLayer)) {
          mapEntityLayer.bringToFront?.();
        }
      }
      elements.layersStatus.textContent = "表示中: バイオーム";
    } catch {
      mapLayerVisibility.biome = false;
      const input = [...elements.layerInputs].find(
        (item) => item.dataset.mapLayer === "biome",
      );
      if (input) {
        input.checked = false;
      }
      elements.layersStatus.textContent = "バイオーム画像を取得できません";
    }
  }

  async function unlockPlayers(passphrase) {
    playerAuth = encodeBasicAuth(passphrase);
    playersVisible = true;

    const unlocked = await checkAuthentication({ showDialogError: true });
    if (!unlocked) {
      return;
    }

    elements.playerForm.reset();
    elements.playerDialog.close();
    setPlayerButton();
    if (map && playerLayer) {
      playerLayer.addTo(map);
      updatePlayers();
      startPlayerUpdates();
      updateMapEntities();
      startMapEntityUpdates();
      updateDetailedServerStatus();
    }
  }

  function openPlayerDialog() {
    elements.playerError.textContent = "";
    elements.playerDialog.showModal();
    window.setTimeout(() => elements.playerPassphrase.focus(), 0);
  }

  function togglePlayers() {
    if (!playerAuth) {
      openPlayerDialog();
      return;
    }

    playersVisible = !playersVisible;
    if (playersVisible) {
      playerLayer.addTo(map);
      updatePlayers();
    } else {
      if (map.hasLayer(playerLayer)) {
        map.removeLayer(playerLayer);
      }
      followedPlayerName = "";
      sessionStorage.removeItem(PLAYER_FOLLOW_STORAGE_KEY);
      updatePlayerFollowOptions(latestPlayers);
    }
    setPlayerButton();
  }

  function formatActivityTime(value) {
    const timestamp = new Date(value);
    if (Number.isNaN(timestamp.getTime())) {
      return "日時不明";
    }
    return new Intl.DateTimeFormat("ja-JP", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(timestamp);
  }

  function activityTypeLabel(type) {
    return {
      chat: "チャット",
      login: "ログイン",
      logout: "ログアウト",
      death: "死亡",
    }[type] || "イベント";
  }

  function activityMatchesFilter(event) {
    if (activityFilter === "all") {
      return true;
    }
    if (activityFilter === "access") {
      return event?.type === "login" || event?.type === "logout";
    }
    return event?.type === activityFilter;
  }

  function renderActivity() {
    elements.activityList.replaceChildren();
    const visibleEvents = activityEvents.filter(activityMatchesFilter);

    for (const event of visibleEvents) {
      const type = ["chat", "login", "logout", "death"].includes(event?.type)
        ? event.type
        : "unknown";
      const item = document.createElement("li");
      item.className = `activity-item is-${type}`;

      const timestamp = document.createElement("time");
      timestamp.className = "activity-time";
      timestamp.dateTime = String(event?.occurredAt || "");
      timestamp.textContent = formatActivityTime(event?.occurredAt);

      const kind = document.createElement("span");
      kind.className = "activity-kind";
      kind.textContent = activityTypeLabel(type);

      const content = document.createElement("div");
      content.className = "activity-content";
      const player = document.createElement("span");
      player.className = "activity-player";
      player.textContent = String(event?.player || "UNKNOWN");
      content.append(player);

      const messageText = String(event?.message || "");
      if (messageText) {
        const message = document.createElement("span");
        message.className = "activity-message";
        message.textContent = messageText;
        content.append(message);
      }

      item.append(timestamp, kind, content);
      elements.activityList.append(item);
    }

    elements.activityEmpty.hidden = visibleEvents.length !== 0;
  }

  function setActivityFilter(filter) {
    activityFilter = filter;
    for (const button of elements.activityFilters) {
      button.classList.toggle(
        "is-active",
        button.dataset.activityFilter === filter,
      );
    }
    renderActivity();
  }

  async function updateActivity() {
    if (!playerAuth || !authValidated) {
      return;
    }
    elements.activityRefresh.disabled = true;
    try {
      const response = await fetch(ACTIVITY_URL, {
        headers: {
          Accept: "application/json",
          Authorization: playerAuth,
        },
        cache: "no-store",
      });
      if (await handleAuthenticationFailure(response, false)) {
        return;
      }
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = await response.json();
      activityEvents = Array.isArray(payload?.data?.events)
        ? payload.data.events
        : [];
      const lastCollectedAt = Number(payload?.data?.lastCollectedAt);
      const collectorHealthy = payload?.data?.collectorHealthy === true;
      elements.activityStatus.textContent = Number.isFinite(lastCollectedAt)
        ? `${collectorHealthy ? "収集中" : "収集停止"} · 最新${activityEvents.length}件 · ${new Date(lastCollectedAt * 1000).toLocaleTimeString("ja-JP")}`
        : `収集待機中 · 最新${activityEvents.length}件`;
      renderActivity();
    } catch {
      elements.activityStatus.textContent = "履歴を取得できません。";
    } finally {
      elements.activityRefresh.disabled = false;
    }
  }

  function closeActivityDialog() {
    if (elements.activityDialog.open) {
      elements.activityDialog.close();
    }
    if (activityTimer !== null) {
      window.clearInterval(activityTimer);
      activityTimer = null;
    }
  }

  function openActivityDialog() {
    elements.activityStatus.textContent = "履歴を読み込んでいます";
    elements.activityDialog.showModal();
    updateActivity();
    if (activityTimer === null) {
      activityTimer = window.setInterval(
        updateActivity,
        ACTIVITY_REFRESH_MS,
      );
    }
  }

  function formatRemaining(seconds) {
    const safeSeconds = Math.max(0, Math.ceil(Number(seconds) || 0));
    const minutes = Math.floor(safeSeconds / 60);
    const remainder = safeSeconds % 60;
    return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
  }

  function renderRestartStatus(status) {
    restartState = String(status?.state || "idle");
    const cooldown = Number(status?.cooldownRemainingSeconds) || 0;
    elements.restartControl.disabled = false;
    elements.restartControl.classList.remove(
      "is-pending",
      "is-executing",
      "is-error",
    );

    if (restartState === "pending") {
      elements.restartControl.textContent = `中止 · ${formatRemaining(status.remainingSeconds)}`;
      elements.restartControl.classList.add("is-pending");
      return;
    }
    if (restartState === "executing") {
      elements.restartControl.textContent = "RESTARTING";
      elements.restartControl.disabled = true;
      elements.restartControl.classList.add("is-executing");
      return;
    }
    if (cooldown > 0) {
      elements.restartControl.textContent = `COOLDOWN · ${formatRemaining(cooldown)}`;
      elements.restartControl.disabled = true;
      return;
    }
    if (restartState === "failed") {
      elements.restartControl.textContent = "RESTART FAILED";
      elements.restartControl.classList.add("is-error");
      return;
    }
    elements.restartControl.textContent = "SERVER RESTART";
  }

  async function updateRestartStatus() {
    if (!playerAuth || !authValidated) {
      return;
    }
    try {
      const response = await fetch(RESTART_STATUS_URL, {
        headers: {
          Accept: "application/json",
          Authorization: playerAuth,
        },
        cache: "no-store",
      });
      if (await handleAuthenticationFailure(response, false)) {
        return;
      }
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      const payload = await response.json();
      renderRestartStatus(payload?.data);
    } catch {
      elements.restartControl.textContent = "CONTROL OFFLINE";
      elements.restartControl.classList.add("is-error");
    }
  }

  function startRestartUpdates() {
    if (!restartEnabled) {
      return;
    }
    updateRestartStatus();
    if (restartTimer === null) {
      restartTimer = window.setInterval(
        updateRestartStatus,
        RESTART_STATUS_REFRESH_MS,
      );
    }
  }

  async function postRestartAction(url, payload) {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        Accept: "application/json",
        Authorization: playerAuth,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
      cache: "no-store",
    });
    if (await handleAuthenticationFailure(response, false)) {
      throw new Error("認証が切れました。");
    }
    const responsePayload = await response.json().catch(() => null);
    if (!response.ok) {
      if (responsePayload?.outcome === "already_active") {
        throw new Error("すでに再起動が予約されています。");
      }
      if (responsePayload?.outcome === "cooldown") {
        throw new Error("再起動後の待機時間中です。");
      }
      if (responsePayload?.outcome === "too_late") {
        throw new Error("再起動処理が始まったため中止できません。");
      }
      throw new Error("操作を受け付けられませんでした。");
    }
    renderRestartStatus(responsePayload?.data);
  }

  async function requestRestart() {
    const confirmation = elements.restartConfirmation.value.trim();
    if (confirmation !== "RESTART") {
      elements.restartError.textContent = "RESTART と正確に入力してください。";
      return;
    }
    elements.restartError.textContent = "";
    try {
      await postRestartAction(RESTART_REQUEST_URL, { confirmation });
      elements.restartForm.reset();
      elements.restartDialog.close();
    } catch (error) {
      elements.restartError.textContent = error.message;
    }
  }

  async function cancelRestart() {
    if (!window.confirm("予約中のサーバー再起動を中止しますか？")) {
      return;
    }
    try {
      await postRestartAction(RESTART_CANCEL_URL, {});
    } catch (error) {
      window.alert(error.message);
    }
  }

  function openRestartDialog() {
    elements.restartError.textContent = "";
    elements.restartDialog.showModal();
    window.setTimeout(() => elements.restartConfirmation.focus(), 0);
  }

  function markGuideSeen() {
    try {
      localStorage.setItem(GUIDE_SEEN_STORAGE_KEY, "1");
    } catch {
      // ブラウザーが保存を拒否しても案内自体は利用できる。
    }
  }

  function openGuide() {
    if (!elements.guideDialog.open) {
      elements.guideDialog.showModal();
    }
  }

  function closeGuide() {
    markGuideSeen();
    if (elements.guideDialog.open) {
      elements.guideDialog.close();
    }
  }

  function showGuideOnFirstVisit() {
    let guideSeen = false;
    try {
      guideSeen = localStorage.getItem(GUIDE_SEEN_STORAGE_KEY) === "1";
    } catch {
      guideSeen = false;
    }
    if (!guideSeen) {
      window.setTimeout(openGuide, 250);
    }
  }

  function wait(milliseconds) {
    return new Promise((resolve) => {
      window.setTimeout(resolve, milliseconds);
    });
  }

  async function fetchWithRetry(url, options, retryDelays) {
    let lastError = new Error("Request failed");

    for (
      let attempt = 0;
      attempt < retryDelays.length;
      attempt += 1
    ) {
      const delay = retryDelays[attempt];
      if (delay > 0) {
        await wait(delay);
      }

      try {
        const response = await fetch(url, options);
        if (
          response.ok
          || (response.status !== 429 && response.status < 500)
        ) {
          return response;
        }
        lastError = new Error(`HTTP ${response.status}`);
      } catch (error) {
        lastError = error;
      }
    }

    throw lastError;
  }

  async function fetchTileBlob(url, options = {}) {
    const response = await fetchWithRetry(
      url,
      options,
      TILE_RETRY_DELAYS_MS,
    );
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return response.blob();
  }

  function scheduleUnexploredTileRefresh(tile, immediate = false) {
    if (!tile.classList.contains("is-unexplored")) {
      return;
    }
    const scheduledTimer = unexploredTileRefreshTimers.get(tile);
    if (scheduledTimer !== undefined) {
      if (!immediate) {
        return;
      }
      window.clearTimeout(scheduledTimer);
      unexploredTileRefreshTimers.delete(tile);
    }

    const timer = window.setTimeout(async () => {
      unexploredTileRefreshTimers.delete(tile);
      if (
        !tile.isConnected
        || !tile.classList.contains("is-unexplored")
      ) {
        return;
      }
      if (document.hidden) {
        scheduleUnexploredTileRefresh(tile);
        return;
      }

      const baseUrl = tile.dataset.mapTileUrl;
      if (!baseUrl) {
        return;
      }
      tile.dataset.liveRefreshAt = String(Date.now());

      try {
        const separator = baseUrl.includes("?") ? "&" : "?";
        const blob = await fetchTileBlob(
          `${baseUrl}${separator}live=1`,
          { cache: "no-store" },
        );
        if (blob.size <= UNEXPLORED_TILE_MAX_BYTES) {
          scheduleUnexploredTileRefresh(tile);
          return;
        }
        if (!tile.isConnected) {
          return;
        }

        const objectUrl = URL.createObjectURL(blob);
        tile.onload = () => {
          tile.onload = null;
          tile.onerror = null;
          URL.revokeObjectURL(objectUrl);
          tile.classList.remove("is-unexplored");
        };
        tile.onerror = () => {
          tile.onload = null;
          tile.onerror = null;
          URL.revokeObjectURL(objectUrl);
          tile.src = TRANSPARENT_TILE;
          scheduleUnexploredTileRefresh(tile);
        };
        tile.src = objectUrl;
      } catch {
        scheduleUnexploredTileRefresh(tile);
      }
    }, immediate ? 0 : UNEXPLORED_TILE_REFRESH_MS);

    unexploredTileRefreshTimers.set(tile, timer);
  }

  function refreshVisibleUnexploredTiles(immediate = false) {
    for (const tile of document.querySelectorAll(
      "#map img.leaflet-tile.is-unexplored",
    )) {
      scheduleUnexploredTileRefresh(tile, immediate);
    }
  }

  function fitWorld() {
    if (map && worldBounds) {
      map.fitBounds(worldBounds, {
        paddingTopLeft: [42, 100],
        paddingBottomRight: [42, 80],
        animate: true,
      });
    }
  }

  function createMap(config) {
    const width = Number(config.mapSize?.x) || 6144;
    const depth = Number(config.mapSize?.z) || 6144;
    const maxZoom = Number(config.maxZoom) || MAP_NATIVE_MAX_ZOOM;
    const halfWidth = width / 2;
    const halfDepth = depth / 2;
    worldWidth = width;
    worldDepth = depth;

    worldBounds = L.latLngBounds(
      [-halfWidth, -halfDepth],
      [halfWidth, halfDepth],
    );

    map = L.map("map", {
      crs: gameCrs,
      center: [0, 0],
      zoom: 1,
      minZoom: Math.max(0, maxZoom - 5),
      maxZoom: maxZoom + 1,
      maxBounds: worldBounds,
      maxBoundsViscosity: 1,
      zoomControl: false,
      attributionControl: false,
      scrollWheelZoom: true,
      doubleClickZoom: true,
      keyboard: true,
      tap: true,
    });
    playerLayer = L.layerGroup();
    mapEntityLayer = L.layerGroup();

    const tiles = L.tileLayer("/map/{z}/{x}/{y}.png", {
      tileSize: MAP_TILE_SIZE,
      minZoom: 0,
      maxNativeZoom: maxZoom,
      maxZoom: maxZoom + 1,
      noWrap: true,
      bounds: worldBounds,
      keepBuffer: 3,
      updateWhenIdle: false,
    });

    tiles.getTileUrl = function getTileUrl(coordinates) {
      const gameCoordinates = {
        x: coordinates.x,
        y: -coordinates.y - 1,
        z: coordinates.z,
      };
      return L.TileLayer.prototype.getTileUrl.call(this, gameCoordinates);
    };

    tiles.createTile = function createTile(coordinates, done) {
      const tile = document.createElement("img");
      const url = this.getTileUrl(coordinates);

      tile.alt = "";
      tile.setAttribute("role", "presentation");
      tile.decoding = "async";
      tile.dataset.mapTileUrl = url;

      fetchTileBlob(url)
        .then((blob) => {
          if (blob.size <= UNEXPLORED_TILE_MAX_BYTES) {
            tile.classList.add("is-unexplored");
            tile.src = TRANSPARENT_TILE;
            done(null, tile);
            scheduleUnexploredTileRefresh(tile);
            return;
          }

          const objectUrl = URL.createObjectURL(blob);
          tile.onload = () => {
            URL.revokeObjectURL(objectUrl);
            done(null, tile);
          };
          tile.onerror = () => {
            URL.revokeObjectURL(objectUrl);
            done(new Error("Tile image could not be decoded"), tile);
          };
          tile.src = objectUrl;
        })
        .catch((error) => {
          tile.classList.add("is-unexplored");
          tile.src = TRANSPARENT_TILE;
          done(error, tile);
          scheduleUnexploredTileRefresh(tile);
        });

      return tile;
    };

    tiles.addTo(map);
    let restoredView = null;
    try {
      restoredView = JSON.parse(
        sessionStorage.getItem(APP_RELOAD_VIEW_STORAGE_KEY) || "null",
      );
    } catch {
      restoredView = null;
    }
    sessionStorage.removeItem(APP_RELOAD_VIEW_STORAGE_KEY);
    if (
      Array.isArray(restoredView?.center)
      && restoredView.center.length === 2
      && restoredView.center.every(Number.isFinite)
      && Number.isFinite(restoredView?.zoom)
    ) {
      map.setView(restoredView.center, restoredView.zoom, { animate: false });
    } else {
      fitWorld();
    }

    map.on("mousemove", (event) => updateCoordinates(event.latlng));
    map.on("mouseout", () => updateCoordinates(null));
    map.on("click", (event) => updateCoordinates(event.latlng));
    map.on("moveend zoomend", () => {
      refreshVisibleUnexploredTiles(true);
    });

    elements.zoomIn.addEventListener("click", () => map.zoomIn());
    elements.zoomOut.addEventListener("click", () => map.zoomOut());
    elements.resetView.addEventListener("click", fitWorld);

    elements.loadingPanel.classList.add("is-hidden");
    setStatus("online", "MAP ONLINE");
    startGameTimeUpdates();
    showGuideOnFirstVisit();

    if (playerAuth && authValidated) {
      playersVisible = true;
      playerLayer.addTo(map);
      updatePlayers();
      startPlayerUpdates();
      updateMapEntities();
      startMapEntityUpdates();
    }
  }

  async function loadMap() {
    setStatus("loading", "MAP LINKING");
    elements.loadingTitle.textContent = "地図データに接続中";
    elements.loadingMessage.textContent = "探索記録を読み込んでいます";
    elements.retryButton.hidden = true;

    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 8000);

    try {
      const response = await fetchWithRetry(
        CONFIG_URL,
        {
          headers: { Accept: "application/json" },
          cache: "no-store",
          signal: controller.signal,
        },
        CONFIG_RETRY_DELAYS_MS,
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const payload = await response.json();
      const config = payload?.data;

      if (!config?.enabled) {
        throw new Error("サーバー側の地図レンダリングが無効です");
      }

      if (!map) {
        createMap(config);
      } else {
        elements.loadingPanel.classList.add("is-hidden");
        setStatus("online", "MAP ONLINE");
        startGameTimeUpdates();
      }
    } catch (error) {
      const maintenanceWindow = window.LiveMapMaintenance?.findWindow(
        new Date(),
        MAINTENANCE_TIME_ZONE,
        MAINTENANCE_WINDOWS,
      );
      if (maintenanceWindow) {
        showError(
          `${maintenanceWindow.start}開始の予定メンテナンス時間です。終了までしばらくお待ちください`,
          "定期メンテナンス中です",
          "MAINTENANCE",
        );
        return;
      }
      const reason = error.name === "AbortError"
        ? "サーバーからの応答がタイムアウトしました"
        : "しばらく待ってから再接続してください";
      showError(reason);
    } finally {
      window.clearTimeout(timeout);
    }
  }

  elements.retryButton.addEventListener("click", loadMap);
  elements.playerAccess.addEventListener("click", togglePlayers);
  elements.playerFollow.addEventListener("change", () => {
    selectFollowedPlayer(elements.playerFollow.value);
  });
  elements.playerCancel.addEventListener("click", () => {
    elements.playerForm.reset();
    elements.playerDialog.close();
  });
  elements.playerForm.addEventListener("submit", (event) => {
    event.preventDefault();
    elements.playerError.textContent = "";
    unlockPlayers(elements.playerPassphrase.value);
  });
  elements.activityControl.addEventListener("click", openActivityDialog);
  elements.activityClose.addEventListener("click", closeActivityDialog);
  elements.activityRefresh.addEventListener("click", updateActivity);
  elements.activityDialog.addEventListener("close", () => {
    if (activityTimer !== null) {
      window.clearInterval(activityTimer);
      activityTimer = null;
    }
  });
  for (const button of elements.activityFilters) {
    button.addEventListener("click", () => {
      setActivityFilter(button.dataset.activityFilter || "all");
    });
  }
  elements.playerInfoControl.addEventListener(
    "click",
    openPlayerInfoDialog,
  );
  elements.playerInfoClose.addEventListener(
    "click",
    closePlayerInfoDialog,
  );
  elements.layersControl.addEventListener("click", () => {
    elements.layersDialog.showModal();
  });
  elements.layersClose.addEventListener("click", () => {
    elements.layersDialog.close();
  });
  for (const input of elements.layerInputs) {
    input.addEventListener("change", () => {
      const kind = input.dataset.mapLayer;
      mapLayerVisibility[kind] = input.checked;
      if (kind === "biome") {
        updateBiomeVisibility();
      } else {
        renderMapEntities(
          latestMapEntities,
          latestMapEntitiesCollectedAt,
        );
      }
    });
  }
  elements.layerPlayerFilter.addEventListener("change", () => {
    renderMapEntities(
      latestMapEntities,
      latestMapEntitiesCollectedAt,
    );
  });
  elements.biomeOpacity.addEventListener("input", () => {
    biomeLayer?.setOpacity(Number(elements.biomeOpacity.value) / 100);
  });
  elements.serverStatusControl.addEventListener("click", async () => {
    elements.serverStatusDialog.showModal();
    await Promise.all([
      updateGameTime(),
      updateServerVersion(),
      updateDetailedServerStatus(),
    ]);
  });
  elements.serverStatusClose.addEventListener("click", () => {
    elements.serverStatusDialog.close();
  });
  elements.restartControl.addEventListener("click", () => {
    if (restartState === "pending") {
      cancelRestart();
    } else {
      openRestartDialog();
    }
  });
  elements.restartDialogCancel.addEventListener("click", () => {
    elements.restartForm.reset();
    elements.restartDialog.close();
  });
  elements.restartForm.addEventListener("submit", (event) => {
    event.preventDefault();
    requestRestart();
  });
  elements.guideControl.addEventListener("click", openGuide);
  elements.guideClose.addEventListener("click", closeGuide);
  elements.guideStart.addEventListener("click", closeGuide);
  elements.guideDialog.addEventListener("close", markGuideSeen);
  window.addEventListener("resize", () => {
    if (map) {
      map.invalidateSize({ pan: false });
    }
  });
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      checkAppVersion();
      refreshVisibleUnexploredTiles(true);
      updateGameTime();
      updateGameSchedule();
      updateServerVersion();
      updateDetailedServerStatus();
      updateRestartStatus();
      updateMapEntities();
      updatePlayers();
      if (elements.activityDialog.open) {
        updateActivity();
      }
    }
  });

  async function loadFeatures() {
    try {
      const response = await fetch(FEATURES_URL, {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!response.ok) {
        return;
      }
      const payload = await response.json();
      restartEnabled = payload?.data?.restart === true;
    } catch {
      restartEnabled = false;
    }
  }

  document.documentElement.dataset.appVersion = APP_VERSION;
  loadMap();
  checkAppVersion();
  appVersionTimer = window.setInterval(
    checkAppVersion,
    APP_VERSION_REFRESH_MS,
  );
  startGameScheduleUpdates();
  startServerVersionUpdates();
  if (playerAuth) {
    loadFeatures().then(() => checkAuthentication()).then((authenticated) => {
      if (!authenticated || !map || !playerLayer) {
        return;
      }
      playersVisible = true;
      playerLayer.addTo(map);
      updatePlayers();
      startPlayerUpdates();
      updateMapEntities();
      startMapEntityUpdates();
      updateDetailedServerStatus();
      setPlayerButton();
    });
  } else {
    loadFeatures();
  }
})();
