<script setup>
import { computed } from "vue";
import { useI18n } from "../i18n/index.js";
import {
  ask,
  isAsking,
  refusals,
  retry,
  setDraft,
  turnState,
} from "../composables/useFollowUps.js";

const { t } = useI18n();

const props = defineProps({
  entry: { type: Object, required: true },
});

const turns = computed(() => props.entry.follow_ups ?? []);
const draft = computed({
  get: () => props.entry.follow_up_draft ?? "",
  set: (text) => setDraft(props.entry.entry_id, text),
});
const asking = computed(() => isAsking(props.entry));
const refusal = computed(() => refusals[props.entry.entry_id] ?? "");

function cutNote(turn) {
  if (turn.unsent) return t("ask.unsent");
  return turn.answer ? t("ask.cutOff") : t("ask.noReply");
}

function send(event) {
  // Enter that confirms an input-method composition is not a send.
  if (event?.isComposing) return;
  void ask(props.entry.entry_id);
}
</script>

<template>
  <section class="questions">
    <div
      v-for="turn in turns"
      :key="turn.id"
      class="turn"
      :data-state="turnState(turn)"
    >
      <p class="turn-question selectable">{{ turn.question }}</p>
      <p v-if="turn.answer" class="turn-answer selectable">{{ turn.answer }}</p>
      <div v-if="turnState(turn) === 'asking' && !turn.answer" class="turn-waiting">
        <span class="spinner" aria-hidden="true"></span>
      </div>
      <div v-if="turnState(turn) === 'cut'" class="turn-cut">
        <span class="turn-cut-note">{{ cutNote(turn) }}</span>
        <button
          class="btn-inline turn-retry"
          :disabled="asking"
          @click="retry(entry.entry_id, turn.id)"
        >
          {{ t("ask.retry") }}
        </button>
      </div>
    </div>

    <form class="ask" @submit.prevent="send()">
      <input
        v-model="draft"
        class="ask-field"
        type="text"
        autocomplete="off"
        enterkeyhint="send"
        :aria-label="t('ask.label')"
        :placeholder="t('ask.label')"
        @keydown.enter.prevent="send($event)"
      />
      <button class="btn btn-primary ask-send" type="submit" :disabled="asking || !draft.trim()">
        {{ t("ask.send") }}
      </button>
    </form>
    <p v-if="refusal" class="ask-refusal">{{ refusal }}</p>
  </section>
</template>

<style scoped>
.questions {
  margin-top: 1.25rem;
  border-top: 1px solid var(--border);
  padding-top: 0.9rem;
}

.turn + .turn {
  margin-top: 0.9rem;
}

.turn-question {
  margin-left: auto;
  width: fit-content;
  max-width: 85%;
  padding: 0.45rem 0.7rem;
  border-radius: 12px;
  background: var(--surface-2);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.turn-answer {
  margin-top: 0.5rem;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.turn-waiting {
  margin-top: 0.5rem;
}

.turn-cut {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.4rem;
  font-size: 0.85rem;
  color: var(--warning);
}

.turn-retry {
  min-height: 32px;
  padding: 0 0.75rem;
  font-size: 0.8rem;
}

.spinner {
  display: inline-block;
  width: 13px;
  height: 13px;
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

.ask {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.9rem;
}

.ask-field {
  flex: 1 1 auto;
  min-width: 0;
  /* The card around it refuses selection for the swipe, and WebKit carries that into
     a field inside it: the caret and a paste need it back. */
  user-select: text;
  -webkit-user-select: text;
}

.ask-send {
  flex: 0 0 auto;
  width: auto;
  padding: 0 1rem;
  touch-action: manipulation;
}

.ask-refusal {
  margin-top: 0.5rem;
  font-size: 0.85rem;
  color: var(--error);
}
</style>
