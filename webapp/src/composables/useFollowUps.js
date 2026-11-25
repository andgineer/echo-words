import { reactive, watch } from "vue";
import { streamQuestion } from "../api/ask.js";
import { chipLabel, chipNote, visibleSegments } from "./entryChips.js";
import { entries, upsertEntry } from "./useEntries.js";
import { createRequestId } from "./useResendQueue.js";
import { ServerUnreachable } from "./useServerReach.js";

// Turns this page is answering right now. A turn stored as asking that is not here was
// interrupted by a reload or a closed tab, and is shown as cut off.
const live = reactive(new Set());
// The server's refusal of a question as sent, an answer to one request: shown under
// the field until the next question, never stored.
export const refusals = reactive({});

const REFUSED = new Set([400, 413, 422]);

function find(entryId) {
  return entries.value.find((entry) => entry.entry_id === entryId);
}

export function turnState(turn) {
  return turn.state === "asking" && !live.has(turn.id) ? "cut" : turn.state;
}

export function isAsking(entry) {
  return (entry?.follow_ups ?? []).some((turn) => turnState(turn) === "asking");
}

export function setDraft(entryId, text) {
  if (find(entryId)) upsertEntry({ entry_id: entryId, follow_up_draft: text });
}

function update(entryId, turnId, change) {
  const turns = find(entryId)?.follow_ups ?? [];
  if (!turns.some((turn) => turn.id === turnId)) return;
  upsertEntry({
    entry_id: entryId,
    follow_ups: turns.map((turn) =>
      turn.id === turnId
        ? { ...turn, ...(typeof change === "function" ? change(turn) : change) }
        : turn,
    ),
  });
}

function refuse(entryId, turnId, reason) {
  const entry = find(entryId);
  if (!entry) return;
  const turns = entry.follow_ups ?? [];
  const turn = turns.find((item) => item.id === turnId);
  refusals[entryId] = reason;
  const typed = entry.follow_up_draft ?? "";
  upsertEntry({
    entry_id: entryId,
    follow_ups: turns.filter((item) => item.id !== turnId),
    // The question goes back into the field so it can be shortened and sent again,
    // ahead of anything typed since rather than in place of it.
    ...(turn ? { follow_up_draft: typed ? `${turn.question} ${typed}` : turn.question } : {}),
  });
}

function finished(entry) {
  return entry.status === "done" && entry.shape === "unit";
}

// The question is asked about what the reader is looking at, so an article still being
// written, or an analysis run again meanwhile, is waited for rather than sent half-done.
function entrySettled(entryId) {
  const settled = () => {
    const entry = find(entryId);
    return !entry || (entry.status !== "pending" && !entry.detail_pending);
  };
  if (settled()) return Promise.resolve();
  return new Promise((resolve) => {
    const stop = watch(settled, (done) => {
      if (!done) return;
      stop();
      resolve();
    });
  });
}

export function material(entry, turnId) {
  const turns = entry.follow_ups ?? [];
  const at = turns.findIndex((turn) => turn.id === turnId);
  return {
    lang: entry.lang,
    word: entry.word,
    analysed_as: entry.analysed_as || "",
    context: entry.context || "",
    analysis: entry.text || "",
    chips: visibleSegments(entry).map((segment) => ({
      label: chipLabel(entry, segment),
      note: chipNote(entry, segment),
    })),
    detail: entry.detail_html || "",
    // A reply that never finished is not something the model said.
    exchanges: turns
      .slice(0, at)
      .filter((turn) => turn.state === "done")
      .map(({ question, answer }) => ({ question, answer })),
    question: turns[at].question,
  };
}

async function run(entryId, turnId) {
  try {
    await entrySettled(entryId);
    const entry = find(entryId);
    if (!entry?.follow_ups?.some((turn) => turn.id === turnId)) return;
    if (!finished(entry)) {
      update(entryId, turnId, { state: "cut" });
      return;
    }
    let ended = false;
    await streamQuestion(entryId, material(entry, turnId), (name, data) => {
      if (name === "delta") {
        update(entryId, turnId, (turn) => ({ answer: turn.answer + (data.text ?? "") }));
      } else if (name === "reset") {
        update(entryId, turnId, { answer: "" });
      } else if (name === "done") {
        ended = true;
        // A reply stopped at the size bound is not the whole answer.
        update(entryId, turnId, { state: data.complete === false ? "cut" : "done" });
      }
    });
    if (!ended) update(entryId, turnId, { state: "cut" });
  } catch (error) {
    if (REFUSED.has(error.status)) refuse(entryId, turnId, error.message);
    else update(entryId, turnId, { state: "cut", unsent: error instanceof ServerUnreachable });
  } finally {
    live.delete(turnId);
  }
}

export async function ask(entryId) {
  const entry = find(entryId);
  const question = (entry?.follow_up_draft ?? "").trim();
  if (!question || isAsking(entry)) return;
  delete refusals[entryId];
  const turn = { id: createRequestId(), question, answer: "", state: "asking" };
  live.add(turn.id);
  upsertEntry({
    entry_id: entryId,
    follow_up_draft: "",
    follow_ups: [...(entry.follow_ups ?? []), turn],
  });
  await run(entryId, turn.id);
}

export async function retry(entryId, turnId) {
  const entry = find(entryId);
  if (!entry?.follow_ups?.some((turn) => turn.id === turnId) || isAsking(entry)) return;
  delete refusals[entryId];
  live.add(turnId);
  update(entryId, turnId, { state: "asking", answer: "", unsent: false });
  await run(entryId, turnId);
}

export function _resetForTest() {
  live.clear();
  for (const key of Object.keys(refusals)) delete refusals[key];
}
