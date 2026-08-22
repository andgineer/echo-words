# echo-words

Отправьте слово — получите лингвистический разбор, а карточка окажется в колоде
Anki раньше, чем вы дочитаете разбор до конца.

echo-words — личный помощник для пополнения словарного запаса, доступный только
внутри вашей сети Tailscale: бэкенд на FastAPI и PWA на Vue 3, которые

- потоком отдают компактный разбор слова или выражения — переводы, значения,
  употребление, происхождение и примеры с переводами
- произносят слово: локально через Piper или онлайн через edge-tts
- добавляют двустороннюю заметку в отдельную колоду Anki этого языка, без дублей
- сначала используют бесплатные LLM-провайдеры и лишь потом платную модель
- **не хранят никакой базы данных** и не доступны из интернета

<table>
<tr>
<td align="center" valign="top"><sub><b>Слово или выражение на выбор</b></sub><br/><img src="images/screenshots/add-word.png" width="280"/></td>
<td align="center" valign="top"><sub><b>Разбор, произношение, карточка</b></sub><br/><img src="images/screenshots/card-added.png" width="280"/></td>
<td align="center" valign="top"><sub><b>Любой язык и любая письменность</b></sub><br/><img src="images/screenshots/cyrillic-card.png" width="280"/></td>
</tr>
<tr>
<td align="center" valign="top"><sub><b>Что попало в колоды</b></sub><br/><img src="images/screenshots/stats.png" width="280"/></td>
<td align="center" valign="top"><sub><b>Провайдеры, синхронизация, расходы</b></sub><br/><img src="images/screenshots/status.png" width="280"/></td>
<td></td>
</tr>
</table>

!!! note "Про язык на скриншотах"
    Язык интерфейса переключается в шапке (EN/RU), а язык разборов задаётся
    настройкой `ECHOWORDS_TARGET_LANG` — по умолчанию русский.

### Быстрый старт

1. [Установите приложение](installation.md) и запустите его у себя.
2. [Настройте языки](configuration.md) — по колоде Anki и голосу на каждый язык
   и хотя бы один бесплатный ключ LLM-провайдера.
3. [Разверните на Oracle Cloud](deploy-oracle.md) — $0 в месяц, только внутри
   вашей сети Tailscale.
4. [Установите PWA](pwa-install.md) на телефон и добавьте команду в меню
   «Поделиться».
