((root, factory) => {
  "use strict";

  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.LiveMapMaintenance = Object.freeze(api);
  }
})(typeof globalThis === "object" ? globalThis : this, () => {
  "use strict";

  function parseClock(value) {
    const match = /^([01]\d|2[0-3]):([0-5]\d)$/.exec(value);
    if (!match) {
      return null;
    }
    return (Number(match[1]) * 60) + Number(match[2]);
  }

  function parseWindows(rawWindows) {
    const values = Array.isArray(rawWindows)
      ? rawWindows
      : String(rawWindows || "").split(",");

    return values.flatMap((rawValue) => {
      const value = String(rawValue).trim();
      const match = /^([^\s-]+)\s*-\s*([^\s-]+)$/.exec(value);
      if (!match) {
        return [];
      }
      const startMinute = parseClock(match[1]);
      const endMinute = parseClock(match[2]);
      if (
        startMinute === null
        || endMinute === null
        || startMinute === endMinute
      ) {
        return [];
      }
      return [{
        start: match[1],
        end: match[2],
        startMinute,
        endMinute,
      }];
    });
  }

  function minuteInTimeZone(now, timeZone) {
    try {
      const parts = new Intl.DateTimeFormat("en-GB", {
        timeZone,
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
      }).formatToParts(now);
      const values = Object.fromEntries(
        parts.map((part) => [part.type, part.value]),
      );
      return (Number(values.hour) * 60) + Number(values.minute);
    } catch {
      return null;
    }
  }

  function findWindow(now, timeZone, rawWindows) {
    const currentMinute = minuteInTimeZone(now, timeZone);
    if (currentMinute === null) {
      return null;
    }

    return parseWindows(rawWindows).find((window) => {
      if (window.startMinute < window.endMinute) {
        return currentMinute >= window.startMinute
          && currentMinute < window.endMinute;
      }
      return currentMinute >= window.startMinute
        || currentMinute < window.endMinute;
    }) || null;
  }

  return { findWindow, parseWindows };
});
