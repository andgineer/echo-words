import os
from collections.abc import Iterator
from pathlib import Path

import allure
import pytest
from fakes import FakeBroker
from fastapi.testclient import TestClient

from echo_words.api import create_app
from echo_words.config import Settings
from echo_words.languages import Language, load_languages

_VOCABULARY = "Vocabulary analysis"
_PLATFORM = "Application platform"

_DEFAULT_BEHAVIOR_BY_FILE: dict[str, tuple[str, str, str | None]] = {
    "test_anki.py": (_VOCABULARY, "Anki cards", "Headless collection"),
    "test_api.py": (_VOCABULARY, "Input and languages", None),
    "test_api_backend.py": (_VOCABULARY, "LLM cascade", "Paid attempt"),
    "test_backend.py": (_VOCABULARY, "LLM cascade", None),
    "test_broker.py": (_VOCABULARY, "LLM cascade", "Broker lifecycle"),
    "test_card.py": (_VOCABULARY, "Card extraction", "Card payload validation"),
    "test_config.py": (_PLATFORM, "Configuration and lifecycle", "Settings"),
    "test_echo_words.py": (_PLATFORM, "Configuration and lifecycle", "CLI startup"),
    "test_languages.py": (_VOCABULARY, "Input and languages", None),
    "test_llm_backend.py": (_VOCABULARY, "LLM cascade", "Free pool attempt"),
    "test_events.py": (_PLATFORM, "Answer delivery", "Event fan-out"),
    "test_pipeline.py": (_VOCABULARY, "Answer delivery", "Streaming pipeline"),
    "test_prompt.py": (_VOCABULARY, "Answer delivery", "Prompt construction"),
    "test_sanitizer.py": (_PLATFORM, "Answer delivery", "Safe answer HTML"),
}

_BEHAVIOR_BY_TEST: dict[tuple[str, str], tuple[str, str, str | None]] = {
    ("test_api.py", "test_health_answers_without_any_backend"): (
        _PLATFORM,
        "Health and deployment",
        "Health probe",
    ),
    ("test_api.py", "test_built_page_is_served_at_the_root"): (
        _PLATFORM,
        "PWA resilience",
        "PWA shell",
    ),
    ("test_api.py", "test_app_starts_without_a_built_page"): (
        _PLATFORM,
        "PWA resilience",
        "PWA shell",
    ),
    ("test_api.py", "test_missing_languages_config_stops_the_startup"): (
        _PLATFORM,
        "Configuration and lifecycle",
        "Startup validation",
    ),
}

_STORY_BY_FILE_AND_TEST: dict[tuple[str, str], str] = {
    ("test_api.py", "test_languages_feed_the_selector"): "Language selection",
    ("test_api.py", "test_accepted_submission_names_the_resolved_language"): "Word submission",
    ("test_api.py", "test_every_entry_gets_its_own_id"): "Word submission",
    ("test_api.py", "test_context_travels_with_the_word_sanitized"): "Word submission",
    ("test_api.py", "test_context_is_capped"): "Word submission",
    ("test_api.py", "test_question_mark_prefix_means_lookup_only"): "Lookup-only submission",
    ("test_api.py", "test_lookup_only_flag_is_honored"): "Lookup-only submission",
    ("test_backend.py", "test_a_completed_pool_answer_never_touches_the_paid_client"): (
        "Cascade routing"
    ),
    ("test_backend.py", "test_a_pool_that_says_nothing_in_time_steps_up_invisibly"): (
        "Paid recovery"
    ),
    ("test_backend.py", "test_a_pool_that_outlives_the_budget_steps_up_with_a_reset"): (
        "Paid recovery"
    ),
    ("test_backend.py", "test_a_fault_is_not_paid_for"): "Cascade routing",
    ("test_backend.py", "test_a_pool_configuration_fault_never_steps_up"): "Cascade routing",
    ("test_backend.py", "test_the_call_that_answered_is_the_call_that_is_rated"): (
        "Quality feedback"
    ),
    ("test_backend.py", "test_an_abandoned_stream_is_not_rated"): "Quality feedback",
    ("test_backend.py", "test_a_stepped_up_answer_does_not_rate_the_pool"): "Quality feedback",
    ("test_backend.py", "test_the_model_that_answered_is_kept_for_the_status_view"): (
        "Call status"
    ),
    ("test_backend.py", "test_the_last_call_is_kept_per_language"): "Call status",
    ("test_backend.py", "test_a_step_up_is_kept_under_the_alias_that_answered"): "Call status",
    ("test_backend.py", "test_a_failure_is_kept_too"): "Call status",
    ("test_backend.py", "test_the_language_names_which_paid_model_it_steps_up_to"): (
        "Paid recovery"
    ),
    ("test_backend.py", "test_without_a_paid_alias_a_pool_miss_is_a_failure"): ("Paid recovery"),
    ("test_backend.py", "test_without_a_paid_alias_a_deeper_analysis_is_refused"): (
        "Explicit paid requests"
    ),
    ("test_backend.py", "test_the_deeper_analysis_goes_straight_to_the_paid_model"): (
        "Explicit paid requests"
    ),
    ("test_backend.py", "test_a_step_up_spends_from_the_same_wallet_as_the_deeper_analysis"): (
        "Daily paid-call cap"
    ),
    ("test_backend.py", "test_a_pool_miss_past_the_cap_fails_instead_of_paying"): (
        "Daily paid-call cap"
    ),
    ("test_backend.py", "test_an_unlimited_cap_never_refuses"): "Daily paid-call cap",
    ("test_backend.py", "test_a_language_with_its_own_model_cannot_pay_past_the_off_switch"): (
        "Paid recovery"
    ),
    ("test_backend.py", "test_an_unresolvable_paid_alias_does_not_spend_the_wallet"): (
        "Daily paid-call cap"
    ),
    ("test_backend.py", "test_calls_today_rolls_over_in_utc_when_read"): ("Daily paid-call cap"),
}

_LANGUAGE_CONFIG_TESTS = frozenset(
    {
        "test_load_languages_indexes_by_code",
        "test_load_languages_keeps_optional_fields",
        "test_load_languages_ignores_unknown_keys",
        "test_missing_file_is_a_config_error",
        "test_broken_toml_is_a_config_error",
        "test_table_without_languages_is_a_config_error",
        "test_missing_required_field_is_a_config_error",
        "test_unknown_script_is_a_config_error",
    },
)

_NORMALIZATION_TESTS = frozenset(
    {
        "test_normalize_submission_strips_the_lookup_shortcut",
        "test_normalize_submission_composes_accents",
        "test_sanitize_context_collapses_whitespace_and_control_chars",
        "test_sanitize_context_is_capped",
    },
)

LANGUAGES_TOML = """
[languages.en]
name       = "English"
deck       = "English::Vocabulary"
dict_api   = "en"
tts        = "piper"
tts_voice  = "en_US-lessac-medium"
accent     = "us"
script     = "latin"

[languages.de]
name      = "Deutsch"
deck      = "German::Vocabulary"
dict_api  = "de"
tts       = "piper"
tts_voice = "de_DE-thorsten-medium"
script    = "latin"

[languages.sr]
name      = "Српски"
deck      = "Serbian::Vocabulary"
api_model = "gpt-fast"
tts       = "edge"
edge_tts_voice = "sr-RS-SophieNeural"
script    = "latin+cyrillic"
prompt_hints = "for nouns give gender and plural"
"""


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _allure_behavior(request: pytest.FixtureRequest) -> None:
    """Give every Python test a product behavior; an unmapped new file is an error."""
    filename = Path(request.node.path).name
    test_name = getattr(request.node, "originalname", request.node.name)
    behavior = _BEHAVIOR_BY_TEST.get((filename, test_name))
    if behavior is None:
        behavior = _DEFAULT_BEHAVIOR_BY_FILE.get(filename)
    if behavior is None:
        pytest.fail(f"Allure taxonomy is missing for {filename}::{test_name}")

    epic, feature, default_story = behavior
    story = _STORY_BY_FILE_AND_TEST.get((filename, test_name), default_story)
    if filename == "test_api.py" and story is None:
        story = "Input validation"
    elif filename == "test_languages.py":
        if test_name in _LANGUAGE_CONFIG_TESTS:
            story = "Language configuration"
        elif test_name in _NORMALIZATION_TESTS:
            story = "Input normalization"
        else:
            story = "Input validation"

    allure.dynamic.epic(epic)
    allure.dynamic.feature(feature)
    if story is not None:
        allure.dynamic.story(story)


@pytest.fixture(autouse=True)
def _no_real_broker(monkeypatch: pytest.MonkeyPatch) -> None:
    # A real AsyncBroker would refresh llmbroker's curated pool over the network.
    monkeypatch.setattr("llmbroker.AsyncBroker", FakeBroker)


@pytest.fixture(autouse=True)
def _no_ambient_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    # The suite must not inherit the developer's or the deploy box's ECHOWORDS_*.
    for name in [name for name in os.environ if name.startswith("ECHOWORDS_")]:
        monkeypatch.delenv(name)


@pytest.fixture
def languages_file(tmp_path: Path) -> Path:
    path = tmp_path / "languages.toml"
    path.write_text(LANGUAGES_TOML, encoding="utf-8")
    return path


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    path = tmp_path / "_static"
    path.mkdir()
    (path / "index.html").write_text("<!doctype html><title>echo-words</title>", encoding="utf-8")
    return path


@pytest.fixture
def settings(languages_file: Path, static_dir: Path, tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        languages_config=languages_file,
        data_dir=tmp_path / "data",
        static_dir=static_dir,
        anki_sync=False,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def languages(languages_file: Path) -> dict[str, Language]:
    return load_languages(languages_file)
