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
  "add.revert": "↩︎ Go back to a card for “{word}”",
  "add.showingOther": "This is “{word}”, not the “{submitted}” you typed.",
  "add.replaceCard": "Replace the card with “{word}”",
  "add.analyseInstead": "Analyse “{word}” instead",
  "add.unattested":
    "“{word}” — the model does not vouch for this word. No card was made.",
  "add.unattestedLookup": "“{word}” — the model does not vouch for this word.",
  "add.cardedInstead":
    "“{word}” looks like a typo, so the card is for “{carded}” instead.",
  "add.analysedInstead": "This is “{shown}”, not the “{word}” you typed.",
  "add.otherWordCard": "The card is for “{carded}”, not the “{word}” you typed.",
  "add.misspelled":
    "“{word}” looks like a typo for “{suggestion}”, so no card was made.",
  "add.moreCommon": "The card is for “{word}”; “{suggestion}” is named the more usual spelling.",
  "add.rebuild": "Rebuild the card",
  "add.detailReady": "Full analysis ready",
  "add.detail": "More detail",
  "add.noCard": "no card",
  "add.textNoCard": "text — no card",
  "add.analysisFailed": "Could not get the analysis.",
  "add.retry": "Send “{word}” again",
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
    "<b>Spelling.</b> What became of the word you typed is always said above the analysis. When " +
    "no such word exists, the card is made for the corrected one and says so; undo removes it. " +
    "When the word exists but another spelling is the usual one, the card is yours and a button " +
    "offers to replace it. When the model does not vouch for the word at all, there is no card " +
    "and no article: it will not invent a word that nobody uses.",

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
  "card.unattested": "🚫 no card",
  "card.misspelled": "🚫 no card — looks misspelled",
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
