import { onScopeDispose, ref, watch } from "vue";
import { apiRequest } from "../api/_request.js";
import { applyReceipt } from "./useEntries.js";
import { serverReach, ServerUnreachable } from "./useServerReach.js";

const STORAGE_KEY = "echo-words-resend-queue";
const REFUSED_KEY = "echo-words-resend-refused";
// Submitting only registers the word; the answer arrives over the event stream.
export const SUBMIT_TIMEOUT_MS = 15_000;
export const RECHECK_INTERVAL_MS = 30_000;

export const queuedWords = ref([]);
export const refusedWords = ref([]);
let flushing = null;

function loadQueue() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    queuedWords.value = Array.isArray(saved)
      ? saved.map((item) => ({ ...item, body: withRequestId(item.body) }))
      : [];
    saveQueue();
  } catch {
    queuedWords.value = [];
  }
}

function saveQueue() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(queuedWords.value));
}

function loadRefused() {
  try {
    const saved = JSON.parse(localStorage.getItem(REFUSED_KEY) || "[]");
    refusedWords.value = Array.isArray(saved) ? saved : [];
  } catch {
    refusedWords.value = [];
  }
}

function saveRefused() {
  localStorage.setItem(REFUSED_KEY, JSON.stringify(refusedWords.value));
}

function createRequestId() {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  const bytes = new Uint8Array(16);
  if (typeof globalThis.crypto?.getRandomValues === "function") {
    globalThis.crypto.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256);
    }
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function withRequestId(body) {
  return body.request_id ? body : { ...body, request_id: createRequestId() };
}

export function enqueueWord(body) {
  queuedWords.value.push({ body: withRequestId(body), queued_at: Date.now() });
  saveQueue();
}

export function dismissRefusal(index) {
  refusedWords.value = refusedWords.value.filter((_, at) => at !== index);
  saveRefused();
}

// A passage cut to 16 and a short word behind it fit a 360px phone's line in either
// interface language; cut to 24 they need 390px.
const PREVIEW_LENGTH = 16;
const graphemes = new Intl.Segmenter(undefined, { granularity: "grapheme" });

export function preview(text) {
  const characters = Array.from(graphemes.segment(text), ({ segment }) => segment);
  if (characters.length <= PREVIEW_LENGTH) return text;
  return `${characters.slice(0, PREVIEW_LENGTH).join("").trimEnd()}…`;
}

// Receipts still on their way. A stream that opens meanwhile may have missed the whole
// answer, and only the receipt names the entry its catch-up has to fetch.
export const receiptsInFlight = new Set();

export async function submitWord(body, onReceipt) {
  const submission = apiRequest("/api/words", {
    method: "POST",
    body,
    timeoutMs: SUBMIT_TIMEOUT_MS,
  }).then((accepted) => {
    onReceipt(accepted);
    return accepted;
  });
  receiptsInFlight.add(submission);
  try {
    return await submission;
  } finally {
    receiptsInFlight.delete(submission);
  }
}

export function isRetryableWordError(error) {
  return error instanceof ServerUnreachable || error?.status >= 500;
}

// Sent again, a refused word is refused again, and it would hold back every word behind it.
function isRefusal(error) {
  return error?.status >= 400 && error.status < 500;
}

function refuse(item, reason) {
  loadRefused();
  refusedWords.value.push({ word: item.body.word, reason });
  saveRefused();
}

async function sendHead() {
  const item = queuedWords.value[0];
  try {
    await submitWord(item.body, (accepted) => {
      // The POST can finish before SSE connects. Keep its receipt so reconnect
      // can recover this one answer without downloading a server history.
      if (!accepted?.entry_id) return;
      applyReceipt({
        entry_id: accepted.entry_id,
        word: accepted.word ?? item.body.word,
        lang: item.body.lang,
        lookup_only: accepted.lookup_only ?? item.body.lookup_only,
        context: item.body.context || "",
        requested_shape: item.body.shape ?? null,
        requested_reverse: accepted.reverse ?? null,
      });
    });
  } catch (error) {
    if (!isRefusal(error)) throw error;
    refuse(item, error.message);
  }
  queuedWords.value.shift();
  saveQueue();
}

async function sendQueued() {
  try {
    loadQueue();
    while (queuedWords.value.length) await sendHead();
    return null;
  } catch (error) {
    return error;
  } finally {
    flushing = null;
  }
}

// One flush at a time, settling on what stopped it or on null. It starts a tick late: run
// at once, an empty queue's flush clears the guard before `??=` sets it, which then stays.
export function flushQueue() {
  flushing ??= Promise.resolve().then(sendQueued);
  return flushing;
}

// Any answer, whatever asked for it, says the server is back; a page left on screen
// asks again by itself, so a word saved during an outage never waits for the next open.
export function resendWhileWaiting(visible) {
  let recheck = null;
  watch(
    serverReach,
    (reach) => {
      if (!reach.failure && queuedWords.value.length) void flushQueue();
    },
    { flush: "sync" },
  );
  watch(
    () => queuedWords.value.length > 0 && visible.value,
    (waiting) => {
      clearInterval(recheck);
      recheck = waiting ? setInterval(flushQueue, RECHECK_INTERVAL_MS) : null;
    },
    { immediate: true },
  );
  onScopeDispose(() => clearInterval(recheck));
}

export function useResendQueue() {
  loadQueue();
  loadRefused();
  return { queuedWords, refusedWords, dismissRefusal };
}

export function _resetForTest() {
  flushing = null;
  queuedWords.value = [];
  refusedWords.value = [];
}
