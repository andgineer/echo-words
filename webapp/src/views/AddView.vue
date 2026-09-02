<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { apiRequest } from "../api/_request.js";
import { upsertEntry } from "../composables/useEntries.js";
import { useEventStream } from "../composables/useEventStream.js";
import { useLanguage } from "../composables/useLanguage.js";
import { useI18n } from "../i18n/index.js";
import {
  enqueueWord,
  isRetryableWordError,
  withRequestId,
} from "../composables/useResendQueue.js";

const { t, tn } = useI18n();
const { languages, selected, loadLanguages } = useLanguage();
const { entries, start: startEventStream, stop: stopEventStream } = useEventStream();

const word = ref("");
const lookupOnly = ref(false);
const hint = ref("");
const busy = ref(false);
const helpOpen = ref(false);

watch([word, selected, lookupOnly], () => {
  hint.value = "";
});

onMounted(async () => {
  startEventStream();
  try {
    await loadLanguages();
  } catch (e) {
    hint.value = e.message;
  }
});

onUnmounted(stopEventStream);

async function submit() {
  if (busy.value || !word.value.trim() || !selected.value) return;
  await sendWord(word.value.trim(), lookupOnly.value);
}

async function analyseSegment(entry, segment) {
  if (busy.value) return;
  // The unit belongs to the text it was found in, whatever the selector shows now.
  await sendWord(segment.label, lookupOnly.value, segment.context || "", "unit", entry.lang);
}

async function sendWord(
  submittedWord,
  submittedLookupOnly,
  context = "",
  shape = null,
  lang = selected.value,
) {
  busy.value = true;
  hint.value = "";
  const body = withRequestId({
    word: submittedWord,
    lang,
    lookup_only: submittedLookupOnly,
  });
  if (context) body.context = context;
  if (shape) body.shape = shape;
  try {
    const accepted = await apiRequest("/api/words", {
      method: "POST",
      body,
    });
    const metadata = {
      entry_id: accepted.entry_id,
      word: submittedWord,
      lang,
      language: languages.value.find((item) => item.code === lang)?.name || "",
      lookup_only: submittedLookupOnly,
      context,
      // Kept so a failed entry can be sent again as submitted: `shape` is what the
      // answer turned out to be, which a failed entry never has.
      requested_shape: shape,
    };
    const alreadyStreaming = entries.value.some((entry) => entry.entry_id === accepted.entry_id);
    upsertEntry(
      alreadyStreaming ? metadata : { ...metadata, status: "pending" },
      { newest: true },
    );
    word.value = "";
    lookupOnly.value = false;
  } catch (e) {
    if (isRetryableWordError(e)) {
      enqueueWord(body);
      word.value = "";
      lookupOnly.value = false;
      await nextTick();
      hint.value = t("add.queued");
    } else {
      hint.value = e.message;
    }
  } finally {
    busy.value = false;
  }
}

async function retry(entry) {
  if (busy.value) return;
  await sendWord(
    entry.word,
    entry.lookup_only ?? false,
    entry.context || "",
    entry.requested_shape ?? null,
    entry.lang,
  );
}

async function entryAction(entry, action) {
  hint.value = "";
  upsertEntry({ entry_id: entry.entry_id, control_error: null });
  try {
    await apiRequest(`/api/words/${entry.entry_id}/${action}`, { method: "POST" });
  } catch (e) {
    hint.value = e.message;
  }
}

const CARD_STATUS_KEYS = {
  added: "card.added",
  lookup_only: "card.lookupOnly",
  text: "card.text",
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

function spellingNotice(entry) {
  // Whatever the answer did with the spelling is said above the analysis, because
  // the analysis may be of another word and the card was made without asking.
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
}

const spellingNotices = computed(() =>
  Object.fromEntries(entries.value.map((entry) => [entry.entry_id, spellingNotice(entry)])),
);

function correctionLabel(entry) {
  // The offer points back to the reader's own spelling once the entry shows another,
  // and its wording follows the card: there is nothing to replace without one.
  if (entry.showing_other_spelling) return t("add.revert", { word: entry.suggestion });
  return entry.card_status === "added"
    ? t("add.replaceCard", { word: entry.suggestion })
    : t("add.analyseInstead", { word: entry.suggestion });
}

function cardStatusText(entry) {
  if (!entry.card_status) return "";
  const parts = [entry.card_error ? `⚠️ ${entry.card_error}` : cardStatusLabel(entry)];
  if (entry.card_kept) parts.push(t("card.kept"));
  if (entry.no_audio) parts.push(t("card.noAudio"));
  if (entry.no_card_audio) parts.push(t("card.noCardAudio"));
  return parts.join(" · ");
}

function errorText(error) {
  return error === "analysis_failed" ? t("add.analysisFailed") : error;
}

async function undo() {
  if (!selected.value) return;
  try {
    const result = await apiRequest(`/api/languages/${selected.value}/undo`, { method: "POST" });
    hint.value = result.undone ? t("add.undone", { word: result.word }) : t("add.nothingToUndo");
  } catch (e) {
    hint.value = e.message;
  }
}
</script>

<template>
  <section class="card">
    <div class="form-group">
      <label for="lang">{{ t("add.language") }}</label>
      <select id="lang" v-model="selected">
        <option v-for="lang in languages" :key="lang.code" :value="lang.code">
          {{ lang.name }}
        </option>
      </select>
    </div>

    <div class="form-group">
      <label for="word">{{ t("add.word") }}</label>
      <input
        id="word"
        v-model="word"
        type="text"
        autocomplete="off"
        autocapitalize="none"
        spellcheck="false"
        :placeholder="t('add.wordPlaceholder')"
        @keyup.enter="submit"
      />
    </div>

    <label class="lookup">
      <input v-model="lookupOnly" type="checkbox" />
      {{ t("add.lookupOnly") }}
    </label>

    <button class="btn btn-primary" :disabled="busy" @click="submit">{{ t("add.submit") }}</button>

    <button class="btn-inline undo" @click="undo">{{ t("add.undo") }}</button>

    <p v-if="hint" class="hint">{{ hint }}</p>
  </section>

  <section class="answers">
    <p v-if="!entries.length" class="empty">{{ t("add.empty") }}</p>
    <article v-for="entry in entries" :key="entry.entry_id" class="card entry">
      <p v-if="entry.status === 'pending' && !entry.text" class="entry-head">
        ⏳ <b>{{ entry.word }}</b> …
      </p>
      <div v-if="spellingNotices[entry.entry_id]" class="entry-notice">
        <p class="notice-text">{{ spellingNotices[entry.entry_id] }}</p>
        <button
          v-if="entry.suggestion"
          class="btn-inline correction"
          @click="entryAction(entry, 'switch')"
        >
          {{ correctionLabel(entry) }}
        </button>
      </div>
      <p v-if="entry.shape === 'text' && entry.text" class="entry-source">{{ entry.word }}</p>
      <div v-if="entry.text" class="entry-text" v-html="entry.text"></div>
      <div
        v-if="entry.detail_html"
        class="entry-detail"
        v-html="entry.detail_html"
      ></div>
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
        <p class="segments-title">
          {{ t(`add.${entry.segment_kind}`) }}
        </p>
        <div
          v-for="(segment, index) in entry.segments"
          :key="`${index}|${segment.label}`"
          class="segment"
        >
          <button
            class="btn-inline segment-label"
            :disabled="busy"
            @click="analyseSegment(entry, segment)"
          >
            {{ segment.label }}
          </button>
          <p v-if="segment.reason" class="segment-reason">{{ segment.reason }}</p>
        </div>
      </div>
      <p v-if="entry.card_status" class="entry-card-status">{{ cardStatusText(entry) }}</p>
      <div v-if="entry.error" class="entry-error">
        <p class="error-text">{{ errorText(entry.error) }}</p>
        <button v-if="entry.word" class="btn-inline retry" :disabled="busy" @click="retry(entry)">
          {{ t("add.retry", { word: entry.word }) }}
        </button>
      </div>
      <p v-if="entry.detail_error" class="entry-error">{{ entry.detail_error }}</p>
      <p v-if="entry.control_error" class="entry-error">{{ entry.control_error }}</p>
      <div v-if="entry.status === 'done'" class="entry-actions">
        <button
          v-if="entry.shape === 'unit' && (entry.card_status === 'added' || entry.card_kept)"
          class="btn-inline rebuild"
          @click="entryAction(entry, 'rebuild')"
        >
          {{ t("add.rebuild") }}
        </button>
        <button
          v-if="entry.shape === 'unit'"
          class="btn-inline detail"
          :disabled="!entry.detail_available || !!entry.detail_html"
          @click="entryAction(entry, 'detail')"
        >
          {{ entry.detail_html ? t("add.detailReady") : t("add.detail") }}
        </button>
      </div>
      <p class="entry-meta">
        {{ entry.language }}<span v-if="entry.model"> · {{ entry.model }}</span><span v-if="entry.shape === 'text'"> · {{ t("add.textNoCard") }}</span><span v-else-if="entry.lookup_only"> · {{ t("add.noCard") }}</span>
      </p>
    </article>
  </section>

  <section class="about">
    <button class="btn-inline about-toggle" @click="helpOpen = !helpOpen">
      {{ helpOpen ? t("add.aboutHide") : t("add.aboutShow") }}
    </button>
    <div v-if="helpOpen" class="about-text">
      <p v-html="t('add.aboutIntro')"></p>
      <p v-html="t('add.aboutText')"></p>
      <p v-html="t('add.aboutLookup')"></p>
      <p v-html="t('add.aboutCorrection')"></p>
    </div>
  </section>
</template>

<style scoped>
.lookup {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  text-transform: none;
  letter-spacing: normal;
  font-size: 0.85rem;
  color: var(--text);
  margin-bottom: 1rem;
}

.hint {
  margin-top: 0.75rem;
  font-size: 0.85rem;
  color: var(--warning);
}

.segments {
  margin-top: 0.75rem;
}

.segments-title {
  font-size: 0.85rem;
  color: var(--text-muted);
}

.segment {
  margin-top: 0.4rem;
}

.segment-reason {
  font-size: 0.8rem;
  color: var(--text-muted);
  line-height: 1.4;
}

.undo {
  margin-top: 0.75rem;
}

.answers {
  margin-top: 1rem;
}

.empty {
  color: var(--text-muted);
  font-size: 0.85rem;
  text-align: center;
  padding: 1.5rem 0;
}

.entry-head {
  font-size: 1rem;
}

.entry-card-status {
  margin-top: 0.5rem;
  font-size: 0.85rem;
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

.entry-meta {
  margin-top: 0.35rem;
  font-size: 0.75rem;
  color: var(--text-muted);
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

.entry-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: 0.75rem;
}

.entry-actions .btn-inline:disabled {
  opacity: 0.45;
}

.entry-error {
  color: var(--error);
}

.entry-error .btn-inline {
  margin-top: 0.4rem;
}

.about {
  margin-top: 1rem;
  text-align: center;
}

.about-text {
  margin-top: 0.75rem;
  text-align: left;
  font-size: 0.85rem;
  color: var(--text-muted);
  line-height: 1.5;
}

.about-text p + p {
  margin-top: 0.6rem;
}
</style>
