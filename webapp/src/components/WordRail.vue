<script setup>
import { nextTick, ref, watch } from "vue";
import { useI18n } from "../i18n/index.js";

const { t } = useI18n();

const props = defineProps({
  entries: { type: Array, default: () => [] },
  selectedId: { type: String, default: "" },
});
const emit = defineEmits(["select"]);

const rail = ref(null);

watch(
  () => props.selectedId,
  async () => {
    await nextTick();
    centreActive();
  },
);

// The rail is the only way back to a word seen a dozen entries ago, so the chip
// under the card is pulled into the middle whenever the selection moves.
function centreActive() {
  const strip = rail.value;
  const chip = strip?.querySelector(".chip.active");
  if (!strip || !chip || typeof strip.scrollTo !== "function") return;
  strip.scrollTo({
    left: Math.max(chip.offsetLeft - strip.clientWidth / 2 + chip.offsetWidth / 2, 0),
    behavior: "smooth",
  });
}

// A pending answer and a running paid call are the same thing to the reader: work
// is happening on that word, and they are free to swipe away from it.
function running(entry) {
  return entry.status === "pending" || !!entry.detail_pending;
}
</script>

<template>
  <div
    v-if="entries.length"
    ref="rail"
    class="chips"
    role="tablist"
    :aria-label="t('add.railLabel')"
  >
    <button
      v-for="entry in entries"
      :key="entry.entry_id"
      type="button"
      class="chip"
      :class="{ active: entry.entry_id === selectedId, running: running(entry) }"
      role="tab"
      :aria-selected="entry.entry_id === selectedId"
      :title="entry.word"
      :data-testid="`chip-${entry.entry_id}`"
      @click="emit('select', entry.entry_id)"
    >
      {{ entry.word }}
    </button>
  </div>
</template>

<style scoped>
.chips {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  overscroll-behavior-x: contain;
  padding-bottom: 8px;
  /* macOS otherwise paints a full-width white bar across the dark card. */
  scrollbar-width: thin;
  scrollbar-color: var(--border-strong) transparent;
}

.chips::-webkit-scrollbar {
  height: 4px;
}

.chips::-webkit-scrollbar-track {
  background: transparent;
}

.chips::-webkit-scrollbar-thumb {
  background: var(--border-strong);
  border-radius: 999px;
}

.chip {
  flex: 0 0 auto;
  padding: 0.3rem 0.65rem;
  border-radius: 999px;
  font-family: inherit;
  font-size: 0.8rem;
  cursor: pointer;
  /* A sentence is an entry like any other; unbounded it would crowd out the words. */
  max-width: 148px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  border: 1px solid var(--border-strong);
  background: var(--field);
  color: var(--text-muted);
  transition:
    transform 0.1s,
    background 0.12s,
    border-color 0.12s;
  touch-action: manipulation;
}

.chip:active {
  transform: scale(0.94);
}

.chip.active {
  border-color: var(--accent);
  background: color-mix(in srgb, var(--accent) 14%, transparent);
  color: var(--text);
  font-weight: 600;
}

/* No ⏳ prefix: a prefix makes the chip jump in width when the answer lands. */
.chip.running::after {
  content: "";
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-left: 6px;
  border-radius: 999px;
  background: var(--accent);
  vertical-align: middle;
  animation: pulse 1.1s ease-in-out infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.2;
  }
}
</style>
