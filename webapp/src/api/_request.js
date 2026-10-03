import { locale } from "../i18n/index.js";
import { noteAnswer, noteFailure, ServerUnreachable } from "../composables/useServerReach.js";

// Tailscale serve answers 502 when nothing listens behind it, and the app never sends
// one itself: a 502 means the VM is up and echo-words is not.
const APP_DOWN = 502;

export async function apiRequest(path, { method = "GET", body, timeoutMs } = {}) {
  const init = { method, headers: { "Accept-Language": locale.value } };
  let timer;
  if (timeoutMs) {
    // A plain timer rather than AbortSignal.timeout, so a test's fake clock drives it.
    const controller = new AbortController();
    timer = setTimeout(() => controller.abort(), timeoutMs);
    init.signal = controller.signal;
  }
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  try {
    const resp = await fetch(path, init);
    if (resp.status === APP_DOWN) throw noteFailure("app-down");
    noteAnswer();
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      const detail = err.detail;
      const message = Array.isArray(detail)
        ? detail[0]?.msg || `HTTP ${resp.status}`
        : detail || `HTTP ${resp.status}`;
      const e = new Error(message);
      e.status = resp.status;
      throw e;
    }
    if (resp.status === 204 || resp.headers.get("content-length") === "0") return null;
    return await resp.json();
  } catch (error) {
    if (error instanceof ServerUnreachable || error?.status) throw error;
    if (error?.name === "AbortError") throw noteFailure("no-answer");
    if (error instanceof TypeError) {
      throw noteFailure(globalThis.navigator?.onLine === false ? "offline" : "unreachable");
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
