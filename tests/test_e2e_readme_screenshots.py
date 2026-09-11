"""Every screenshot the README and the docs show is taken by one script from the built
PWA, so a change to the page can leave that script looking for something that is no
longer there, and a picture taken by hand is one nothing will ever retake."""

import importlib.util
import sys
from pathlib import Path

import pytest
from e2e_app import BUILT_PWA, REPO_ROOT
from playwright.sync_api import Browser

pytestmark = pytest.mark.e2e

_SPEC = importlib.util.spec_from_file_location(
    "capture_readme_screenshots",
    REPO_ROOT / "scripts" / "capture_readme_screenshots.py",
)
assert _SPEC and _SPEC.loader
screenshots = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = screenshots
_SPEC.loader.exec_module(screenshots)


def test_the_readme_screenshots_are_captured_from_the_built_pwa(
    browser: Browser,
    tmp_path: Path,
) -> None:
    if not (BUILT_PWA / "index.html").exists():
        pytest.fail(f"{BUILT_PWA}/index.html is missing — run `uv run inv build-static`")

    with screenshots.live_server() as url:
        screenshots.capture(browser, url, tmp_path)

    assert sorted(path.name for path in tmp_path.glob("*.png")) == sorted(
        path.name for path in screenshots.SCREENSHOTS.glob("*.png")
    )
