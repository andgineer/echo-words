import { computed, ref } from "vue";
import { t } from "../i18n/index.js";

const STORAGE_KEY = "echo-words-server-reach";

export const REACH_KINDS = ["offline", "unreachable", "no-answer", "app-down"];

export class ServerUnreachable extends Error {
  constructor(kind) {
    super(t(`reach.${kind}`));
    this.name = "ServerUnreachable";
    this.kind = kind;
  }
}

function emptyReach() {
  return { answeredAt: null, failure: null };
}

function loadReach() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    if (!saved || typeof saved !== "object") return emptyReach();
    const failure = saved.failure;
    return {
      answeredAt: Number.isFinite(saved.answeredAt) ? saved.answeredAt : null,
      failure:
        REACH_KINDS.includes(failure?.kind) && Number.isFinite(failure.at)
          ? { kind: failure.kind, at: failure.at }
          : null,
    };
  } catch {
    return emptyReach();
  }
}

export const serverReach = ref(loadReach());

// A phone with no network knows it already; only the other kinds need pointing out.
export const serverUnanswered = computed(() => {
  const kind = serverReach.value.failure?.kind;
  return Boolean(kind) && kind !== "offline";
});

function saveReach() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(serverReach.value));
  } catch {
    // the note only lives as long as this page
  }
}

export function noteAnswer() {
  serverReach.value = { answeredAt: Date.now(), failure: null };
  saveReach();
}

export function noteFailure(kind) {
  serverReach.value = { ...serverReach.value, failure: { kind, at: Date.now() } };
  saveReach();
  return new ServerUnreachable(kind);
}

export function _resetForTest() {
  serverReach.value = loadReach();
}
