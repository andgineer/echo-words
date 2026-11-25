import { locale } from "../i18n/index.js";
import { noteAnswer, noteFailure } from "../composables/useServerReach.js";
import { APP_DOWN, refusal, unreached } from "./_request.js";

function dispatch(block, onEvent) {
  let name = "message";
  const data = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /u, ""));
  }
  let parsed = {};
  try {
    parsed = JSON.parse(data.join("\n") || "{}");
  } catch {
    // A block that is not JSON carries nothing the reply can use.
  }
  onEvent(name, parsed);
}

// EventSource only issues GET, and the question travels in a POST body, so the
// event stream is read off the response by hand.
export async function streamQuestion(entryId, body, onEvent) {
  const resp = await fetch(`/api/words/${encodeURIComponent(entryId)}/ask`, {
    method: "POST",
    headers: { "Accept-Language": locale.value, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).catch((error) => {
    throw unreached(error);
  });
  if (resp.status === APP_DOWN) throw noteFailure("app-down");
  noteAnswer();
  if (!resp.ok) throw await refusal(resp);
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n?/gu, "\n");
    for (let cut = buffer.indexOf("\n\n"); cut >= 0; cut = buffer.indexOf("\n\n")) {
      dispatch(buffer.slice(0, cut), onEvent);
      buffer = buffer.slice(cut + 2);
    }
  }
  if (buffer.trim()) dispatch(buffer, onEvent);
}
