"""What the page survives when the connection, not the model, is what fails.

Both cases live only in the browser: one is the event stream dying mid-answer and the
page having to find out what it missed, the other is a word submitted with no network
at all. Neither the Python suite nor the component suite can reach them, because
neither has a browser whose connection can be taken away.
"""

import re
import shutil
from pathlib import Path

import pytest
from e2e_app import BUILT_PWA, WORD, Gate, answer, live_app, submit
from fakes import FakeHandle
from playwright.sync_api import Page, expect

from echo_words.config import Settings

pytestmark = pytest.mark.e2e

ARTICLE = "<b>the finished analysis</b>"
RECONNECT_TIMEOUT_MS = 15_000


def test_cached_startup_shows_languages_and_history_without_downloading_them(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with live_app(settings, monkeypatch, handles=[FakeHandle([answer(ARTICLE)])]) as app:
        submit(page, app.url)
        expect(page.locator(".delete-card")).to_be_visible()
        requests = []

        def refuse_download(route):
            requests.append(route.request.url)
            route.abort()

        for endpoint in ("languages", "languages/config", "languages/catalog", "words/recent"):
            page.route(f"**/api/{endpoint}", refuse_download)
        for _ in range(2):
            page.reload()
            expect(page.locator(".entry-text")).to_contain_text("the finished analysis")
            expect(page.get_by_role("tab", name="English", exact=True)).to_be_visible()
            page.get_by_placeholder("a word or a phrase").fill("another word")
            expect(page.get_by_role("button", name="Analyse")).to_be_enabled()
        assert requests == []


def test_an_expired_language_cache_stays_visible_when_refresh_fails(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with live_app(settings, monkeypatch) as app:
        page.goto(app.url)
        expect(page.get_by_role("tab", name="English", exact=True)).to_be_visible()
        page.evaluate("() => navigator.serviceWorker.ready")
        page.wait_for_function("navigator.serviceWorker.controller !== null")
        page.evaluate("""() => new Promise((resolve, reject) => {
            const request = indexedDB.open('echo-words', 1);
            request.onsuccess = () => {
                const db = request.result;
                const tx = db.transaction('cache', 'readwrite');
                const store = tx.objectStore('cache');
                const get = store.get('/api/languages');
                get.onsuccess = () => store.put({ ...get.result, fetchedAt: 1, attemptedAt: 1 });
                tx.oncomplete = () => { db.close(); resolve(); };
                tx.onerror = () => reject(tx.error);
            };
        })""")
        page.context.set_offline(True)
        page.reload()
        expect(page.get_by_role("tab", name="English", exact=True)).to_be_visible()
        page.get_by_placeholder("a word or a phrase").fill("word")
        expect(page.get_by_role("button", name="Analyse")).to_be_enabled()
        requests = []
        page.on(
            "request",
            lambda request: (
                requests.append(request.url) if request.url.endswith("/api/languages") else None
            ),
        )
        page.reload()
        expect(page.get_by_role("tab", name="English", exact=True)).to_be_visible()
        assert requests == []


def test_the_installed_pwa_starts_offline_with_its_history_and_all_directories(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with live_app(settings, monkeypatch, handles=[FakeHandle([answer(ARTICLE)])]) as app:
        submit(page, app.url)
        expect(page.locator(".delete-card")).to_be_visible()
        page.evaluate("() => navigator.serviceWorker.ready")
        page.wait_for_function("navigator.serviceWorker.controller !== null")
        # A read transaction after the writes is a commit barrier, not a sleep.
        page.evaluate("""() => new Promise((resolve) => {
            const request = indexedDB.open('echo-words', 1);
            request.onsuccess = () => {
                const db = request.result;
                const tx = db.transaction('cache', 'readonly');
                const get = tx.objectStore('cache').getAllKeys();
                tx.oncomplete = () => { db.close(); resolve(get.result); };
            };
        })""")
        page.context.set_offline(True)
        page.reload()
        expect(page.locator(".entry-text")).to_contain_text("the finished analysis")
        expect(page.get_by_role("tab", name="English", exact=True)).to_be_visible()
        page.locator('[data-testid="edit-languages"]').click()
        expect(page.locator('[data-testid="row-en"]')).to_be_visible()
        page.locator("#new-lang").fill("Spanish")
        expect(page.locator('[data-testid="add-es"]')).to_be_visible()
        page.locator('[data-testid="open-en"]').click()
        expect(page.locator("#lang-deck")).not_to_have_value("")


def test_a_new_service_worker_and_bundle_keep_the_browser_database(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    build = tmp_path / "pwa"
    shutil.copytree(BUILT_PWA, build)
    with live_app(
        settings, monkeypatch, static_build=build, handles=[FakeHandle([answer(ARTICLE)])]
    ) as app:
        submit(page, app.url)
        expect(page.locator(".delete-card")).to_be_visible()
        page.evaluate("() => navigator.serviceWorker.ready")
        page.wait_for_function("navigator.serviceWorker.controller !== null")

        index = (build / "index.html").read_text()
        old_asset = re.search(r'src="/(assets/index-[^"]+\.js)"', index).group(1)
        new_asset = old_asset.replace(".js", "-update.js")
        (build / new_asset).write_text(
            (build / old_asset).read_text() + "\nglobalThis.updatedPwaBuild = true;\n",
        )
        (build / "index.html").write_text(index.replace(old_asset, new_asset))
        worker = (build / "sw.js").read_text().replace(old_asset, new_asset)
        worker, replaced = re.subn(
            r'url:"index.html",revision:"[^"]+"',
            'url:"index.html",revision:"test-update"',
            worker,
        )
        assert replaced == 1
        (build / "sw.js").write_text(worker)
        page.evaluate("""() => new Promise(async (resolve) => {
            navigator.serviceWorker.addEventListener('controllerchange', resolve, { once: true });
            const registration = await navigator.serviceWorker.getRegistration();
            await registration.update();
        })""")
        page.context.set_offline(True)
        page.reload()
        page.wait_for_function("globalThis.updatedPwaBuild === true")
        expect(page.locator(".entry-text")).to_contain_text("the finished analysis")
        expect(page.get_by_role("tab", name="English", exact=True)).to_be_visible()


def test_an_answer_finished_while_the_page_was_deaf_is_recovered_on_reconnect(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The event stream is the only way an answer reaches the page, and it dies with the
    connection. Everything published while it was down has to be recovered when it comes
    back, or the entry stays half-written on the screen with the work long since done."""
    gate = Gate()
    with live_app(
        settings,
        monkeypatch,
        handles=[FakeHandle([answer(ARTICLE)], hold=gate.wait)],
    ) as app:
        submit(page, app.url)
        expect(page.locator(".entry-text")).to_contain_text("the finished analysis")

        page.context.set_offline(True)
        gate.open()
        page.context.set_offline(False)

        expect(page.locator(".delete-card")).to_be_visible(timeout=RECONNECT_TIMEOUT_MS)
        expect(page.locator(".working.pending")).to_have_count(0)


def test_a_word_submitted_with_no_connection_is_sent_once_when_it_returns(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Offline the submission is kept rather than lost, and coming back online sends it.
    The pool is scripted with exactly one answer, so a resend that submitted the word
    twice would ask for a second and fail here rather than quietly double the card."""
    with live_app(settings, monkeypatch, handles=[FakeHandle([answer(ARTICLE)])]) as app:
        page.goto(app.url)
        expect(page.get_by_role("tab", name="English", exact=True)).to_be_visible()
        page.context.set_offline(True)
        page.get_by_placeholder("a word or a phrase").fill(WORD)
        page.get_by_role("button", name="Analyse").click()
        expect(page.get_by_text("the word is saved and will be sent later")).to_be_visible()

        page.context.set_offline(False)

        expect(page.locator(".entry-text")).to_contain_text(
            "the finished analysis",
            timeout=RECONNECT_TIMEOUT_MS,
        )
        articles = len(app.broker.stream_calls) - len(app.broker.attestation_calls)
        assert articles == 1


def test_a_page_reloaded_mid_answer_picks_the_entry_back_up(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A reload throws away everything the page knew and opens a new event stream onto
    an answer already half delivered. What was written so far has to come back with the
    entry, and the rest has to arrive on the new stream."""
    gate = Gate()
    with live_app(
        settings,
        monkeypatch,
        handles=[FakeHandle([answer(ARTICLE)], hold=gate.wait)],
    ) as app:
        submit(page, app.url)
        expect(page.locator(".entry-text")).to_contain_text("the finished analysis")

        page.reload()

        expect(page.locator(".entry-text")).to_contain_text("the finished analysis")
        expect(page.locator(".working.pending")).to_be_visible()

        gate.open()

        expect(page.locator(".delete-card")).to_be_visible()
        expect(page.locator(".working.pending")).to_have_count(0)


def test_a_second_page_open_on_the_same_server_is_told_the_same_answer(
    page: Page,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The event stream fans out to whoever is listening — a phone left open beside the
    laptop is the ordinary case. A page that did not submit the word still has to be
    shown it, or it sits on a rail that never moves again."""
    gate = Gate()
    with live_app(
        settings,
        monkeypatch,
        handles=[FakeHandle([answer(ARTICLE)], hold=gate.wait)],
    ) as app:
        onlooker = page.context.new_page()
        onlooker.goto(app.url)
        submit(page, app.url)
        expect(page.locator(".entry-text")).to_contain_text("the finished analysis")

        gate.open()

        expect(onlooker.locator(".entry-text")).to_contain_text("the finished analysis")
        expect(onlooker.locator(".delete-card")).to_be_visible()
        onlooker.close()
