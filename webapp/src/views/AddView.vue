<script setup>
import { onMounted, ref, watch } from "vue";
import { apiRequest } from "../api/_request.js";
import { useLanguage } from "../composables/useLanguage.js";

const { languages, selected, loadLanguages } = useLanguage();

const word = ref("");
const lookupOnly = ref(false);
const hint = ref("");
const busy = ref(false);
const entries = ref([]);
const helpOpen = ref(false);

watch([word, selected], () => {
  hint.value = "";
});

onMounted(async () => {
  try {
    await loadLanguages();
  } catch (e) {
    hint.value = e.message;
  }
});

async function submit() {
  if (busy.value || !word.value.trim() || !selected.value) return;
  busy.value = true;
  hint.value = "";
  try {
    const accepted = await apiRequest("/api/words", {
      method: "POST",
      body: { word: word.value, lang: selected.value, lookup_only: lookupOnly.value },
    });
    entries.value.unshift(accepted);
    word.value = "";
    lookupOnly.value = false;
  } catch (e) {
    hint.value = e.message;
  } finally {
    busy.value = false;
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

    <p v-if="hint" class="hint">{{ hint }}</p>
  </section>

  <section class="answers">
    <p v-if="!entries.length" class="empty">Здесь появятся разборы слов.</p>
    <article v-for="entry in entries" :key="entry.entry_id" class="card entry">
      <p class="entry-head">
        ⏳ <b>{{ entry.word }}</b> …
      </p>
      <p class="entry-meta">
        {{ entry.language }}<span v-if="entry.lookup_only"> · без карточки</span>
      </p>
    </article>
  </section>

  <section class="about">
    <button class="btn-inline" @click="helpOpen = !helpOpen">
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

.entry-meta {
  margin-top: 0.35rem;
  font-size: 0.75rem;
  color: var(--text-muted);
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
