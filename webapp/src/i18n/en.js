export default {
  "nav.words": "Words",
  "nav.stats": "Stats",
  "nav.status": "Status",
  "nav.label": "Navigation",
  "nav.locale": "Interface language",

  "add.language": "Language",
  "add.word": "Word or phrase",
  "add.wordPlaceholder": "word",
  "add.lookupOnly": "Look up only — no Anki card",
  "add.submit": "Analyse",
  "add.undo": "Undo the last one",
  "add.undone": "Removed: {word}",
  "add.nothingToUndo": "Nothing to undo",
  "add.queued": "No connection — the word is saved and will be sent later.",
  "add.empty": "Word analyses will appear here.",
  "add.revert": "↩︎ Revert to “{word}”",
  "add.correct": "✏️ Correct to “{word}”",
  "add.keep": "✓ Keep “{word}”",
  "add.rebuild": "Rebuild the card",
  "add.detailReady": "Full analysis ready",
  "add.detail": "More detail",
  "add.noCard": "no card",
  "add.textNoCard": "text — no card",
  "add.analysisFailed": "Could not get the analysis. Try sending the word again.",
  "add.contextAudio": "The whole text",
  "add.text": "Words and combinations — tap one to analyse it:",
  "add.expression": "Words in this expression — tap one to analyse it:",
  "add.senses": "Senses of this word — tap one to analyse it:",
  "add.aboutHide": "Hide",
  "add.aboutShow": "What this is and how to use it",
  "add.aboutIntro":
    "echo-words analyses a word or a whole expression in the language you pick: translation, " +
    "senses, usage, origin and examples — and adds one selected sense to Anki as four cards, " +
    "so it is reviewed from both bare and sentence prompts. An expression is analysed as one thing, " +
    "and its component words remain available as separate chips.",
  "add.aboutText":
    "<b>A sentence or a longer text</b> gets a different answer: it is translated and its hard " +
    "parts are explained, and it makes no card — a whole sentence is not reviewable. Under the " +
    "answer comes every source word, with multi-word combinations kept together; one tap " +
    "analyses that chip as a unit, with the text kept as its context.",
  "add.aboutLookup":
    "<b>Look up only.</b> The checkbox next to the input gives you the analysis and the " +
    "pronunciation without creating a card. A leading <b>?</b> does the same: “? word”.",
  "add.aboutCorrection":
    "<b>✏️ Correct.</b> The submitted text stays in the history; a unit card uses the validated " +
    "dictionary headword returned by the analysis. When the input looks like a typo, no card is " +
    "created until you choose a spelling: under the analysis a ✏️ button offers the corrected " +
    "spelling and a ✓ button asks for yours to be analysed as a word. Either way the card is " +
    "made from the spelling that was actually analysed.",

  "card.added": "✅ added to Anki",
  "card.addedCount.one": "✅ 1 card: {kinds}",
  // English selects neither "few" nor "many"; the catalogues are keyed alike.
  "card.addedCount.few": "✅ {count} cards: {kinds}",
  "card.addedCount.many": "✅ {count} cards: {kinds}",
  "card.addedCount.other": "✅ {count} cards: {kinds}",
  "card.kind.recognition": "word → meaning",
  "card.kind.recall": "meaning → word",
  "card.kind.contextRecognition": "sentence → meaning",
  "card.kind.contextProduction": "gap → word",
  "card.lookupOnly": "👁 lookup only",
  "card.text": "👁 text — no card",
  "card.failed": "⚠️ card failed",
  "card.spelling": "✏️ looks like a typo — no card yet",
  "card.spellingRefused": "⚠️ the model will not analyse this spelling as a word",
  "card.kept": "the card you had is untouched",
  "card.noAudio": "🔇 submitted text has no audio",
  "card.noCardAudio": "🔇 Anki card has no audio",

  "stats.title": "Stats",
  "stats.today": "Today: {count}",
  "stats.last7Days": "Last 7 days: {count}",
  "stats.allTime": "All time: {count}",
  "stats.sinceStart": "Since startup: {lookupOnly} without a card",

  "status.title": "Status",
  "status.never": "never",
  "status.pool": "LLM: {usable}/{total} providers",
  "status.degraded": " · limited fallback",
  "status.poolUnavailable": "LLM unavailable: {error}",
  "status.missingFreeKeys": "Free-pool keys missing:",
  "status.missingPaidKeys": "Paid-model keys missing:",
  "status.paidCalls": "Paid calls today: {today}/{cap}",
  "status.ankiweb": "AnkiWeb: {result}",
  "status.neverSynced": "not synced yet",
  "status.unsynced": " · unsynced changes",
  "status.lastSync": "Last sync: {time}",
  "status.syncError": "Sync error: {error}",
  "status.fullSyncRequired": "A manual one-way Anki sync is required.",
  "status.paidModel": "Paid model: {alias} · {availability}",
  "status.paidNotConfigured": "not configured",
  "status.paidAvailable": "available",
  "status.paidUnavailable": "unavailable: {reason}",
  "status.lastCall": "Last call: {result} · {model} · {time}",
  "status.callOk": "ok",
  "status.callFailed": "failed",
  "status.unknownModel": "model unknown",
  "status.noCalls": "No recent calls.",
};
