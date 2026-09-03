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
import EntryCard from "../components/EntryCard.vue";
import LanguagePicker from "../components/LanguagePicker.vue";
import WordRail from "../components/WordRail.vue";

const { t } = useI18n();
const { languages, selected, loadLanguages } = useLanguage();
const { entries, start: startEventStream, stop: stopEventStream } = useEventStream();

const emit = defineEmits(["navigate"]);

const word = ref("");
const hint = ref("");
const busy = ref(false);
const helpOpen = ref(false);
// Which entry each language is showing, so switching back to a language returns to
// the word it was left on rather than to its newest.
const selectedIds = ref({});
const direction = ref(1);

const railEntries = computed(() =>
  entries.value.filter((entry) => entry.lang === selected.value),
);

const selectedId = computed(() => {
  const wanted = selectedIds.value[selected.value];
  if (railEntries.value.some((entry) => entry.entry_id === wanted)) return wanted;
  return railEntries.value[0]?.entry_id || "";
});

const selectedEntry = computed(
  () => railEntries.value.find((entry) => entry.entry_id === selectedId.value) || null,
);

watch([word, selected], () => {
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

function pickLanguage(code) {
  if (code === selected.value) return;
  // The other language's card has no position relative to this one's, so it simply
  // comes in from the right.
  direction.value = 1;
  selected.value = code;
}

function selectEntry(entryId) {
  if (entryId === selectedId.value) return;
  const from = railEntries.value.findIndex((entry) => entry.entry_id === selectedId.value);
  const to = railEntries.value.findIndex((entry) => entry.entry_id === entryId);
  direction.value = to >= from ? 1 : -1;
  selectedIds.value = { ...selectedIds.value, [selected.value]: entryId };
}

function swipe(step) {
  const at = railEntries.value.findIndex((entry) => entry.entry_id === selectedId.value);
  const next = railEntries.value[at + step];
  if (next) selectEntry(next.entry_id);
}

function selectNewest(lang, entryId) {
  direction.value = 1;
  selectedIds.value = { ...selectedIds.value, [lang]: entryId };
}

async function submit() {
  if (busy.value || !word.value.trim() || !selected.value) return;
  await sendWord(word.value.trim());
}

async function analyseSegment(entry, segment) {
  if (busy.value) return;
  // The unit belongs to the text it was found in, whatever the selector shows now.
  await sendWord(segment.label, segment.context || "", "unit", entry.lang);
}

async function sendWord(submittedWord, context = "", shape = null, lang = selected.value) {
  busy.value = true;
  hint.value = "";
  const body = withRequestId({
    word: submittedWord,
    lang,
    lookup_only: false,
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
      lookup_only: false,
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
    selectNewest(lang, accepted.entry_id);
    word.value = "";
  } catch (e) {
    if (isRetryableWordError(e)) {
      enqueueWord(body);
      word.value = "";
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
  await sendWord(entry.word, entry.context || "", entry.requested_shape ?? null, entry.lang);
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

// The paid call takes about ten seconds, so the card and the word's chip say it is
// running from the moment it is asked for rather than when the answer lands.
async function requestDetail(entry) {
  hint.value = "";
  upsertEntry({ entry_id: entry.entry_id, control_error: null, detail_pending: true });
  try {
    const result = await apiRequest(`/api/words/${entry.entry_id}/detail`, { method: "POST" });
    if (result?.cached) {
      upsertEntry({
        entry_id: entry.entry_id,
        detail_html: result.detail_html,
        detail_pending: false,
      });
    }
  } catch (e) {
    upsertEntry({ entry_id: entry.entry_id, detail_pending: false });
    hint.value = e.message;
  }
}
</script>

<template>
  <LanguagePicker
    :languages="languages"
    :selected="selected"
    @update:selected="pickLanguage"
    @edit="emit('navigate', 'languages')"
  />

  <section class="card">
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

    <button class="btn btn-primary submit" :disabled="busy" @click="submit">
      {{ t("add.submit") }}
    </button>

    <p v-if="hint" class="hint">{{ hint }}</p>
  </section>

  <section class="switcher">
    <WordRail :entries="railEntries" :selected-id="selectedId" @select="selectEntry" />
    <EntryCard
      v-if="selectedEntry"
      :entry="selectedEntry"
      :busy="busy"
      :direction="direction"
      @switch="entryAction(selectedEntry, 'switch')"
      @detail="requestDetail(selectedEntry)"
      @delete-card="entryAction(selectedEntry, 'delete-card')"
      @retry="retry(selectedEntry)"
      @segment="analyseSegment(selectedEntry, $event)"
      @swipe="swipe"
    />
    <p v-else class="empty">{{ t("add.empty") }}</p>
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
#word {
  margin-bottom: 1rem;
}

.hint {
  margin-top: 0.75rem;
  font-size: 0.85rem;
  color: var(--warning);
}

.switcher {
  margin-top: 1rem;
  margin-bottom: 1rem;
}

.empty {
  color: var(--text-muted);
  font-size: 0.85rem;
  text-align: center;
  padding: 1.5rem 0;
}

.about {
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
