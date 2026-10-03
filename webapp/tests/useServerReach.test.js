import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  _resetForTest,
  noteAnswer,
  noteFailure,
  serverReach,
  serverUnanswered,
} from "../src/composables/useServerReach.js";
import { EPIC, FEATURE, labelBehavior } from "./allure-taxonomy.js";

const KEY = "echo-words-server-reach";

beforeEach(async () => {
  await labelBehavior(EPIC.APPLICATION_PLATFORM, FEATURE.PWA_RESILIENCE, "Server not answering");
  localStorage.clear();
  _resetForTest();
});

afterEach(() => {
  localStorage.clear();
});

describe("server reach", () => {
  it("keeps the last answer and the failure after it across a reload", () => {
    noteAnswer();
    noteFailure("no-answer");

    _resetForTest();

    expect(serverReach.value.answeredAt).toBeGreaterThan(0);
    expect(serverReach.value.failure).toMatchObject({ kind: "no-answer" });
  });

  it("clears the failure on the next answer", () => {
    noteFailure("app-down");
    noteAnswer();

    expect(serverReach.value.failure).toBeNull();
    expect(serverUnanswered.value).toBe(false);
  });

  it("does not flag a device that simply has no network", () => {
    noteFailure("offline");
    expect(serverUnanswered.value).toBe(false);

    noteFailure("unreachable");
    expect(serverUnanswered.value).toBe(true);
  });

  it.each([
    ["{not json", { answeredAt: null, failure: null }],
    [JSON.stringify({ answeredAt: "yesterday", failure: { kind: "moon", at: 1 } }), { answeredAt: null, failure: null }],
    [JSON.stringify({ answeredAt: 5, failure: { kind: "no-answer", at: 6, extra: 1 } }), { answeredAt: 5, failure: { kind: "no-answer", at: 6 } }],
  ])("reads what storage holds without trusting it (%s)", (stored, expected) => {
    localStorage.setItem(KEY, stored);

    _resetForTest();

    expect(serverReach.value).toEqual(expected);
  });
});
