<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useI18n } from "../i18n/index.js";

const { t } = useI18n();

const props = defineProps({
  entry: { type: Object, required: true },
  busy: { type: Boolean, default: false },
  // Which side the card comes in from: +1 for a later entry, -1 for an earlier one.
  direction: { type: Number, default: 1 },
});
const emit = defineEmits([
  "switch",
  "detail",
  "delete-card",
  "retry",
  "segment",
  "swipe",
  "paid-answer",
  "remove-entry",
  "played",
]);

const SWIPE_THRESHOLD = 55;
const ARRIVAL_OFFSET = 44;
const FADE_TRAVEL = 420;

const dragX = ref(0);
const dragging = ref(false);
const confirming = ref(false);
let startX = 0;
let held = false;

const isText = computed(() => props.entry.shape === "text");
const isPending = computed(() => props.entry.status === "pending");
const working = computed(() => isPending.value || !!props.entry.detail_pending);
const busyLabel = computed(() =>
  isPending.value
    ? t("add.analysing", { word: props.entry.word })
    : t("add.buildingEntry"),
);

// The deeper analysis is offered on any finished word answer; a running text has no
// single word to go deeper on.
const showsDetail = computed(() => props.entry.status === "done" && props.entry.shape === "unit");
// Nothing in the row can be acted on while the first answer is still coming: there is
// no recording, no card and nothing to go deeper into.
const showsRow = computed(() => !isPending.value);

const detailReady = computed(() => !!props.entry.detail_html);
const detailDisabled = computed(
  () =>
    !detailReady.value &&
    (!props.entry.detail_available || !!props.entry.detail_pending || props.busy),
);
const detailTitle = computed(() =>
  detailReady.value ? t("add.detailGoto") : t("add.detail"),
);

const detailSection = ref(null);

// Once the deeper article exists the button stops buying a second one and becomes the
// way down to it: it sits at the top of a card the article has made long.
function hitDetail() {
  if (detailReady.value) {
    detailSection.value?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    return;
  }
  emit("detail");
}

// Which of the three shapes the Anki control takes. A text entry never had a card to
// speak of, so it gets no control rather than a permanently empty one.
const ankiSlot = computed(() => {
  const entry = props.entry;
  if (isText.value || !entry.card_status) return "";
  if (entry.card_status === "added" || entry.card_kept) return "delete";
  if (entry.card_status === "failed") return "failed";
  return "absent";
});

const ankiTitle = computed(() => {
  const entry = props.entry;
  const parts = [];
  if (ankiSlot.value === "delete") parts.push(t("add.deleteCard"));
  else if (ankiSlot.value === "failed") parts.push(t("add.cardNotMade"));
  else parts.push(t("add.noCard"));
  if (entry.card_kept) parts.push(t("card.kept"));
  if (entry.no_audio) parts.push(t("card.noAudio"));
  if (entry.no_card_audio) parts.push(t("card.noCardAudio"));
  return parts.join(" · ");
});

const wordAudio = ref(null);
const contextAudio = ref(null);
// Which recording is sounding, so the two share one pair of controls and one progress
// line: starting either one stops the other.
const sounding = ref("");
const progress = ref(0);

function player(which) {
  return which === "word" ? wordAudio.value : contextAudio.value;
}

function toggleAudio(which) {
  const element = player(which);
  if (!element) return;
  if (sounding.value === which) {
    element.pause();
    return;
  }
  player(which === "word" ? "text" : "word")?.pause();
  element.currentTime = 0;
  void element.play?.()?.catch?.(() => {});
}

function started(which) {
  sounding.value = which;
}

function stopped(which) {
  if (sounding.value !== which) return;
  sounding.value = "";
  progress.value = 0;
}

function tick(which, event) {
  if (sounding.value !== which) return;
  const element = event.target;
  progress.value = element.duration ? (element.currentTime / element.duration) * 100 : 0;
}

// A recording plays by itself exactly once: when the card it belongs to was just
// made, in front of the reader. Reopening that card, switching back to it, or
// reloading the page finds it silent, and the button is there to press.
//
// The one chance is spent by clearing the entry's own flag rather than by remembering
// what has played: a set of played recordings dies with the page, and the flag does
// not, so every reload found the same cards still "just made" and spoke again. Spent
// on the spot, whether or not the browser let the sound out — a card the reader
// swiped away from before it could speak has still had its moment.
watch(
  () => [props.entry.entry_id, props.entry.audio_url, props.entry.just_finished],
  ([id, url, fresh]) => {
    if (!(id && url && fresh)) return;
    emit("played");
    void wordAudio.value?.play?.()?.catch?.(() => {});
  },
  { immediate: true, flush: "post" },
);

watch(
  () => props.entry.entry_id,
  () => {
    confirming.value = false;
    sounding.value = "";
    progress.value = 0;
    arrive();
  },
);

// The card is mounted afresh whenever the language it belongs to had nothing to show
// a moment ago, and that switch is a switch like any other.
onMounted(arrive);

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
  // Two frames so the offset is painted before it is released. The timer is the
  // fallback: a hidden tab throttles rAF, and a card left 44px off-centre until
  // the tab comes back would be worse than skipping the animation.
  if (typeof requestAnimationFrame === "function") {
    requestAnimationFrame(() => requestAnimationFrame(settle));
  }
  setTimeout(settle, 60);
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
  const shift = release();
  if (shift <= -SWIPE_THRESHOLD) emit("swipe", 1);
  else if (shift >= SWIPE_THRESHOLD) emit("swipe", -1);
}

// `touch-action: pan-y` hands a mostly-vertical drag to the page, and the browser
// says so by cancelling the gesture. Committing its sideways part would switch the
// card under a reader who was only scrolling.
function onPointerCancel() {
  if (held) release();
}

function release() {
  held = false;
  const shift = dragX.value;
  dragging.value = false;
  dragX.value = 0;
  return shift;
}

const deckStyle = computed(() => ({
  transform: `translateX(${dragX.value}px)`,
  opacity: String(1 - Math.min(Math.abs(dragX.value) / FADE_TRAVEL, 0.4)),
}));

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

const detailErrorText = computed(() =>
  props.entry.detail_error === "detail_failed"
    ? t("add.detailFailed")
    : props.entry.detail_error,
);

// Every sense of one word is chipped under that same word, so the label repeats down
// the row and the meaning underneath is the only thing telling them apart. On a rail
// of senses the meaning is the chip; the parts of a phrase keep their own wording.
const chipsAreSenses = computed(() => props.entry.segment_kind === "senses");
const visibleSegments = computed(() => {
  const entry = props.entry;
  const segments = entry.segments ?? [];
  if (!chipsAreSenses.value || entry.card_status !== "added") return segments;
  return segments.filter((_, index) => index !== entry.carded_sense);
});

function chipLabel(segment) {
  return chipsAreSenses.value && segment.reason ? segment.reason : segment.label;
}

function chipReason(segment) {
  return chipsAreSenses.value && segment.reason ? "" : segment.reason;
}

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
    @pointercancel="onPointerCancel"
    @pointerleave="onPointerUp"
  >
    <div v-if="working" class="progress"><div class="progress-bar"></div></div>

    <div class="entry-head">
      <span class="entry-title" :class="isText ? 'kind' : 'word'">
        {{ isText ? t("add.sentence") : entry.word }}
      </span>
      <span v-if="entry.model" class="entry-model">{{ entry.model }}</span>
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

    <div v-if="showsRow" class="entry-actions">
      <div v-if="entry.audio_url || entry.context_audio_url || showsDetail" class="act-group">
        <button
          v-if="entry.audio_url"
          class="act act-square speak-word"
          :title="sounding === 'word' ? t('add.pauseAudio') : t('add.speakWord')"
          :aria-label="t('add.speakWord')"
          @click="toggleAudio('word')"
        >
          <svg v-if="sounding === 'word'" class="glyph" viewBox="0 0 24 24" aria-hidden="true">
            <rect x="7" y="5" width="3.6" height="14" rx="1.2" fill="currentColor" />
            <rect x="13.4" y="5" width="3.6" height="14" rx="1.2" fill="currentColor" />
          </svg>
          <svg v-else class="glyph" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M11 5 6.5 9H3v6h3.5L11 19V5Z" />
            <path d="M15 9.5a4 4 0 0 1 0 5" />
            <path d="M17.8 6.8a8 8 0 0 1 0 10.4" />
          </svg>
        </button>

        <button
          v-if="entry.context_audio_url"
          class="act act-wide speak-text"
          :title="sounding === 'text' ? t('add.pauseAudio') : t('add.speakText')"
          :aria-label="t('add.speakText')"
          @click="toggleAudio('text')"
        >
          <svg v-if="sounding === 'text'" class="glyph" viewBox="0 0 24 24" aria-hidden="true">
            <rect x="7" y="5" width="3.6" height="14" rx="1.2" fill="currentColor" />
            <rect x="13.4" y="5" width="3.6" height="14" rx="1.2" fill="currentColor" />
          </svg>
          <svg v-else class="glyph glyph-wide" viewBox="0 0 33 24" aria-hidden="true">
            <path d="M10 5.5 6.5 8.8H3.8v6.4h2.7L10 18.5V5.5Z" />
            <path d="M15.5 8.8h15.5M15.5 12.5h15.5M15.5 16.2h9.5" stroke-width="2.1" />
          </svg>
        </button>

        <button
          v-if="showsDetail"
          class="act detail"
          :disabled="detailDisabled"
          :title="detailTitle"
          @click="hitDetail"
        >
          <span v-if="entry.detail_pending" class="spinner" aria-hidden="true"></span>
          <svg v-else-if="detailReady" class="glyph glyph-goto" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M6 3.5h7l5 5v12a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1v-16a1 1 0 0 1 1-1Z" />
            <path d="M13 3.5v5h5" />
            <path d="M8.5 13h7" />
            <path d="M8.5 16.5h4.5" />
          </svg>
          <svg v-else class="glyph glyph-fetch" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 4v10" />
            <path d="m7.5 9.5 4.5 4.5 4.5-4.5" />
            <path d="M5.5 19.5h13" />
          </svg>
          {{ t("add.detail") }}
        </button>

        <span v-if="sounding" class="act-progress" :style="{ width: `${progress}%` }"></span>
      </div>

      <div class="act-side">
        <button
          v-if="ankiSlot === 'delete'"
          class="act act-anki delete-card"
          :title="ankiTitle"
          @click="confirming = true"
        >
          <svg class="glyph" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M4 6.5h16" />
            <path d="M9.5 6.5V4.6h5v1.9" />
            <path d="M6.6 6.5 7.6 20a1.2 1.2 0 0 0 1.2 1.1h6.4A1.2 1.2 0 0 0 16.4 20l1-13.5" />
            <path d="M10.2 10.4v6.8M13.8 10.4v6.8" />
          </svg>
          Anki
        </button>
        <button
          v-else-if="ankiSlot"
          class="act act-anki act-anki-none"
          :class="{ failed: ankiSlot === 'failed' }"
          :title="ankiTitle"
          disabled
        >
          <svg v-if="ankiSlot === 'failed'" class="glyph" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 4.6 21.4 20H2.6L12 4.6Z" />
            <path d="M12 10.6v3.8" />
            <path d="M12 17.2v.2" />
          </svg>
          <svg v-else class="glyph" viewBox="0 0 24 24" aria-hidden="true">
            <rect x="3.2" y="6" width="17.6" height="12" rx="2.4" />
            <path d="M5 19 19 5" />
          </svg>
          Anki
        </button>
        <button
          class="act act-square act-close remove-entry"
          :title="t('add.removeFromFeed')"
          :aria-label="t('add.removeFromFeed')"
          @click="emit('remove-entry')"
        >
          <svg class="glyph" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M6.5 6.5 17.5 17.5M17.5 6.5 6.5 17.5" />
          </svg>
        </button>
      </div>
    </div>

    <div v-if="confirming" class="confirm">
      <p class="confirm-text">{{ t("add.deleteCardConfirm", { word: entry.word }) }}</p>
      <div class="confirm-actions">
        <button class="confirm-yes" @click="confirmDelete">
          {{ t("add.deleteCardYes") }}
        </button>
        <button class="btn-inline confirm-no" @click="confirming = false">
          {{ t("add.deleteCardNo") }}
        </button>
      </div>
    </div>

    <div v-if="isPending" class="working pending">
      <span class="spinner" aria-hidden="true"></span>
      <span>{{ busyLabel }}</span>
    </div>

    <p v-if="isText && entry.text" class="entry-source">{{ entry.word }}</p>

    <div v-if="entry.text" class="entry-text" v-html="entry.text"></div>

    <section v-if="entry.detail_html" ref="detailSection" class="entry-detail-block">
      <div class="detail-head">
        <span class="detail-title">{{ t("add.detailSection") }}</span>
        <span v-if="entry.detail_model" class="entry-model">{{ entry.detail_model }}</span>
      </div>
      <div class="entry-detail" v-html="entry.detail_html"></div>
    </section>

    <audio
      v-if="entry.audio_url"
      ref="wordAudio"
      class="entry-audio"
      :src="entry.audio_url"
      preload="none"
      @play="started('word')"
      @pause="stopped('word')"
      @ended="stopped('word')"
      @timeupdate="tick('word', $event)"
    ></audio>
    <audio
      v-if="entry.context_audio_url"
      ref="contextAudio"
      class="entry-audio"
      :src="entry.context_audio_url"
      preload="none"
      @play="started('text')"
      @pause="stopped('text')"
      @ended="stopped('text')"
      @timeupdate="tick('text', $event)"
    ></audio>

    <div v-if="visibleSegments.length" class="segments">
      <div
        v-for="(segment, index) in visibleSegments"
        :key="`${index}|${segment.label}`"
        class="segment"
      >
        <button class="segment-label" :disabled="busy" @click="emit('segment', segment)">
          {{ chipLabel(segment) }}
        </button>
        <p v-if="chipReason(segment)" class="segment-reason">{{ chipReason(segment) }}</p>
      </div>
    </div>

    <button
      v-if="entry.paid_answer_available"
      class="btn-inline paid-answer"
      :disabled="busy"
      @click="emit('paid-answer')"
    >
      {{ t("add.paidAnswer") }}
    </button>

    <div v-if="entry.error" class="entry-error">
      <p class="error-text">{{ errorText }}</p>
      <button v-if="entry.word" class="btn-inline retry" :disabled="busy" @click="emit('retry')">
        {{ t("add.retry", { word: entry.word }) }}
      </button>
    </div>
    <p v-if="entry.card_error" class="entry-error card-error">{{ entry.card_error }}</p>
    <p v-if="entry.detail_error" class="entry-error">{{ detailErrorText }}</p>
    <p v-if="entry.control_error" class="entry-error">{{ entry.control_error }}</p>

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
  margin-bottom: 0.75rem;
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
  margin-top: 0.75rem;
  margin-bottom: 0.5rem;
  padding-left: 0.6rem;
  border-left: 3px solid var(--border);
  white-space: pre-wrap;
}

/* Every control the card offers, in one row under the word. The two groups say what
   they do to: the left acts on the answer, the right gets rid of it. */
.entry-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.act-group {
  position: relative;
  display: flex;
  align-items: center;
  overflow: hidden;
  border: 1px solid var(--border-strong);
  border-radius: 9px;
  background: var(--field);
}

.act-side {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 4px;
}

.act {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-height: 36px;
  padding: 0 9px;
  border: none;
  background: none;
  color: var(--text);
  font-family: inherit;
  font-size: 0.8rem;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
  transition:
    background 0.12s,
    color 0.12s,
    border-color 0.12s;
  touch-action: manipulation;
}

.act-group .act + .act {
  border-left: 1px solid var(--border-strong);
}

.act:hover:not(:disabled) {
  background: color-mix(in srgb, var(--text) 8%, transparent);
}

.act:active:not(:disabled) {
  transform: scale(0.96);
}

.act:disabled {
  color: var(--text-muted);
  cursor: not-allowed;
}

.act-square {
  width: 38px;
  padding: 0;
}

/* Wider than the plain speaker so the lines of text beside it read as lines of text
   rather than as more of the same sound waves. */
.act-wide {
  width: 54px;
  padding: 0;
}

.glyph {
  width: 16px;
  height: 16px;
  flex: 0 0 auto;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.glyph-wide {
  width: 23px;
  stroke-width: 1.8;
}

.act-progress {
  position: absolute;
  left: 0;
  bottom: 0;
  height: 2px;
  background: var(--accent);
}

.act-anki {
  border: 1px solid var(--border-strong);
  border-radius: 9px;
  color: var(--text-muted);
}

.act-anki:hover:not(:disabled) {
  background: none;
  color: var(--error);
  border-color: var(--error);
}

/* No card to delete, so nothing to press: a dashed outline and the crossed card say
   which of the two removals is unavailable and why. */
.act-anki-none {
  border-style: dashed;
}

.act-anki-none.failed {
  color: var(--warning);
  border-color: color-mix(in srgb, var(--warning) 55%, transparent);
}

.act-close {
  border: 1px solid var(--border-strong);
  border-radius: 9px;
  width: 34px;
  color: var(--text-muted);
}

.act-close:hover {
  color: var(--text);
  border-color: color-mix(in srgb, var(--text) 30%, transparent);
}

/* Driven by the row's own buttons; the element is only there to make the sound and
   to speak once by itself on a card just made. */
.entry-audio {
  display: none;
}

.entry-text {
  margin-top: 0.9rem;
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

/* A second answer by a second model is a section of its own, titled and signed on one
   line, and not a paragraph that happens to follow the first. */
.entry-detail-block {
  margin-top: 1.5rem;
  border-top: 1px solid var(--border-strong);
  padding-top: 0.95rem;
}

.detail-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.6rem;
  margin-bottom: 0.6rem;
}

.detail-title {
  font-size: 0.75rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
}

.entry-detail {
  line-height: 1.5;
  white-space: pre-wrap;
}

/* Filled pills that look pressable; no caption above them. The reason stays: two
   sense chips of the same word are told apart by nothing else. */
.segments {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 6px;
  margin-top: 1.25rem;
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

/* The question belongs under the button that asked it, not at the end of the card. */
.confirm {
  margin-top: 0.6rem;
  border: 1px solid color-mix(in srgb, var(--error) 45%, transparent);
  background: color-mix(in srgb, var(--error) 8%, transparent);
  border-radius: 9px;
  padding: 0.7rem 0.75rem;
}

.confirm-text {
  font-size: 0.85rem;
  line-height: 1.4;
}

.confirm-actions {
  display: flex;
  gap: 0.4rem;
  margin-top: 0.6rem;
}

.confirm-yes {
  min-height: 34px;
  padding: 0 0.9rem;
  border: none;
  border-radius: 8px;
  background: var(--error);
  color: #fff;
  font-family: inherit;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  touch-action: manipulation;
}

.confirm-no {
  min-height: 34px;
  padding: 0 0.9rem;
  font-size: 0.8rem;
}

.paid-answer {
  margin-top: 0.75rem;
}

.entry-error {
  margin-top: 0.75rem;
  color: var(--error);
}

.entry-error .btn-inline {
  margin-top: 0.4rem;
}
</style>
