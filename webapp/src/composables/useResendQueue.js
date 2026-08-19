import { ref } from "vue";
import { apiRequest } from "../api/_request.js";

const STORAGE_KEY = "echo-words-resend-queue";

export const queuedWords = ref([]);
let inFlight = false;

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

export function isRetryableWordError(error) {
  return error instanceof TypeError || error?.status >= 500;
}

export async function flushQueue() {
  if (inFlight) return;
  inFlight = true;
  loadQueue();
  try {
    while (queuedWords.value.length) {
      const item = queuedWords.value[0];
      try {
        await apiRequest("/api/words", { method: "POST", body: item.body });
        queuedWords.value.shift();
        saveQueue();
      } catch (error) {
        break;
      }
    }
  } finally {
    inFlight = false;
  }
}

export function useResendQueue() {
  loadQueue();
  return { queuedWords, enqueueWord, flushQueue };
}

export function _resetForTest() {
  inFlight = false;
  queuedWords.value = [];
}
