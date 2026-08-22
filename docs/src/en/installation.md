# Installation

Python 3.12+ and [uv](https://docs.astral.sh/uv/) are required. Node.js 22 is
needed only to build the PWA from a source checkout.

## Install `uv`

[Installing `uv`](https://docs.astral.sh/uv/getting-started/installation/)

## Install the application

```bash
uv tool install echo-words --upgrade --python 3.13
```

## Run it from a source checkout

Running from a checkout is the supported way to develop and to deploy:

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

`inv dev` serves the built bundle on <http://127.0.0.1:8080> and copies
`languages.example.toml` into place when the config file does not exist yet.

Before the first lookup succeeds you need at least one LLM provider key — see
[Configuration](configuration.md).

## Piper and `espeak-ng`

Piper voices phonemize through `espeak-ng`. Install the system package on any
machine that configures `tts = "piper"`:

```bash
sudo apt install espeak-ng     # Debian/Ubuntu
brew install espeak-ng         # macOS
```

Languages configured with `tts = "edge"` need no system package at all.
