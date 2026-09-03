"""What reference works outside the models say about a wording.

Both model tiers vouch for the same well-formed nonsense, so agreement between them
cannot separate a coinage from a word (spec/decision-llm-backend.md). Two questions
can, and neither needs a key: whether a dictionary has an entry, and whether the
wording occurs in running text at all.
"""

import logging
import re
from collections import OrderedDict
from dataclasses import dataclass
from urllib.parse import quote_plus

import httpx

from echo_words.languages import Language, other_script

# The English wiki documents every language, and the source-language wiki holds what
# it has not reached yet — `вратити се` is in the Serbian wiki and not the English one.
UNIVERSAL_WIKI = "en"
WIKTIONARY_URL = "https://{wiki}.wiktionary.org/w/api.php"
LOOKUP_TIMEOUT_SECONDS = 4.0
CACHE_LIMIT = 2048
# Wikimedia asks for a user agent that identifies the caller.
USER_AGENT = "echo-words/1 (private vocabulary assistant)"
WIKIPEDIA_URL = "https://{lang}.wikipedia.org/w/api.php"
# The reader is sent to a general web search rather than back to the encyclopedia,
# whose register carries no slang: it is the one source that just answered nought.
USAGE_SEARCH_URL = "https://duckduckgo.com/?q={query}"
USAGE_EXAMPLES = 3
_TAGS = re.compile(r"<[^>]*>")

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Usage:
    """How often a wording occurs in the encyclopedia, and where the reader can see it.

    A count rather than a judgement: the reader decides what nought occurrences means
    about a word the dictionary also lacks.
    """

    hits: int
    examples: list[str]
    search_url: str


class Wikipedia:
    """Occurrences of a wording in running text, which no dictionary can bound.

    A dictionary answers whether a word was written down; this answers whether anyone
    writes it. Measured over the registered fixtures, every invented wording occurs
    nought times and every real one at least six, colloquial and Serbian alike.
    """

    def __init__(self, timeout: float = LOOKUP_TIMEOUT_SECONDS) -> None:
        self._timeout = timeout

    async def usage(self, word: str, language: Language) -> Usage | None:
        """What the encyclopedia has, or None where the question could not be asked.

        A language written in two scripts is searched in both and the counts added:
        the search matches an exact string, so one script alone counts a fraction of
        what a wording is used in — `прозор` occurs ten times as often as `prozor`.
        """
        wording = word.strip()
        if not wording:
            return None
        found = await self._search(wording, language)
        alternate = other_script(wording, language)
        if found is None or not alternate or alternate == wording.casefold():
            return found
        also = await self._search(alternate, language)
        if also is None:
            return found
        return Usage(
            hits=found.hits + also.hits,
            examples=(found.examples + also.examples)[:USAGE_EXAMPLES],
            search_url=found.search_url,
        )

    async def _search(self, wording: str, language: Language) -> Usage | None:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                response = await client.get(
                    WIKIPEDIA_URL.format(lang=language.code),
                    params={
                        "action": "query",
                        "list": "search",
                        "srsearch": f'"{wording}"',
                        "srwhat": "text",
                        "srlimit": USAGE_EXAMPLES,
                        "format": "json",
                    },
                )
                response.raise_for_status()
                found = response.json()["query"]
        except Exception as exc:  # noqa: BLE001 - every lookup boundary degrades to unknown
            logger.warning("wikipedia lookup failed for %s/%r: %s", language.code, wording, exc)
            return None
        return Usage(
            hits=int(found.get("searchinfo", {}).get("totalhits", 0)),
            examples=[_plain(item.get("snippet", "")) for item in found.get("search", [])],
            search_url=USAGE_SEARCH_URL.format(query=quote_plus(f'"{wording}"')),
        )


def _plain(snippet: str) -> str:
    """The search fragment as text. Its markup marks the match and is not ours to keep."""
    return " ".join(_TAGS.sub("", snippet).replace("&quot;", '"').replace("&amp;", "&").split())


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
