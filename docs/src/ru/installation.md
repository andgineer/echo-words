# Установка

Нужны Python 3.12+ и [uv](https://docs.astral.sh/uv/). Node.js 22 требуется
только для сборки PWA из исходников.

## Установка `uv`

[Установка `uv`](https://docs.astral.sh/uv/getting-started/installation/)

## Установка приложения

```bash
uv tool install echo-words --upgrade --python 3.13
```

## Запуск из исходников

Именно так приложение разрабатывают и разворачивают:

```bash
git clone https://github.com/andgineer/echo-words.git
cd echo-words
uv sync
npm --prefix webapp ci
mkdir -p ~/.echo-words
cp languages.example.toml ~/.echo-words/languages.toml
inv build-static
inv dev
```

`inv dev` отдаёт собранный бандл на <http://127.0.0.1:8080> и сам копирует
`languages.example.toml`, если файла настроек ещё нет.

Чтобы первый же разбор удался, нужен хотя бы один ключ LLM-провайдера — см.
[Настройку](configuration.md).

## Piper и `espeak-ng`

Голоса Piper используют `espeak-ng` для фонемизации. Установите системный пакет
на каждой машине, где настроен `tts = "piper"`:

```bash
sudo apt install espeak-ng     # Debian/Ubuntu
brew install espeak-ng         # macOS
```

Языкам с `tts = "edge"` системные пакеты не нужны вовсе.
