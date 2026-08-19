"""The one ``AsyncBroker`` both cascade steps share, and the failure they map onto."""

from functools import lru_cache
from types import ModuleType
from typing import TYPE_CHECKING

from echo_words.config import Settings
from echo_words.languages import Language

if TYPE_CHECKING:
    from llmbroker import AsyncBroker

# Both providers get the functional description's complete-answer budget. A paid
# step-up may therefore take two such windows end to end, but never a separate minute.
ANSWER_BUDGET_SECONDS = 25.0


class BackendError(RuntimeError):
    """Every LLM failure the pipeline sees, whichever step and whichever cause."""


class BudgetMissError(BackendError):
    """The pool did not deliver a complete answer in time — the one step-up trigger."""


@lru_cache(maxsize=1)
def llmbroker() -> ModuleType:
    """The ``llmbroker`` module, imported at call time."""
    # Imported here rather than at module level so a missing or broken install is a
    # clear config error on the first word instead of a crash before the app serves.
    try:
        import llmbroker as module  # noqa: PLC0415
    except ImportError as exc:
        raise BackendError(f"llmbroker is not usable: {exc}") from exc
    return module


def paid_alias(language: Language, settings: Settings) -> str:
    """The paid model this language reaches, or empty when the paid step is switched off."""
    # An empty ECHOWORDS_API_MODEL switches the second step off app-wide: a language's
    # own api_model chooses which paid model answers, never whether one is paid for.
    if not settings.api_model:
        return ""
    return language.api_model or settings.api_model


def paid_aliases(languages: dict[str, Language], settings: Settings) -> list[str]:
    """Every paid alias a language can reach; llmbroker takes them at construction."""
    aliases: list[str] = []
    for language in languages.values():
        alias = paid_alias(language, settings)
        if alias and alias not in aliases:
            aliases.append(alias)
    return aliases


def create_broker(settings: Settings, languages: dict[str, Language]) -> "AsyncBroker":
    return llmbroker().AsyncBroker(
        home=settings.llmbroker_home,
        direct=paid_aliases(languages, settings),
    )
