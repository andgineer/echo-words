<script setup>
import { computed, onMounted, ref } from "vue";
import { ChevronDown, ChevronLeft } from "lucide-vue-next";
import { apiRequest } from "../api/_request.js";
import { loadLanguages } from "../composables/useLanguage.js";
import { useI18n } from "../i18n/index.js";

const { t } = useI18n();

const props = defineProps({
  code: { type: String, required: true },
});
const emit = defineEmits(["back", "done"]);

const SCRIPTS = ["latin", "cyrillic", "latin+cyrillic"];
const ENGINES = ["piper", "edge"];

const form = ref({
  name: "",
  deck: "",
  script: "latin",
  tts: "",
  tts_voice: "",
  edge_tts_voice: "",
  dict_api: "",
  accent: "",
});
const advanced = ref(false);
const asking = ref(false);
const hint = ref("");
const saved = ref(false);
const busy = ref(false);

const engine = computed(() => (form.value.tts === "edge" ? "edge" : "piper"));
const voiceField = computed(() => (engine.value === "edge" ? "edge_tts_voice" : "tts_voice"));

// Piper's only sr_RS model is Lower Sorbian, so choosing it for Serbian gets a voice
// of another language rather than none (spec/decision-tts.md).
const piperHasNoVoice = computed(() => engine.value === "piper" && props.code === "sr");

const voiceHint = computed(() =>
  piperHasNoVoice.value ? t("languages.voiceNoSerbian") : t("languages.voiceHint"),
);

onMounted(async () => {
  try {
    const table = await apiRequest("/api/languages/config");
    const found = table.find((language) => language.code === props.code);
    if (!found) {
      emit("done");
      return;
    }
    form.value = {
      name: found.name ?? "",
      deck: found.deck ?? "",
      script: found.script ?? "latin",
      tts: found.tts ?? "",
      tts_voice: found.tts_voice ?? "",
      edge_tts_voice: found.edge_tts_voice ?? "",
      dict_api: found.dict_api ?? "",
      accent: found.accent ?? "",
    };
  } catch (e) {
    hint.value = e.message;
  }
});

function pickEngine(value) {
  form.value.tts = value;
  saved.value = false;
}

async function save() {
  if (busy.value) return;
  busy.value = true;
  hint.value = "";
  saved.value = false;
  try {
    await apiRequest(`/api/languages/${props.code}`, { method: "PUT", body: { ...form.value } });
    await loadLanguages();
    saved.value = true;
  } catch (e) {
    hint.value = e.message;
  } finally {
    busy.value = false;
  }
}

async function remove() {
  if (busy.value) return;
  busy.value = true;
  hint.value = "";
  asking.value = false;
  try {
    await apiRequest(`/api/languages/${props.code}`, { method: "DELETE" });
    // The removed language may have been the selected one; this replaces it.
    await loadLanguages();
    emit("done");
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
    {{ t("languages.backToList") }}
  </button>

  <section class="card">
    <div class="detail-title">
      <h2>{{ form.name || code }}</h2>
      <span class="lang-code">{{ code }}</span>
    </div>

    <div class="group">
      <label for="lang-name">{{ t("languages.name") }}</label>
      <input id="lang-name" v-model="form.name" type="text" autocomplete="off" />
    </div>

    <div class="group">
      <label for="lang-deck">{{ t("languages.deck") }}</label>
      <input id="lang-deck" v-model="form.deck" type="text" autocomplete="off" />
    </div>

    <div class="group">
      <span class="group-label">{{ t("languages.script") }}</span>
      <div class="seg-container opt-row">
        <button
          v-for="item in SCRIPTS"
          :key="item"
          class="opt-btn"
          :class="{ active: form.script === item }"
          :data-testid="`script-${item}`"
          @click="form.script = item"
        >
          {{ t(`languages.script.${item}`) }}
        </button>
      </div>
    </div>

    <button class="collapse" data-testid="advanced" @click="advanced = !advanced">
      <ChevronDown
        :size="14"
        aria-hidden="true"
        :style="{ transform: advanced ? 'rotate(180deg)' : 'rotate(0deg)' }"
      />
      {{ t("languages.advanced") }}
    </button>

    <div v-if="advanced" class="advanced-fields">
      <div class="group">
        <span class="group-label">{{ t("languages.tts") }}</span>
        <div class="seg-container opt-row">
          <button
            v-for="item in ENGINES"
            :key="item"
            class="opt-btn"
            :class="{ active: engine === item }"
            :data-testid="`tts-${item}`"
            @click="pickEngine(item)"
          >
            {{ t(`languages.tts.${item}`) }}
          </button>
        </div>
      </div>

      <div class="group">
        <label for="lang-voice">
          {{ engine === "edge" ? t("languages.voiceEdge") : t("languages.voicePiper") }}
        </label>
        <input id="lang-voice" v-model="form[voiceField]" type="text" autocomplete="off" />
        <p class="form-hint voice-hint" :class="{ warn: piperHasNoVoice }">{{ voiceHint }}</p>
      </div>

      <div class="pair">
        <div>
          <label for="lang-dict">{{ t("languages.dictApi") }}</label>
          <input
            id="lang-dict"
            v-model="form.dict_api"
            type="text"
            autocomplete="off"
            :placeholder="t('languages.dictApiPlaceholder')"
          />
        </div>
        <div>
          <label for="lang-accent">{{ t("languages.accent") }}</label>
          <input
            id="lang-accent"
            v-model="form.accent"
            type="text"
            autocomplete="off"
            :placeholder="t('languages.accentPlaceholder')"
          />
        </div>
      </div>
    </div>

    <div v-if="!asking" class="footer-actions">
      <button class="btn btn-primary btn-save" :disabled="busy" @click="save">
        {{ t("languages.save") }}
      </button>
      <button class="btn-inline btn-danger remove" @click="asking = true">
        {{ t("languages.remove") }}
      </button>
    </div>

    <div v-else class="confirm">
      <p class="confirm-text">{{ t("languages.removeConfirm", { name: form.name || code }) }}</p>
      <div class="confirm-actions">
        <button class="btn-inline btn-danger confirm-yes" @click="remove">
          {{ t("languages.removeYes") }}
        </button>
        <button class="btn-inline confirm-no" @click="asking = false">
          {{ t("languages.removeNo") }}
        </button>
      </div>
    </div>

    <p v-if="saved" class="form-hint saved">{{ t("languages.saved") }}</p>
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

.detail-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.detail-title h2 {
  font-size: 1.5rem;
  font-weight: 700;
}

.lang-code {
  font-size: 0.65rem;
  font-weight: 500;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--text-muted);
  border: 1px solid var(--border-strong);
  border-radius: 5px;
  padding: 0.1rem 0.35rem;
}

.group {
  margin-bottom: 1rem;
}

.group-label {
  display: block;
  font-size: 0.8rem;
  color: var(--text-muted);
  margin-bottom: 0.3rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 500;
}

.seg-container {
  display: flex;
  align-items: center;
  gap: 3px;
  background: var(--field-deep);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 3px;
}

.opt-btn {
  flex: 1;
  min-width: 0;
  height: 34px;
  border: none;
  border-radius: 9px;
  font-family: inherit;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  color: var(--accent);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition:
    background 0.15s,
    color 0.15s,
    box-shadow 0.15s,
    transform 0.1s;
  touch-action: manipulation;
}

.opt-btn:active {
  transform: scale(0.95);
}

.opt-btn.active {
  background: var(--accent);
  color: #fff;
  box-shadow: 0 4px 12px color-mix(in srgb, var(--accent) 40%, transparent);
}

.collapse {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  width: 100%;
  background: none;
  border: none;
  border-top: 1px solid var(--border);
  color: var(--text-muted);
  font-family: inherit;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 500;
  padding: 0.75rem 0;
  margin-bottom: 0.25rem;
  cursor: pointer;
}

.pair {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.voice-hint {
  margin-top: 0.4rem;
  line-height: 1.5;
}

.voice-hint.warn {
  color: var(--warning);
}

.footer-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-top: 1.25rem;
}

.btn-save {
  flex: 1;
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
  margin-top: 1.25rem;
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

.saved {
  margin-top: 0.5rem;
  color: var(--success);
}

.hint {
  margin-top: 0.5rem;
  font-size: 0.85rem;
  color: var(--warning);
}
</style>
