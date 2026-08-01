"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const {
  findWindow,
  parseWindows,
} = require("../site/assets/maintenance.js");

test("予定メンテナンス時間の開始を含み終了を含まない", () => {
  assert.deepEqual(
    findWindow(
      new Date("2026-08-01T00:00:00Z"),
      "Asia/Tokyo",
      "09:00-09:20,23:00-23:20",
    )?.start,
    "09:00",
  );
  assert.equal(
    findWindow(
      new Date("2026-08-01T00:20:00Z"),
      "Asia/Tokyo",
      "09:00-09:20,23:00-23:20",
    ),
    null,
  );
});

test("日付をまたぐ時間帯を判定する", () => {
  const windows = "23:50-00:10";
  assert.equal(
    findWindow(
      new Date("2026-08-01T14:55:00Z"),
      "Asia/Tokyo",
      windows,
    )?.start,
    "23:50",
  );
  assert.equal(
    findWindow(
      new Date("2026-08-01T15:05:00Z"),
      "Asia/Tokyo",
      windows,
    )?.end,
    "00:10",
  );
});

test("不正な時間帯とタイムゾーンはメンテナンス扱いにしない", () => {
  assert.deepEqual(
    parseWindows("09:00-09:00,25:00-26:00,invalid"),
    [],
  );
  assert.equal(
    findWindow(new Date(), "Invalid/Zone", "09:00-09:20"),
    null,
  );
});
