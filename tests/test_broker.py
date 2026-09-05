import sys

import pytest
from fakes import FakeBroker
from fastapi.testclient import TestClient
from llmbroker import AsyncResult, SchemaVersionError

from echo_words.api import create_app
from echo_words.broker import BackendError, create_broker, llmbroker, paid_aliases
from echo_words.config import Settings


def test_the_installed_llmbroker_carries_the_completed_result_seam():
    assert callable(AsyncResult.record_quality)
    assert isinstance(AsyncResult.llm_name, property)


def test_a_language_without_its_own_model_steps_up_to_the_configured_one(settings, languages):
    named = settings.model_copy(update={"api_model": "gpt-default"})
    assert paid_aliases(languages, named) == ["gpt-default", "gpt-fast"]


def test_one_alias_is_declared_once(settings: Settings, languages):
    assert paid_aliases(languages, settings) == ["gpt-fast"]


def test_no_configured_model_switches_the_paid_step_off_app_wide(settings, languages):
    paidless = settings.model_copy(update={"api_model": ""})
    assert languages["sr"].api_model == "gpt-fast"
    assert paid_aliases(languages, paidless) == []


def test_the_broker_keeps_its_state_where_the_configuration_says(settings, languages):
    broker = create_broker(settings, languages)
    assert broker.home == settings.llmbroker_home
    assert broker.direct_aliases == ["gpt-fast"]


def test_the_broker_is_built_after_the_languages_and_closed_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
):
    built: list[FakeBroker] = []

    class Recording(FakeBroker):
        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            built.append(self)

    monkeypatch.setattr("llmbroker.AsyncBroker", Recording)
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert app.state.cascade is not None
        assert app.state.cascade.broker is built[0]
        assert built[0].direct_aliases == paid_aliases(app.state.languages, settings)
        assert built[0].closed is False
    assert built[0].closed is True


def test_an_unusable_llmbroker_is_a_config_error_not_a_startup_crash(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
):
    def unusable() -> None:
        raise BackendError("llmbroker is not usable: no module named 'llmbroker'")

    monkeypatch.setattr("echo_words.broker.llmbroker", unusable)
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert app.state.cascade is None


@pytest.mark.parametrize(
    "error",
    [
        OSError("home is unreadable"),
        SchemaVersionError("bad schema", found=2, expected=1),
    ],
)
def test_any_broker_construction_failure_degrades_instead_of_crashing_startup(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    error: Exception,
):
    def broken_broker(*_args: object, **_kwargs: object) -> None:
        raise error

    monkeypatch.setattr("echo_words.api.create_broker", broken_broker)
    app = create_app(settings)
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert app.state.cascade is None


def test_a_missing_install_names_itself(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(sys.modules, "llmbroker", None)
    llmbroker.cache_clear()
    try:
        with pytest.raises(BackendError, match="llmbroker"):
            llmbroker()
    finally:
        llmbroker.cache_clear()
