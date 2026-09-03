<script setup>
import { computed, onMounted, ref } from "vue";
import { ChevronLeft, Pencil, Trash2 } from "lucide-vue-next";
import { apiRequest } from "../api/_request.js";
import { loadLanguages } from "../composables/useLanguage.js";
import { useI18n } from "../i18n/index.js";

const { t } = useI18n();
const emit = defineEmits(["back", "open"]);

const rows = ref([]);
const asking = ref("");
const draft = ref("");
const hint = ref("");
const busy = ref(false);

// Two or three letters is a code; anything longer is a name, and the code is taken
// from it. Both are refused by the backend if they do not hold up.
const derivedCode = computed(() => {
  const typed = draft.value.trim();
  if (typed.length <= 3) return typed.toLowerCase();
  return typed.slice(0, 2).toLowerCase();
});

const derivedDeck = computed(() => `EchoWords: ${draft.value.trim()}`);

const deckHint = computed(() =>
  draft.value.trim()
    ? t("languages.deckHint", { deck: derivedDeck.value })
    : t("languages.deckHintEmpty"),
);

onMounted(refresh);

async function refresh() {
  try {
    rows.value = await apiRequest("/api/languages/config");
  } catch (e) {
    hint.value = e.message;
  }
}

async function add() {
  const name = draft.value.trim();
  if (busy.value || !name) return;
  busy.value = true;
  hint.value = "";
  try {
    await apiRequest(`/api/languages/${derivedCode.value}`, {
      method: "PUT",
      body: { name, deck: derivedDeck.value, script: "latin" },
    });
    draft.value = "";
    await refresh();
    await loadLanguages();
  } catch (e) {
    hint.value = e.message;
  } finally {
    busy.value = false;
  }
}

async function remove(code) {
  if (busy.value) return;
  busy.value = true;
  hint.value = "";
  asking.value = "";
  try {
    await apiRequest(`/api/languages/${code}`, { method: "DELETE" });
    await refresh();
    // The selection may have been the language just removed; this replaces it.
    await loadLanguages();
  } catch (e) {
    hint.value = e.message;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <button class="btn-inline back" @click="emit('back')">
    <ChevronLeft :size="12" aria-hidden="true" />
    {{ t("languages.back") }}
  </button>

  <section class="card">
    <h2>{{ t("languages.title") }}</h2>

    <div v-for="row in rows" :key="row.code" class="lang-row" :data-testid="`row-${row.code}`">
      <div v-if="asking !== row.code" class="lang-item">
        <div class="lang-headings">
          <div class="lang-name">
            {{ row.name }}<span class="lang-code">{{ row.code }}</span>
          </div>
          <div class="lang-deck">{{ row.deck }}</div>
        </div>
        <div class="row-actions">
          <button
            class="row-btn"
            :title="t('languages.settings')"
            :aria-label="t('languages.settings')"
            :data-testid="`open-${row.code}`"
            @click="emit('open', row.code)"
          >
            <Pencil :size="16" aria-hidden="true" />
          </button>
          <button
            class="row-btn"
            :title="t('languages.remove')"
            :aria-label="t('languages.remove')"
            :data-testid="`remove-${row.code}`"
            @click="asking = row.code"
          >
            <Trash2 :size="16" aria-hidden="true" />
          </button>
        </div>
      </div>

      <div v-else class="confirm">
        <p class="confirm-text">{{ t("languages.removeConfirm", { name: row.name }) }}</p>
        <div class="confirm-actions">
          <button class="btn-inline btn-danger confirm-yes" @click="remove(row.code)">
            {{ t("languages.removeYes") }}
          </button>
          <button class="btn-inline confirm-no" @click="asking = ''">
            {{ t("languages.removeNo") }}
          </button>
        </div>
      </div>
    </div>
  </section>

  <section class="card">
    <label for="new-lang">{{ t("languages.addTitle") }}</label>
    <input
      id="new-lang"
      v-model="draft"
      type="text"
      autocomplete="off"
      autocapitalize="none"
      spellcheck="false"
      :placeholder="t('languages.addPlaceholder')"
      @keyup.enter="add"
    />
    <button class="btn btn-primary add" :disabled="busy" @click="add">
      {{ t("languages.add") }}
    </button>
    <p class="form-hint deck-hint">{{ deckHint }}</p>
    <p v-if="hint" class="hint">{{ hint }}</p>
  </section>
</template>

<style scoped>
.back {
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
  margin-bottom: 0.75rem;
  padding: 0.25rem 0.5rem 0.25rem 0.3rem;
}

h2 {
  font-size: 1.5rem;
  font-weight: 700;
  margin-bottom: 0.75rem;
}

.lang-row + .lang-row {
  border-top: 1px solid var(--border);
}

.lang-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.7rem 0;
}

.lang-headings {
  min-width: 0;
}

.lang-name {
  font-size: 0.95rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}

.lang-code {
  font-size: 0.65rem;
  font-weight: 500;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-muted);
  border: 1px solid var(--border-strong);
  border-radius: 5px;
  padding: 0.05rem 0.3rem;
}

.lang-deck {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-top: 0.2rem;
}

.row-actions {
  margin-left: auto;
  display: flex;
  gap: 0.35rem;
  flex: 0 0 auto;
}

.row-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  background: none;
  border: 1px solid var(--surface-2);
  border-radius: 8px;
  color: var(--text-muted);
  cursor: pointer;
  transition:
    color 0.15s,
    border-color 0.15s,
    transform 0.1s;
  touch-action: manipulation;
}

.row-btn:hover {
  color: var(--text);
  border-color: var(--accent);
}

.row-btn:active {
  transform: scale(0.94);
}

/* The question replaces the row it came from — never a modal. */
.confirm {
  padding: 0.7rem 0;
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

.btn-danger {
  border-color: var(--error);
  color: var(--error);
}

.btn-danger:hover {
  color: var(--error);
  border-color: var(--error);
}

#new-lang {
  margin-bottom: 0.75rem;
}

.deck-hint {
  margin-top: 0.5rem;
  line-height: 1.5;
}

.hint {
  margin-top: 0.5rem;
  font-size: 0.85rem;
  color: var(--warning);
}
</style>
