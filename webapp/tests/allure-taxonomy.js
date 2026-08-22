export const EPIC = Object.freeze({
  VOCABULARY_ANALYSIS: "Vocabulary analysis",
  ANKI_CARDS: "Anki cards",
  PRONUNCIATION: "Pronunciation",
  APPLICATION_PLATFORM: "Application platform",
});

export const FEATURE = Object.freeze({
  INPUT_AND_LANGUAGES: "Input and languages",
  LLM_CASCADE: "LLM cascade",
  ANSWER_DELIVERY: "Answer delivery",
  CORRECTION_AND_DETAIL: "Correction and detail",
  HISTORY: "History",
  CARD_CONTRACT: "Card contract",
  COLLECTION: "Collection",
  DUPLICATES_AND_REBUILD: "Duplicates and rebuild",
  ANKIWEB_SYNC: "AnkiWeb sync",
  STATS_AND_UNDO: "Stats and undo",
  RECORDING_LOOKUP: "Recording lookup",
  LOCAL_TTS: "Local TTS",
  ONLINE_FALLBACK: "Online fallback",
  AUDIO_DELIVERY: "Audio delivery",
  CONFIGURATION_AND_LIFECYCLE: "Configuration and lifecycle",
  API_CLIENT: "API client",
  PWA_RESILIENCE: "PWA resilience",
  INTERFACE_LANGUAGE: "Interface language",
  HEALTH_AND_DEPLOYMENT: "Health and deployment",
});

export async function labelBehavior(epic, feature, story = null) {
  await allure.epic(epic);
  await allure.feature(feature);
  if (story) await allure.story(story);
}
