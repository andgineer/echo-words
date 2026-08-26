export default {
  "nav.words": "Слова",
  "nav.stats": "Статистика",
  "nav.status": "Состояние",
  "nav.label": "Навигация",
  "nav.locale": "Язык интерфейса",

  "add.language": "Язык",
  "add.word": "Слово или выражение",
  "add.wordPlaceholder": "слово",
  "add.lookupOnly": "Только посмотреть — без карточки в Anki",
  "add.submit": "Разобрать",
  "add.undo": "Отменить последнее",
  "add.undone": "Удалено: {word}",
  "add.nothingToUndo": "Нечего отменять",
  "add.queued": "Нет связи — слово сохранено и будет отправлено позже.",
  "add.empty": "Здесь появятся разборы слов.",
  "add.revert": "↩︎ Вернуть «{word}»",
  "add.correct": "✏️ Исправить на «{word}»",
  "add.rebuild": "Пересобрать карточку",
  "add.detailReady": "Подробный разбор готов",
  "add.detail": "Подробнее",
  "add.noCard": "без карточки",
  "add.textNoCard": "текст — без карточки",
  "add.analysisFailed": "Не удалось получить разбор. Попробуйте отправить слово ещё раз.",
  "add.contextAudio": "Весь текст",
  "add.segments": "Стоит разобрать отдельно:",
  "add.senses": "У слова есть и другие значения — нажмите, чтобы разобрать:",
  "add.aboutHide": "Свернуть",
  "add.aboutShow": "Что это и как пользоваться",
  "add.aboutIntro":
    "echo-words разбирает слово или целое выражение на выбранном языке: перевод, значения, " +
    "употребление, происхождение и примеры — и сам добавляет компактную карточку в Anki, " +
    "чтобы слово попало в повторения. Выражение разбирается целиком: приложение не " +
    "спрашивает, какое из его слов вы имели в виду.",
  "add.aboutText":
    "<b>Предложение или текст</b> получает другой ответ: его переводят и объясняют трудные " +
    "места, но карточку не создают — целое предложение не повторишь. Под ответом появляется " +
    "то, что стоит разобрать отдельно; одно нажатие разбирает такую единицу как обычное " +
    "слово, а текст остаётся её контекстом.",
  "add.aboutLookup":
    "<b>Только посмотреть.</b> Галочка рядом с полем ввода даёт разбор и произношение, но " +
    "карточку не создаёт. То же самое делает <b>?</b> перед словом: «? слово».",
  "add.aboutCorrection":
    "<b>✏️ Исправить.</b> Слово всегда разбирается ровно так, как введено, и именно так " +
    "попадает в карточку. Если оно похоже на опечатку, под разбором появится кнопка ✏️ с " +
    "исправленным написанием — разбор повторится для него, и вернуться обратно можно одним " +
    "нажатием.",

  "card.added": "✅ добавлено в Anki",
  "card.addedCount.one": "✅ 1 карточка: {kinds}",
  "card.addedCount.few": "✅ {count} карточки: {kinds}",
  "card.addedCount.many": "✅ {count} карточек: {kinds}",
  "card.addedCount.other": "✅ {count} карточек: {kinds}",
  "card.kind.recognition": "узнавание",
  "card.kind.recall": "воспроизведение",
  "card.kind.context": "контекст",
  "card.kind.sense": "по значению",
  "card.contextNotNeeded": "контекст не понадобился",
  "card.lookupOnly": "👁 только просмотр",
  "card.text": "👁 текст — без карточки",
  "card.fragment": "👁 фрагмент — без карточки",
  "card.failed": "⚠️ карточка не создана",
  "card.noAudio": "🔇 без озвучки",

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
