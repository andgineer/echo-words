import { apiRequest } from "../api/_request.js";
import { entries, replaceEntries, upsertEntry } from "./useEntries.js";

function eventData(event) {
  try {
    return JSON.parse(event.data);
  } catch {
    return null;
  }
}

export function useEventStream({
  EventSourceClass = globalThis.EventSource,
  fetchRecent = () => apiRequest("/api/words/recent"),
} = {}) {
  let source = null;
  let activeRefresh = null;

  async function refresh() {
    const refreshState = { events: [] };
    activeRefresh = refreshState;
    try {
      const snapshot = await fetchRecent();
      if (activeRefresh !== refreshState) return;
      replaceEntries(snapshot);
      activeRefresh = null;
      for (const { name, data } of refreshState.events) applyData(name, data);
    } finally {
      if (activeRefresh === refreshState) activeRefresh = null;
    }
  }

  function applyData(name, data) {
    if (name === "accepted") {
      upsertEntry(data, { newest: true });
    } else if (name === "update") {
      const text = data.text ?? data.content ?? "";
      upsertEntry({ entry_id: data.entry_id, text });
    } else if (name === "reset") {
      upsertEntry({
        entry_id: data.entry_id,
        text: "",
        status: "pending",
        error: null,
        ...(Object.hasOwn(data, "detail_html") ? { detail_html: data.detail_html } : {}),
      });
    } else if (name === "done") {
      upsertEntry({ ...data, status: "done" });
    } else if (name === "detail") {
      upsertEntry({
        entry_id: data.entry_id,
        detail_html: data.text,
        detail_error: data.error,
      });
    } else if (name === "control_error") {
      upsertEntry({ entry_id: data.entry_id, control_error: data.message });
    } else if (name === "error") {
      upsertEntry({ entry_id: data.entry_id, status: "error", error: data.code });
    }
  }

  function apply(name, event) {
    const data = eventData(event);
    if (!data?.entry_id) return;
    applyData(name, data);
    activeRefresh?.events.push({ name, data });
  }

  function start() {
    if (source || typeof EventSourceClass !== "function") return source;
    source = new EventSourceClass("/api/events");
    source.addEventListener("open", () => {
      void refresh().catch(() => {});
    });
    for (const name of [
      "accepted",
      "update",
      "reset",
      "done",
      "detail",
      "control_error",
      "error",
    ]) {
      source.addEventListener(name, (event) => apply(name, event));
    }
    return source;
  }

  function stop() {
    source?.close();
    source = null;
  }

  return { entries, refresh, start, stop };
}
