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

const ENGINES = ["piper", "edge"];

const label = ref("");
const script = ref("");
const piperUnusable = ref(false);
const piperVoices = ref([]);
const answers = ref("unmeasured");
const form = ref({
  deck: "",
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

// A language with no engine set shows none chosen, rather than claiming the one it
// would default to: nothing in the file says so, and a save would not write it.
const engine = computed(() => (ENGINES.includes(form.value.tts) ? form.value.tts : ""));

// A Piper voice is offered rather than typed: only the app's own pinned downloads can
// reach the server, and the backend refuses any other. One configured by hand stays on
// the list, because the backend keeps accepting the value already in the file.
const piperOptions = computed(() => {
  const configured = form.value.tts_voice;
  return configured && !piperVoices.value.includes(configured)
    ? [...piperVoices.value, configured]
    : piperVoices.value;
});

// Which languages Piper's model actually voices is the directory's to know
// (spec/decision-tts.md), and which of those voices this server can install is the
// backend's; neither is this screen's. Offering the engine without one is a promise of
// a download that never happens, so the choice is closed instead of explained after.
// Over the options rather than the build's own list: a voice already in the file is
// one the backend keeps accepting, so a language voiced by hand is offered Piper
// instead of being told this build has none and locked out of the engine it is using.
const piperOffered = computed(() => !piperUnusable.value && piperOptions.value.length > 0);
const noPiperReason = computed(() =>
  piperUnusable.value ? t("languages.voiceNoPiper") : t("languages.voiceNoPiperBuild"),
);

// What the bench has measured about this language's answers, in the reader's words: a
// language nobody measured answers as fluently as one that was (decision-llm-backend).
const answersNote = computed(() => {
  if (answers.value === "unreliable") return t("languages.answersUnreliable");
  if (answers.value === "unmeasured") return t("languages.answersUnmeasured");
  return "";
});

const voiceHint = computed(() => {
  if (engine.value !== "piper") return t("languages.voiceHint");
  if (!piperOffered.value) return noPiperReason.value;
  return t("languages.voicePiperInstalled", { voices: form.value.tts_voice });
});

onMounted(async () => {
  try {
    const table = await apiRequest("/api/languages/config");
    const found = table.find((language) => language.code === props.code);
    if (!found) {
      emit("done");
      return;
    }
    label.value = found.name ?? "";
    script.value = found.script ?? "";
    form.value = {
      deck: found.deck ?? "",
      tts: found.tts ?? "",
      tts_voice: found.tts_voice ?? "",
      edge_tts_voice: found.edge_tts_voice ?? "",
      dict_api: found.dict_api ?? "",
      accent: found.accent ?? "",
    };
    const catalog = await apiRequest("/api/languages/catalog");
    const listed = catalog.find((entry) => entry.code === props.code);
    piperUnusable.value = Boolean(listed?.piper_unusable);
    piperVoices.value = listed?.piper_voices ?? [];
    answers.value = listed?.answers ?? "unmeasured";
  } catch (e) {
    hint.value = e.message;
  }
});

function pickEngine(value) {
  form.value.tts = value;
  // The one voice the server would install, so choosing Piper is not choosing silence.
  if (value === "piper" && !form.value.tts_voice && piperVoices.value.length === 1) {
    form.value.tts_voice = piperVoices.value[0];
  }
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
      <h2>{{ label || code }}</h2>
      <span class="lang-code">{{ code }}</span>
    </div>

    <p
      v-if="answersNote"
      class="form-hint answers-note"
      :class="{ warn: answers === 'unreliable' }"
    >
      {{ answersNote }}
    </p>

    <div class="group">
      <label for="lang-deck">{{ t("languages.deck") }}</label>
      <input id="lang-deck" v-model="form.deck" type="text" autocomplete="off" />
    </div>

    <div v-if="script" class="group">
      <span class="group-label">{{ t("languages.script") }}</span>
      <p class="script-fact" data-testid="script">{{ t(`languages.script.${script}`) }}</p>
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
            :disabled="item === 'piper' && !piperOffered && engine !== 'piper'"
            @click="pickEngine(item)"
          >
            {{ t(`languages.tts.${item}`) }}
          </button>
        </div>
        <p v-if="!piperOffered" class="form-hint warn no-piper">{{ noPiperReason }}</p>
      </div>

      <div v-if="engine === 'edge'" class="group">
        <label for="lang-voice">{{ t("languages.voiceEdge") }}</label>
        <input id="lang-voice" v-model="form.edge_tts_voice" type="text" autocomplete="off" />
        <p class="form-hint voice-hint">{{ voiceHint }}</p>
      </div>

      <div v-else-if="engine === 'piper'" class="group">
        <span class="group-label">{{ t("languages.voicePiper") }}</span>
        <div v-if="piperOptions.length" class="seg-container opt-row">
          <button
            v-for="voice in piperOptions"
            :key="voice"
            class="opt-btn"
            :class="{ active: form.tts_voice === voice }"
            :data-testid="`voice-${voice}`"
            @click="form.tts_voice = voice"
          >
            {{ voice }}
          </button>
        </div>
        <p class="form-hint voice-hint" :class="{ warn: !piperOffered }">{{ voiceHint }}</p>
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
      <p class="confirm-text">{{ t("languages.removeConfirm", { name: label || code }) }}</p>
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

.opt-btn:disabled {
  background: var(--field-deep);
  color: var(--text-muted);
  cursor: not-allowed;
}

.opt-btn:disabled:active {
  transform: none;
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

.script-fact {
  font-size: 0.95rem;
}

.voice-hint {
  margin-top: 0.4rem;
  line-height: 1.5;
}

.voice-hint.warn,
.no-piper,
.answers-note.warn {
  color: var(--warning);
}

.answers-note {
  margin: 0 0 1rem;
  line-height: 1.5;
}

.no-piper {
  margin-top: 0.4rem;
  line-height: 1.5;
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
