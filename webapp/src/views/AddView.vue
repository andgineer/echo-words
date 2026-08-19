<script setup>
import { onMounted, onUnmounted, ref, watch } from "vue";
import { apiRequest } from "../api/_request.js";
import { upsertEntry } from "../composables/useEntries.js";
import { useEventStream } from "../composables/useEventStream.js";
import { useLanguage } from "../composables/useLanguage.js";

const { languages, selected, loadLanguages } = useLanguage();
const { entries, start: startEventStream, stop: stopEventStream } = useEventStream();

const word = ref("");
const lookupOnly = ref(false);
const hint = ref("");
const busy = ref(false);
const helpOpen = ref(false);
const picker = ref(null);

watch([word, selected, lookupOnly], () => {
  hint.value = "";
  picker.value = null;
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

function splitPhrase(value) {
  const lookup = lookupOnly.value || value.startsWith("?");
  const phrase = value.replace(/^\?\s*/, "").trim();
  const tokens = phrase
    .split(/\s+/)
    .map((token) => token.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, ""))
    .filter(Boolean);
  return { phrase, tokens, lookup };
}

async function submit() {
  if (busy.value || !word.value.trim() || !selected.value) return;
  const submittedWord = word.value.trim();
  const choice = splitPhrase(submittedWord);
  if (choice.tokens.length > 1) {
    picker.value = choice;
    hint.value = "";
    return;
  }
  await sendWord(choice.phrase, choice.lookup);
}

async function chooseWord(token) {
  if (busy.value) return;
  const choice = picker.value;
  if (!choice) return;
  await sendWord(token, choice.lookup, choice.phrase);
}

async function sendWord(submittedWord, submittedLookupOnly, context = "") {
  busy.value = true;
  hint.value = "";
  try {
    const body = {
      word: submittedWord,
      lang: selected.value,
      lookup_only: submittedLookupOnly,
    };
    if (context) body.context = context;
    const accepted = await apiRequest("/api/words", {
      method: "POST",
      body,
    });
    const metadata = {
      entry_id: accepted.entry_id,
      word: submittedWord,
      lang: selected.value,
      language: languages.value.find((item) => item.code === selected.value)?.name || "",
      lookup_only: submittedLookupOnly,
      context,
    };
    const alreadyStreaming = entries.value.some((entry) => entry.entry_id === accepted.entry_id);
    upsertEntry(
      alreadyStreaming ? metadata : { ...metadata, status: "pending" },
      { newest: true },
    );
    word.value = "";
    lookupOnly.value = false;
    picker.value = null;
  } catch (e) {
    hint.value = e.message;
  } finally {
    busy.value = false;
  }
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

async function undo() {
  if (!selected.value) return;
  try {
    const result = await apiRequest(`/api/languages/${selected.value}/undo`, { method: "POST" });
    hint.value = result.undone ? `Удалено: ${result.word}` : "Нечего отменять";
  } catch (e) {
    hint.value = e.message;
  }
}
</script>

<template>
  <section class="card">
    <div class="form-group">
      <label for="lang">Язык</label>
      <select id="lang" v-model="selected">
        <option v-for="lang in languages" :key="lang.code" :value="lang.code">
          {{ lang.name }}
        </option>
      </select>
    </div>

    <div class="form-group">
      <label for="word">Слово или выражение</label>
      <input
        id="word"
        v-model="word"
        type="text"
        autocomplete="off"
        autocapitalize="none"
        spellcheck="false"
        placeholder="слово"
        @keyup.enter="submit"
      />
    </div>

    <label class="lookup">
      <input v-model="lookupOnly" type="checkbox" />
      Только посмотреть — без карточки в Anki
    </label>

    <button class="btn btn-primary" :disabled="busy" @click="submit">Разобрать</button>

    <div v-if="picker" class="picker">
      <p>Какое слово разобрать?</p>
      <button
        v-for="(token, index) in picker.tokens"
        :key="`${token}-${index}`"
        class="btn-inline picker-choice"
        :disabled="busy"
        @click="chooseWord(token)"
      >
        {{ token }}
      </button>
    </div>

    <button class="btn-inline undo" @click="undo">Отменить последнее</button>

    <p v-if="hint" class="hint">{{ hint }}</p>
  </section>

  <section class="answers">
    <p v-if="!entries.length" class="empty">Здесь появятся разборы слов.</p>
    <article v-for="entry in entries" :key="entry.entry_id" class="card entry">
      <p v-if="entry.status === 'pending' && !entry.text" class="entry-head">
        ⏳ <b>{{ entry.word }}</b> …
      </p>
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
      <p v-if="entry.card_status" class="entry-card-status">{{ entry.card_status }}</p>
      <p v-if="entry.error" class="entry-error">{{ entry.error }}</p>
      <p v-if="entry.detail_error" class="entry-error">{{ entry.detail_error }}</p>
      <p v-if="entry.control_error" class="entry-error">{{ entry.control_error }}</p>
      <div v-if="entry.status === 'done'" class="entry-actions">
        <button
          v-if="entry.suggestion"
          class="btn-inline correction"
          @click="entryAction(entry, 'switch')"
        >
          {{ entry.correction_reversed ? "↩︎ Вернуть" : "✏️ Исправить на" }}
          «{{ entry.suggestion }}»
        </button>
        <button class="btn-inline rebuild" @click="entryAction(entry, 'rebuild')">
          Пересобрать карточку
        </button>
        <button
          class="btn-inline detail"
          :disabled="!entry.detail_available || !!entry.detail_html"
          @click="entryAction(entry, 'detail')"
        >
          {{ entry.detail_html ? "Подробный разбор готов" : "Подробнее" }}
        </button>
      </div>
      <p class="entry-meta">
        {{ entry.language }}<span v-if="entry.model"> · {{ entry.model }}</span><span v-if="entry.lookup_only"> · без карточки</span>
      </p>
    </article>
  </section>

  <section class="about">
    <button class="btn-inline about-toggle" @click="helpOpen = !helpOpen">
      {{ helpOpen ? "Свернуть" : "Что это и как пользоваться" }}
    </button>
    <div v-if="helpOpen" class="about-text">
      <p>
        echo-words разбирает слово или выражение на выбранном языке: перевод,
        значения, употребление, происхождение и примеры — и сам добавляет
        компактную карточку в Anki, чтобы слово попало в повторения.
      </p>
      <p>
        <b>Только посмотреть.</b> Галочка рядом с полем ввода даёт разбор и
        произношение, но карточку не создаёт. То же самое делает <b>?</b> перед
        словом: «? слово».
      </p>
      <p>
        <b>✏️ Исправить.</b> Слово всегда разбирается ровно так, как введено, и
        именно так попадает в карточку. Если оно похоже на опечатку, под разбором
        появится кнопка ✏️ с исправленным написанием — разбор повторится для
        него, и вернуться обратно можно одним нажатием.
      </p>
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

.picker {
  margin-top: 0.75rem;
  color: var(--text-muted);
}

.picker-choice {
  margin: 0.4rem 0.4rem 0 0;
  font-size: 0.85rem;
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

.entry-audio {
  display: block;
  width: 100%;
  margin-top: 0.75rem;
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
