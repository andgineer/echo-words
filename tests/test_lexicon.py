"""The dictionary lookup: what counts as absent, and what counts as no answer."""

import httpx
import pytest

from echo_words.lexicon import Wikipedia, Wiktionary

pytestmark = pytest.mark.anyio


def responder(pages: dict[str, object]):
    """A transport answering every wiki from one script, keyed by wiki subdomain."""
    asked: list[tuple[str, str]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        wiki = request.url.host.split(".")[0]
        title = request.url.params["titles"]
        asked.append((wiki, title))
        answer = pages.get(wiki)
        if isinstance(answer, int):
            return httpx.Response(answer)
        found = bool(answer) and title in answer
        page = {"1": {"title": title}} if found else {"-1": {"missing": "", "title": title}}
        return httpx.Response(200, json={"query": {"pages": page}})

    return handle, asked


@pytest.fixture
def wiktionary(monkeypatch):
    def build(pages):
        handle, asked = responder(pages)
        original = httpx.AsyncClient

        def client(**kwargs):
            return original(transport=httpx.MockTransport(handle), **kwargs)

        monkeypatch.setattr("echo_words.lexicon.httpx.AsyncClient", client)
        return Wiktionary(), asked

    return build


async def test_a_wording_the_source_wiki_documents_is_found(languages, wiktionary):
    lookup, asked = wiktionary({"de": ["Kummerspeck"]})

    assert await lookup.documents("Kummerspeck", languages["de"]) is True
    # The English wiki is not asked once the source wiki has answered.
    assert asked == [("de", "Kummerspeck")]


async def test_the_english_wiki_covers_what_the_source_wiki_has_not(languages, wiktionary):
    """It documents every language, and the two together are what the coverage
    measurement rests on: neither wiki alone has all of the registered words."""
    lookup, asked = wiktionary({"de": [], "en": ["Kübel"]})

    assert await lookup.documents("Kübel", languages["de"]) is True
    assert [wiki for wiki, _title in asked] == ["de", "en"]


async def test_a_wording_no_wiki_documents_is_absent(languages, wiktionary):
    lookup, _asked = wiktionary({"sr": [], "en": []})

    assert await lookup.documents("змркалица", languages["sr"]) is False


async def test_an_unreachable_wiki_says_nothing_about_the_word(languages, wiktionary):
    """An absent answer is not an absent word. Reporting a miss on a service outage
    would tell the reader their real word is not one, on our own failure."""
    lookup, _asked = wiktionary({"sr": 503, "en": 503})

    assert await lookup.documents("инат", languages["sr"]) is None


async def test_one_wiki_answering_absent_and_the_other_failing_is_not_a_miss(
    languages,
    wiktionary,
):
    lookup, _asked = wiktionary({"sr": [], "en": 429})

    assert await lookup.documents("вратити се", languages["sr"]) is None


async def test_an_english_word_is_asked_of_one_wiki_only(languages, wiktionary):
    lookup, asked = wiktionary({"en": []})

    assert await lookup.documents("bookshelfy", languages["en"]) is False
    assert asked == [("en", "bookshelfy")]


async def test_a_wording_is_asked_about_once_per_process(languages, wiktionary):
    lookup, asked = wiktionary({"en": ["ledge"]})

    assert await lookup.documents("ledge", languages["en"]) is True
    assert await lookup.documents("ledge", languages["en"]) is True
    assert len(asked) == 1


async def test_an_empty_wording_is_not_asked_about(languages, wiktionary):
    lookup, asked = wiktionary({"en": []})

    assert await lookup.documents("   ", languages["en"]) is None
    assert asked == []


def encyclopedia(payload):
    """A transport answering the Wikipedia search from one scripted result."""

    def handle(_request: httpx.Request) -> httpx.Response:
        if isinstance(payload, int):
            return httpx.Response(payload)
        return httpx.Response(200, json={"query": payload})

    return handle


@pytest.fixture
def wikipedia(monkeypatch):
    def build(payload):
        original = httpx.AsyncClient

        def client(**kwargs):
            return original(transport=httpx.MockTransport(encyclopedia(payload)), **kwargs)

        monkeypatch.setattr("echo_words.lexicon.httpx.AsyncClient", client)
        return Wikipedia()

    return build


async def test_usage_reports_the_count_and_what_it_found(languages, wikipedia):
    """The count is the whole answer: every invented wording measured occurs nought
    times, and every real one at least six, so the reader can read it themselves."""
    lookup = wikipedia(
        {
            "searchinfo": {"totalhits": 249},
            "search": [{"snippet": 'неопходно је <span class="searchmatch">водити</span> рачуна'}],
        },
    )

    found = await lookup.usage("водити рачуна", languages["sr"])

    assert found.hits == 249
    # The search markup marks the match and is not ours to keep.
    assert found.examples == ["неопходно је водити рачуна"]
    assert found.search_url.startswith("https://sr.wikipedia.org/w/index.php?search=")


async def test_usage_of_a_wording_nobody_writes_is_nought(languages, wikipedia):
    lookup = wikipedia({"searchinfo": {"totalhits": 0}, "search": []})

    found = await lookup.usage("bookshelfy", languages["en"])

    assert found.hits == 0
    assert found.examples == []


async def test_an_unreachable_encyclopedia_reports_nothing(languages, wikipedia):
    """Nought occurrences and no answer read the same to a reader and mean opposite
    things, so a failed lookup must never be shown as an empty one."""
    lookup = wikipedia(429)

    assert await lookup.usage("инат", languages["sr"]) is None


async def test_an_empty_wording_is_not_searched_for(languages, wikipedia):
    lookup = wikipedia({"searchinfo": {"totalhits": 0}, "search": []})

    assert await lookup.usage("  ", languages["en"]) is None
