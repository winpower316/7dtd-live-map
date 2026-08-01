"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const {
  findWindow,
  parseWeeklyWindows,
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

test("指定曜日だけ週次メンテナンス時間として判定する", () => {
  const weeklyWindows = "Sun+Wed+Fri+Sat@20:00-20:20";
  for (const date of ["2026-08-01", "2026-08-02"]) {
    assert.equal(
      findWindow(
        new Date(`${date}T11:05:00Z`),
        "Asia/Tokyo",
        "",
        weeklyWindows,
      )?.start,
      "20:00",
    );
  }
  assert.equal(
    findWindow(
      new Date("2026-08-03T11:05:00Z"),
      "Asia/Tokyo",
      "",
      weeklyWindows,
    ),
    null,
  );
});

test("日付をまたぐ週次時間帯は開始日の曜日を使う", () => {
  const weeklyWindows = "Sat@23:50-00:10";
  assert.equal(
    findWindow(
      new Date("2026-08-01T14:55:00Z"),
      "Asia/Tokyo",
      "",
      weeklyWindows,
    )?.start,
    "23:50",
  );
  assert.equal(
    findWindow(
      new Date("2026-08-01T15:05:00Z"),
      "Asia/Tokyo",
      "",
      weeklyWindows,
    )?.end,
    "00:10",
  );
});

test("不正な時間帯とタイムゾーンはメンテナンス扱いにしない", () => {
  assert.deepEqual(
    parseWindows("09:00-09:00,25:00-26:00,invalid"),
    [],
  );
  assert.deepEqual(
    parseWeeklyWindows("Funday@20:00-20:20,Sun+Sun@20:00-20:20"),
    [],
  );
  assert.equal(
    findWindow(new Date(), "Invalid/Zone", "09:00-09:20"),
    null,
  );
});
