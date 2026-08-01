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

  const WEEKDAYS = Object.freeze({
    Sun: 0,
    Mon: 1,
    Tue: 2,
    Wed: 3,
    Thu: 4,
    Fri: 5,
    Sat: 6,
  });

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

  function parseWeeklyWindows(rawWindows) {
    const values = Array.isArray(rawWindows)
      ? rawWindows
      : String(rawWindows || "").split(",");

    return values.flatMap((rawValue) => {
      const value = String(rawValue).trim();
      const match = /^([A-Za-z]{3}(?:\+[A-Za-z]{3})*)@(.+)$/.exec(value);
      if (!match) {
        return [];
      }
      const days = match[1].split("+").map((day) => WEEKDAYS[day]);
      const windows = parseWindows(match[2]);
      if (
        windows.length !== 1
        || days.some((day) => day === undefined)
        || new Set(days).size !== days.length
      ) {
        return [];
      }
      return [{ ...windows[0], days }];
    });
  }

  function timeInTimeZone(now, timeZone) {
    try {
      const parts = new Intl.DateTimeFormat("en-US", {
        timeZone,
        weekday: "short",
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
      }).formatToParts(now);
      const values = Object.fromEntries(
        parts.map((part) => [part.type, part.value]),
      );
      const weekday = WEEKDAYS[values.weekday];
      if (weekday === undefined) {
        return null;
      }
      return {
        minute: (Number(values.hour) * 60) + Number(values.minute),
        weekday,
      };
    } catch {
      return null;
    }
  }

  function findWindow(
    now,
    timeZone,
    rawWindows,
    rawWeeklyWindows = "",
  ) {
    const current = timeInTimeZone(now, timeZone);
    if (current === null) {
      return null;
    }

    const windows = [
      ...parseWindows(rawWindows),
      ...parseWeeklyWindows(rawWeeklyWindows),
    ];
    return windows.find((window) => {
      const active = window.startMinute < window.endMinute
        ? current.minute >= window.startMinute
          && current.minute < window.endMinute
        : current.minute >= window.startMinute
          || current.minute < window.endMinute;
      if (!active || !window.days) {
        return active;
      }
      if (window.startMinute < window.endMinute) {
        return window.days.includes(current.weekday);
      }
      const startWeekday = current.minute >= window.startMinute
        ? current.weekday
        : (current.weekday + 6) % 7;
      return window.days.includes(startWeekday);
    }) || null;
  }

  return { findWindow, parseWeeklyWindows, parseWindows };
});
