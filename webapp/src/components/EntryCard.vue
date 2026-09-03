<script setup>
import { computed, ref, watch } from "vue";
import { useI18n } from "../i18n/index.js";

const { t, tn } = useI18n();

const props = defineProps({
  entry: { type: Object, required: true },
  busy: { type: Boolean, default: false },
  // Which side the card comes in from: +1 for a later entry, -1 for an earlier one.
  direction: { type: Number, default: 1 },
});
const emit = defineEmits(["switch", "detail", "delete-card", "retry", "segment", "swipe"]);

const SWIPE_THRESHOLD = 55;
const ARRIVAL_OFFSET = 44;
const FADE_TRAVEL = 420;

const dragX = ref(0);
const dragging = ref(false);
const confirming = ref(false);
let startX = 0;
let held = false;

const CARD_STATUS_KEYS = {
  added: "card.added",
  lookup_only: "card.lookupOnly",
  deleted: "card.deleted",
  failed: "card.failed",
  unattested: "card.unattested",
  misspelled: "card.misspelled",
};

const CARD_KIND_KEYS = {
  Recognition: "card.kind.recognition",
  Recall: "card.kind.recall",
  ContextRecognition: "card.kind.contextRecognition",
  ContextProduction: "card.kind.contextProduction",
};

const isText = computed(() => props.entry.shape === "text");
const isPending = computed(() => props.entry.status === "pending");
const working = computed(() => isPending.value || !!props.entry.detail_pending);
const busyLabel = computed(() =>
  isPending.value
    ? t("add.analysing", { word: props.entry.word })
    : t("add.buildingEntry"),
);

// The deeper analysis is offered on any finished word answer; a running text has no
// single word to go deeper on. Deleting is offered only where a note exists to delete.
const showsDetail = computed(() => props.entry.status === "done" && props.entry.shape === "unit");
const showsDelete = computed(
  () =>
    showsDetail.value &&
    (props.entry.card_status === "added" || !!props.entry.card_kept),
);
const showsActions = computed(() => showsDetail.value && !working.value);

watch(
  () => props.entry.entry_id,
  () => {
    confirming.value = false;
    arrive();
  },
);

// A tap that silently swaps the text reads as nothing having happened, so every
// switch is a movement: the card is placed to one side without a transition, then
// released into the settle the drag itself uses.
function arrive() {
  dragging.value = true;
  dragX.value = props.direction >= 0 ? ARRIVAL_OFFSET : -ARRIVAL_OFFSET;
  const settle = () => {
    dragging.value = false;
    dragX.value = 0;
  };
  if (typeof requestAnimationFrame === "function") {
    requestAnimationFrame(() => requestAnimationFrame(settle));
  } else {
    setTimeout(settle, 20);
  }
}

// `setPointerCapture` is deliberately not called: in Chrome it lands the click on
// the capturing element and eats every tap on the buttons inside the card.
function onPointerDown(event) {
  if (event.target.closest("button, a, audio, input, textarea, select")) return;
  startX = event.clientX;
  held = true;
  dragging.value = true;
  dragX.value = 0;
}

function onPointerMove(event) {
  if (!held) return;
  dragX.value = event.clientX - startX;
}

function onPointerUp() {
  if (!held) return;
  held = false;
  const shift = dragX.value;
  dragging.value = false;
  dragX.value = 0;
  if (shift <= -SWIPE_THRESHOLD) emit("swipe", 1);
  else if (shift >= SWIPE_THRESHOLD) emit("swipe", -1);
}

const deckStyle = computed(() => ({
  transform: `translateX(${dragX.value}px)`,
  opacity: String(1 - Math.min(Math.abs(dragX.value) / FADE_TRAVEL, 0.4)),
}));

function cardKindsText(kinds) {
  const counted = [];
  for (const kind of kinds) {
    const label = t(CARD_KIND_KEYS[kind] ?? kind);
    const seen = counted.find((item) => item.label === label);
    if (seen) seen.count += 1;
    else counted.push({ label, count: 1 });
  }
  return counted.map(({ label, count }) => (count > 1 ? `${label} ×${count}` : label)).join(", ");
}

function cardStatusLabel(entry) {
  const kinds = entry.card_kinds ?? [];
  if (entry.card_status === "added" && kinds.length) {
    return tn("card.addedCount", kinds.length, { kinds: cardKindsText(kinds) });
  }
  return t(CARD_STATUS_KEYS[entry.card_status] ?? entry.card_status);
}

const cardStatusText = computed(() => {
  const entry = props.entry;
  if (!entry.card_status) return "";
  const parts = [entry.card_error ? `⚠️ ${entry.card_error}` : cardStatusLabel(entry)];
  if (entry.card_kept) parts.push(t("card.kept"));
  if (entry.no_audio) parts.push(t("card.noAudio"));
  if (entry.no_card_audio) parts.push(t("card.noCardAudio"));
  return parts.join(" · ");
});

const spellingNotice = computed(() => {
  // Whatever the answer did with the spelling is said above the analysis, because
  // the analysis may be of another word and the card was made without asking.
  const entry = props.entry;
  if (entry.status !== "done") return "";
  if (entry.card_status === "unattested") {
    // A lookup asked for no card, so it is not one that was withheld.
    return entry.lookup_only
      ? t("add.unattestedLookup", { word: entry.word })
      : t("add.unattested", { word: entry.word });
  }
  if (entry.card_status === "misspelled") {
    return t("add.misspelled", { word: entry.word, suggestion: entry.suggestion });
  }
  if (entry.analysed_as) {
    // Always said, whatever the difference is called: the reader typed one wording and
    // is reading about another. Only a suspected misspelling is named as one.
    if (entry.card_status !== "added") {
      return t("add.analysedInstead", { word: entry.word, shown: entry.analysed_as });
    }
    return entry.typo_suspected
      ? t("add.cardedInstead", { word: entry.word, carded: entry.analysed_as })
      : t("add.otherWordCard", { word: entry.word, carded: entry.analysed_as });
  }
  if (entry.suggestion) {
    if (entry.showing_other_spelling) {
      return t("add.showingOther", { word: entry.word, submitted: entry.suggestion });
    }
    // Only an answer that vouched for the wording can call another one "more usual".
    // One that called it a misspelling says that instead, and says it without
    // claiming a card the entry may not have.
    return entry.typo_suspected
      ? t("add.misspelled", { word: entry.word, suggestion: entry.suggestion })
      : t("add.moreCommon", { word: entry.word, suggestion: entry.suggestion });
  }
  return "";
});

// The wording the note actually teaches, which is what the dictionary was asked about.
const taughtWord = computed(
  () => props.entry.analysed_as || props.entry.shown_spelling || props.entry.word,
);

const correctionLabel = computed(() => {
  // The offer points back to the reader's own spelling once the entry shows another,
  // and its wording follows the card: there is nothing to replace without one.
  const entry = props.entry;
  if (entry.showing_other_spelling) return t("add.revert", { word: entry.suggestion });
  return entry.card_status === "added"
    ? t("add.replaceCard", { word: entry.suggestion })
    : t("add.analyseInstead", { word: entry.suggestion });
});

const errorText = computed(() =>
  props.entry.error === "analysis_failed" ? t("add.analysisFailed") : props.entry.error,
);

function confirmDelete() {
  confirming.value = false;
  emit("delete-card");
}
</script>

<template>
  <article
    class="card deck"
    :class="{ settling: !dragging }"
    :style="deckStyle"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerUp"
    @pointerleave="onPointerUp"
  >
    <div v-if="working" class="progress"><div class="progress-bar"></div></div>

    <div class="entry-head">
      <span class="entry-title" :class="isText ? 'kind' : 'word'">
        {{ isText ? t("add.sentence") : entry.word }}
      </span>
      <span v-if="entry.model" class="entry-model">{{ entry.model }}</span>
    </div>

    <p v-if="isText && entry.text" class="entry-source">{{ entry.word }}</p>

    <div v-if="isPending" class="working pending">
      <span class="spinner" aria-hidden="true"></span>
      <span>{{ busyLabel }}</span>
    </div>

    <div v-if="spellingNotice" class="entry-notice">
      <p class="notice-text">{{ spellingNotice }}</p>
      <button
        v-if="entry.suggestion"
        class="btn-inline correction"
        @click="emit('switch')"
      >
        {{ correctionLabel }}
      </button>
    </div>

    <div v-if="entry.not_in_references" class="entry-notice unverified">
      <p class="notice-text">{{ t("add.notInReferences", { word: taughtWord }) }}</p>
      <a
        v-if="entry.usage_search_url"
        class="btn-inline usage-search"
        :href="entry.usage_search_url"
        target="_blank"
        rel="noopener noreferrer"
        >{{ t("add.seeUsageSearch") }}</a
      >
    </div>

    <div v-if="entry.text" class="entry-text" v-html="entry.text"></div>
    <div v-if="entry.detail_html" class="entry-detail" v-html="entry.detail_html"></div>

    <audio
      v-if="entry.audio_url"
      class="entry-audio"
      :src="entry.audio_url"
      controls
      autoplay
      preload="none"
    ></audio>
    <div v-if="entry.context_audio_url" class="context-audio">
      <p class="context-audio-title">{{ t("add.contextAudio") }}</p>
      <audio
        class="entry-audio context-audio-player"
        :src="entry.context_audio_url"
        controls
        preload="none"
      ></audio>
    </div>

    <div v-if="entry.segments?.length" class="segments">
      <div
        v-for="(segment, index) in entry.segments"
        :key="`${index}|${segment.label}`"
        class="segment"
      >
        <button class="segment-label" :disabled="busy" @click="emit('segment', segment)">
          {{ segment.label }}
        </button>
        <p v-if="segment.reason" class="segment-reason">{{ segment.reason }}</p>
      </div>
    </div>

    <p v-if="!isText && entry.card_status" class="entry-card-status">{{ cardStatusText }}</p>

    <div v-if="entry.error" class="entry-error">
      <p class="error-text">{{ errorText }}</p>
      <button v-if="entry.word" class="btn-inline retry" :disabled="busy" @click="emit('retry')">
        {{ t("add.retry", { word: entry.word }) }}
      </button>
    </div>
    <p v-if="entry.detail_error" class="entry-error">{{ entry.detail_error }}</p>
    <p v-if="entry.control_error" class="entry-error">{{ entry.control_error }}</p>

    <div v-if="showsActions && !confirming" class="entry-actions">
      <button
        class="btn-inline detail"
        :disabled="!entry.detail_available || !!entry.detail_html"
        @click="emit('detail')"
      >
        {{ entry.detail_html ? t("add.detailReady") : t("add.detail") }}
      </button>
      <button
        v-if="showsDelete"
        class="btn-inline btn-danger delete-card"
        @click="confirming = true"
      >
        {{ t("add.deleteCard") }}
      </button>
    </div>

    <div v-if="showsActions && confirming" class="confirm">
      <p class="confirm-text">{{ t("add.deleteCardConfirm", { word: entry.word }) }}</p>
      <div class="confirm-actions">
        <button class="btn-inline btn-danger confirm-yes" @click="confirmDelete">
          {{ t("add.deleteCardYes") }}
        </button>
        <button class="btn-inline confirm-no" @click="confirming = false">
          {{ t("add.deleteCardNo") }}
        </button>
      </div>
    </div>

    <div v-if="!isPending && working" class="working">
      <span class="spinner" aria-hidden="true"></span>
      <span>{{ busyLabel }}</span>
    </div>
  </article>
</template>

<style scoped>
.deck {
  position: relative;
  /* The page still scrolls vertically; only sideways travel is the card's. */
  touch-action: pan-y;
  user-select: none;
  -webkit-user-select: none;
  cursor: grab;
  margin-bottom: 0;
}

.deck.settling {
  transition:
    transform 0.18s ease-out,
    opacity 0.18s ease-out;
}

/* A paid call answers in about ten seconds; the strip has to say so at once. */
.progress {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  border-radius: var(--radius) var(--radius) 0 0;
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  overflow: hidden;
}

.progress-bar {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 38%;
  background: var(--accent);
  animation: sweep 1.2s ease-in-out infinite;
}

@keyframes sweep {
  0% {
    left: -38%;
  }
  100% {
    left: 100%;
  }
}

.entry-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.6rem;
  margin-bottom: 0.6rem;
}

.entry-title.word {
  font-size: 1.15rem;
  font-weight: 600;
}

.entry-title.kind {
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
}

.entry-model {
  flex: 0 0 auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 0.68rem;
  color: var(--text-muted);
}

.working {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.75rem;
  font-size: 0.8rem;
  color: var(--text-muted);
}

.working.pending {
  margin-top: 0;
  padding: 0.35rem 0 0.5rem;
}

.spinner {
  width: 13px;
  height: 13px;
  flex: 0 0 auto;
  border: 2px solid color-mix(in srgb, var(--accent) 14%, transparent);
  border-top-color: var(--accent);
  border-radius: 999px;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* Said before the analysis, which may be about another word than the one typed. */
.entry-notice {
  border-left: 3px solid var(--accent);
  padding: 0.1rem 0 0.1rem 0.6rem;
  margin-bottom: 0.75rem;
}

.notice-text {
  font-size: 0.9rem;
}

.entry-notice .btn-inline {
  margin-top: 0.4rem;
}

/* Unverified wording is marked apart from a spelling notice: one is about how the
   word is written, the other about whether it is a word. */
.entry-notice.unverified {
  border-left-color: var(--warning);
}

.entry-source {
  margin-bottom: 0.5rem;
  padding-left: 0.6rem;
  border-left: 3px solid var(--border);
  white-space: pre-wrap;
}

.entry-audio {
  display: block;
  width: 100%;
  margin-top: 0.75rem;
}

.context-audio-title {
  margin-top: 0.75rem;
  font-size: 0.85rem;
  color: var(--text-muted);
}

.context-audio-player {
  margin-top: 0.35rem;
}

.entry-text {
  line-height: 1.5;
  white-space: pre-wrap;
}

/* The forms table is the one place the answer is not flowing prose, so it opts
   out of pre-wrap and scrolls on its own rather than widening the page. */
.entry-text :deep(table),
.entry-detail :deep(table) {
  white-space: normal;
  border-collapse: collapse;
  display: block;
  overflow-x: auto;
  max-width: 100%;
  margin: 0.5rem 0;
}

.entry-text :deep(td),
.entry-detail :deep(td) {
  border-top: 1px solid var(--border);
  padding: 0.25rem 0.75rem 0.25rem 0;
  vertical-align: top;
}

.entry-text :deep(tr:first-child td),
.entry-detail :deep(tr:first-child td) {
  border-top: 0;
}

.entry-detail {
  border-top: 1px solid var(--border);
  margin-top: 1rem;
  padding-top: 1rem;
  line-height: 1.5;
  white-space: pre-wrap;
}

/* Filled pills that look pressable; no caption above them. The reason stays: two
   sense chips of the same word are told apart by nothing else. */
.segments {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 6px;
  margin-top: 0.85rem;
}

.segment {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.2rem;
  max-width: 100%;
}

.segment-label {
  min-height: 36px;
  max-width: 100%;
  padding: 0.35rem 0.7rem;
  border-radius: 999px;
  border: none;
  background: var(--surface-2);
  color: var(--text);
  font-family: inherit;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition:
    transform 0.1s,
    background 0.12s,
    color 0.12s;
  touch-action: manipulation;
}

.segment-label:hover:not(:disabled) {
  background: var(--accent);
  color: #fff;
}

.segment-label:active {
  transform: scale(0.94);
}

.segment-label:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.segment-reason {
  max-width: 190px;
  padding-left: 0.2rem;
  font-size: 0.75rem;
  color: var(--text-muted);
  line-height: 1.35;
}

.entry-card-status {
  margin-top: 0.75rem;
  font-size: 0.85rem;
}

.entry-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: 0.75rem;
}

.entry-actions .btn-inline:disabled {
  opacity: 0.45;
}

.btn-danger {
  border-color: var(--error);
  color: var(--error);
}

.btn-danger:hover {
  color: var(--error);
  border-color: var(--error);
}

.confirm {
  margin-top: 0.75rem;
}

.confirm-text {
  font-size: 0.85rem;
  line-height: 1.4;
}

.confirm-actions {
  display: flex;
  gap: 0.4rem;
  margin-top: 0.5rem;
}

.entry-error {
  color: var(--error);
}

.entry-error .btn-inline {
  margin-top: 0.4rem;
}
</style>
