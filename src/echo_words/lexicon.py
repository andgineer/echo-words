"""Whether any dictionary documents a wording at all, asked outside the models.

Both model tiers vouch for the same well-formed nonsense, so agreement between them
cannot separate a coinage from a word (spec/decision-llm-backend.md). Wiktionary can,
and it is the only free source measured to cover all three languages.
"""

import logging
from collections import OrderedDict

import httpx

from echo_words.languages import Language

# The English wiki documents every language, and the source-language wiki holds what
# it has not reached yet — `вратити се` is in the Serbian wiki and not the English one.
UNIVERSAL_WIKI = "en"
WIKTIONARY_URL = "https://{wiki}.wiktionary.org/w/api.php"
LOOKUP_TIMEOUT_SECONDS = 4.0
CACHE_LIMIT = 2048
# Wikimedia asks for a user agent that identifies the caller.
USER_AGENT = "echo-words/1 (private vocabulary assistant)"

logger = logging.getLogger(__name__)


class Wiktionary:
    """The lookup and its cache, kept together so a process asks each wording once."""

    def __init__(self, timeout: float = LOOKUP_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout
        self._known: OrderedDict[tuple[str, str], bool] = OrderedDict()

    async def documents(self, word: str, language: Language) -> bool | None:
        """True where a wiki has the wording, False where none has it, None where the
        question could not be asked — an unreachable service is not evidence."""
        wording = word.strip()
        if not wording:
            return None
        wikis = [language.code]
        if language.code != UNIVERSAL_WIKI:
            wikis.append(UNIVERSAL_WIKI)
        unknown = False
        async with httpx.AsyncClient(
            timeout=self._timeout,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            for wiki in wikis:
                found = await self._in_wiki(client, wiki, wording)
                if found:
                    return True
                unknown = unknown or found is None
        return None if unknown else False

    async def _in_wiki(self, client: httpx.AsyncClient, wiki: str, wording: str) -> bool | None:
        cached = self._known.get((wiki, wording))
        if cached is not None:
            self._known.move_to_end((wiki, wording))
            return cached
        try:
            response = await client.get(
                WIKTIONARY_URL.format(wiki=wiki),
                params={
                    "action": "query",
                    "titles": wording,
                    "format": "json",
                    "redirects": "1",
                },
            )
            response.raise_for_status()
            pages = response.json()["query"]["pages"]
        except Exception as exc:  # noqa: BLE001 - every lookup boundary degrades to unknown
            logger.warning("wiktionary lookup failed for %s/%r: %s", wiki, wording, exc)
            return None
        found = any("missing" not in page for page in pages.values())
        self._known[wiki, wording] = found
        if len(self._known) > CACHE_LIMIT:
            self._known.popitem(last=False)
        return found
