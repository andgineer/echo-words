export default {
  "nav.words": "Words",
  "nav.stats": "Stats",
  "nav.status": "Status",
  "nav.label": "Navigation",
  "nav.locale": "Interface language",

  "add.wordPlaceholder": "a word or a phrase",
  "add.submit": "Analyse",
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
  "add.notInReferences":
    "No dictionary has “{word}” and Wikipedia never writes it — nor any invented " +
    "word tested. The card was still made.",
  "add.seeUsageSearch": "Search the web",
  "add.detail": "The full entry",
  "add.detailReady": "The entry is ready",
  "add.deleteCard": "Delete from Anki",
  "add.deleteCardConfirm":
    "Delete the cards for “{word}” from Anki? The analysis stays on the screen.",
  "add.deleteCardYes": "Delete",
  "add.deleteCardNo": "Cancel",
  "add.analysing": "Analysing “{word}” — usually a couple of seconds",
  "add.buildingEntry": "Building the full entry — usually about 10 seconds",
  "add.analysisFailed": "Could not get the analysis.",
  "add.retry": "Send “{word}” again",
  "add.contextAudio": "The whole text",
  "add.sentence": "Sentence",
  "add.railLabel": "Analysed words",
  "add.aboutHide": "Hide",
  "add.aboutShow": "What this is and how to use it",
  "add.aboutIntro":
    "echo-words analyses a word or a whole expression in the language you pick: translation, " +
    "senses, usage, origin and examples — and adds one selected sense to Anki as four cards, " +
    "so it is reviewed from both bare and sentence prompts. An expression is analysed as one thing, " +
    "and its component words remain available as separate chips. Everything analysed stays in the " +
    "rail of words above the card: tap a word, or swipe the card sideways.",
  "add.aboutText":
    "<b>A sentence or a longer text</b> gets a different answer: it is translated and its hard " +
    "parts are explained, and it makes no card — a whole sentence is not reviewable. Under the " +
    "answer comes every source word, with multi-word combinations kept together; one tap " +
    "analyses that chip as a unit, with the text kept as its context.",
  "add.aboutLookup":
    "<b>Look up only.</b> A leading <b>?</b> — “? word” — gives you the analysis and the " +
    "pronunciation without creating a card. It is rarely needed: every card offers " +
    "“Delete from Anki”.",
  "add.aboutCorrection":
    "<b>Spelling.</b> What became of the word you typed is always said above the analysis. When " +
    "no such word exists, the card is made for the corrected one and says so; the card's own " +
    "“Delete from Anki” removes it. " +
    "When the word exists but another spelling is the usual one, the card is yours and a button " +
    "offers to replace it. When the model does not vouch for the word at all, there is no card " +
    "and no article: it will not invent a word that nobody uses.",

  "languages.title": "Languages you study",
  "languages.edit": "Edit the languages",
  "languages.back": "Back to the words",
  "languages.backToList": "Languages",
  "languages.settings": "Language settings",
  "languages.remove": "Remove this language",
  "languages.removeConfirm": "Remove “{name}”? Its cards stay in Anki.",
  "languages.removeYes": "Remove",
  "languages.removeNo": "Cancel",
  "languages.addTitle": "Add a language",
  "languages.addPlaceholder": "Español, or es",
  "languages.add": "Add",
  "languages.deckHint":
    "The deck “{deck}” is created for it. Script, voice and dictionary can be set afterwards.",
  "languages.deckHintEmpty":
    "The deck is named after the language. Script, voice and dictionary can be set afterwards.",
  "languages.name": "Name",
  "languages.deck": "Anki deck",
  "languages.script": "Script",
  "languages.script.latin": "Latin",
  "languages.script.cyrillic": "Cyrillic",
  "languages.script.latin+cyrillic": "both",
  "languages.advanced": "Advanced",
  "languages.tts": "Voice",
  "languages.tts.piper": "Piper — on the server",
  "languages.tts.edge": "Edge — over the network",
  "languages.voicePiper": "Piper voice",
  "languages.voiceEdge": "Edge voice",
  "languages.voiceHint": "The voice is fetched with the first word and cached from then on.",
  "languages.voiceNoSerbian":
    "Piper has no Serbian voice: its lone sr_RS model is Lower Sorbian. Use Edge.",
  "languages.dictApi": "Dictionary",
  "languages.dictApiPlaceholder": "e.g. en",
  "languages.accent": "Accent",
  "languages.accentPlaceholder": "e.g. us",
  "languages.save": "Save",
  "languages.saved": "Saved.",

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
  "card.deleted": "🗑 cards deleted from Anki",
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
