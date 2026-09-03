export default {
  "nav.words": "Слова",
  "nav.stats": "Статистика",
  "nav.status": "Состояние",
  "nav.label": "Навигация",
  "nav.locale": "Язык интерфейса",

  "add.wordPlaceholder": "слово или выражение",
  "add.submit": "Разобрать",
  "add.queued": "Нет связи — слово сохранено и будет отправлено позже.",
  "add.empty": "Здесь появятся разборы слов.",
  "add.revert": "↩︎ Вернуть карточку для «{word}»",
  "add.showingOther": "Это «{word}», а не набранное вами «{submitted}».",
  "add.replaceCard": "Заменить карточку на «{word}»",
  "add.analyseInstead": "Разобрать «{word}»",
  "add.unattested":
    "«{word}» — модель не подтверждает такое слово. Карточка не создана.",
  "add.unattestedLookup": "«{word}» — модель не подтверждает такое слово.",
  "add.cardedInstead":
    "«{word}» похоже на опечатку, поэтому карточка создана для «{carded}».",
  "add.analysedInstead": "Это «{shown}», а не набранное вами «{word}».",
  "add.otherWordCard": "Карточка для «{carded}», а не для набранного «{word}».",
  "add.misspelled":
    "«{word}» похоже на опечатку в слове «{suggestion}» — карточка не создана.",
  "add.moreCommon": "Карточка для «{word}»; более употребимым названо «{suggestion}».",
  "add.notInReferences":
    "Слова «{word}» нет в словарях, и Википедия его ни разу не пишет — как и любое " +
    "проверенное выдуманное слово. Карточка всё равно создана.",
  "add.seeUsageSearch": "Поискать в интернете",
  "add.detail": "Полная статья",
  "add.detailReady": "Статья готова",
  "add.deleteCard": "Удалить из Anki",
  "add.deleteCardConfirm":
    "Удалить карточки для «{word}» из Anki? Разбор останется на экране.",
  "add.deleteCardYes": "Удалить",
  "add.deleteCardNo": "Отмена",
  "add.analysing": "Разбираю «{word}» — обычно пара секунд",
  "add.buildingEntry": "Собираю полную статью — обычно около 10 секунд",
  "add.analysisFailed": "Не удалось получить разбор.",
  "add.retry": "Отправить «{word}» ещё раз",
  "add.contextAudio": "Весь текст",
  "add.sentence": "Предложение",
  "add.railLabel": "Разобранные слова",
  "add.aboutHide": "Свернуть",
  "add.aboutShow": "Что это и как пользоваться",
  "add.aboutIntro":
    "echo-words разбирает слово или целое выражение на выбранном языке: перевод, значения, " +
    "употребление, происхождение и примеры — и добавляет одно выбранное значение в Anki " +
    "четырьмя карточками: без контекста и в предложении. Выражение разбирается как целое, " +
    "а его слова остаются отдельными кнопками. Разобранное лежит в ленте слов над карточкой: " +
    "нажмите на слово или пролистайте карточку вбок.",
  "add.aboutText":
    "<b>Предложение или текст</b> получает другой ответ: его переводят и объясняют трудные " +
    "места, но карточку не создают — целое предложение не повторишь. Под ответом появляется " +
    "каждое слово исходного текста, а многословные сочетания остаются вместе; одно нажатие " +
    "разбирает такую кнопку как единицу, а текст остаётся её контекстом.",
  "add.aboutLookup":
    "<b>Только посмотреть.</b> <b>?</b> перед словом — «? слово» — даёт разбор и произношение, " +
    "но карточку не создаёт. Обычно это не нужно: у каждой карточки есть «Удалить из Anki».",
  "add.aboutCorrection":
    "<b>Написание.</b> Над разбором всегда сказано, что стало с введённым словом. Если такого " +
    "слова нет, карточка создаётся для исправленного, и это написано прямо; отменить её можно " +
    "кнопкой «Удалить из Anki». Если слово есть, но чаще пишут иначе, карточка ваша, а рядом " +
    "кнопка заменить её на более частое написание. Если модель не подтверждает слово вовсе, " +
    "карточки нет и разбора тоже — сочинять несуществующее слово она не будет.",

  "languages.title": "Изучаемые языки",
  "languages.edit": "Изменить языки",
  "languages.back": "К словам",
  "languages.backToList": "Языки",
  "languages.settings": "Настройки языка",
  "languages.remove": "Удалить язык",
  "languages.removeConfirm": "Удалить «{name}»? Карточки в Anki останутся.",
  "languages.removeYes": "Удалить",
  "languages.removeNo": "Отмена",
  "languages.addTitle": "Добавить язык",
  "languages.addPlaceholder": "Español или es",
  "languages.add": "Добавить",
  "languages.deckHint":
    "Колода «{deck}» создастся сама. Письменность, голос и словарь можно настроить потом.",
  "languages.deckHintEmpty":
    "Колода создастся сама по названию языка. Письменность, голос и словарь можно " +
    "настроить потом.",
  "languages.name": "Название",
  "languages.deck": "Колода Anki",
  "languages.script": "Письменность",
  "languages.script.latin": "латиница",
  "languages.script.cyrillic": "кириллица",
  "languages.script.latin+cyrillic": "обе",
  "languages.advanced": "Дополнительно",
  "languages.tts": "Озвучка",
  "languages.tts.piper": "Piper — на сервере",
  "languages.tts.edge": "Edge — в сети",
  "languages.voicePiper": "Голос Piper",
  "languages.voiceEdge": "Голос Edge",
  "languages.voiceHint": "Голос скачивается при первом слове и дальше берётся из кэша.",
  "languages.voiceNoSerbian":
    "У Piper нет сербского голоса: единственная модель sr_RS — нижнелужицкая. Возьмите Edge.",
  "languages.dictApi": "Словарь",
  "languages.dictApiPlaceholder": "напр. en",
  "languages.accent": "Акцент",
  "languages.accentPlaceholder": "напр. us",
  "languages.save": "Сохранить",
  "languages.saved": "Сохранено.",

  "card.added": "✅ добавлено в Anki",
  "card.addedCount.one": "✅ 1 карточка: {kinds}",
  "card.addedCount.few": "✅ {count} карточки: {kinds}",
  "card.addedCount.many": "✅ {count} карточек: {kinds}",
  "card.addedCount.other": "✅ {count} карточек: {kinds}",
  "card.kind.recognition": "слово → значение",
  "card.kind.recall": "значение → слово",
  "card.kind.contextRecognition": "предложение → значение",
  "card.kind.contextProduction": "пропуск → слово",
  "card.lookupOnly": "👁 только просмотр",
  "card.deleted": "🗑 карточки удалены из Anki",
  "card.failed": "⚠️ карточка не создана",
  "card.unattested": "🚫 без карточки",
  "card.misspelled": "🚫 без карточки — похоже на опечатку",
  "card.kept": "прежняя карточка осталась",
  "card.noAudio": "🔇 исходный текст без озвучки",
  "card.noCardAudio": "🔇 карточка Anki без озвучки",

  "stats.title": "Статистика",
  "stats.today": "Сегодня: {count}",
  "stats.last7Days": "За 7 дней: {count}",
  "stats.allTime": "Всего: {count}",
  "stats.sinceStart": "После запуска: без карточки {lookupOnly}",

  "status.title": "Состояние",
  "status.never": "нет",
  "status.pool": "LLM: {usable}/{total} провайдеров",
  "status.degraded": " · ограниченный резерв",
  "status.poolUnavailable": "LLM недоступен: {error}",
  "status.missingFreeKeys": "Нет ключей бесплатного пула:",
  "status.missingPaidKeys": "Нет ключей платной модели:",
  "status.paidCalls": "Платных вызовов сегодня: {today}/{cap}",
  "status.ankiweb": "AnkiWeb: {result}",
  "status.neverSynced": "ещё не синхронизировался",
  "status.unsynced": " · есть несинхронизированные изменения",
  "status.lastSync": "Последняя синхронизация: {time}",
  "status.syncError": "Ошибка синхронизации: {error}",
  "status.fullSyncRequired": "Нужна ручная односторонняя синхронизация Anki.",
  "status.paidModel": "Платная модель: {alias} · {availability}",
  "status.paidNotConfigured": "не настроена",
  "status.paidAvailable": "доступна",
  "status.paidUnavailable": "недоступна: {reason}",
  "status.lastCall": "Последний вызов: {result} · {model} · {time}",
  "status.callOk": "успешно",
  "status.callFailed": "ошибка",
  "status.unknownModel": "модель неизвестна",
  "status.noCalls": "Последних вызовов нет.",
};
