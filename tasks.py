import os
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path

from invoke import task, Context, Collection
import time


DOCS_PATH = Path("docs")
DOCS_SRC_PATH = DOCS_PATH / 'src'
WEBAPP_PATH = Path("webapp")
STATIC_PATH = Path("_static")
LANGUAGES_EXAMPLE = Path("languages.example.toml")
DEFAULT_LANGUAGES_CONFIG = Path.home() / ".echo-words" / "languages.toml"


def get_allowed_doc_languages():
    """Detect languages as subfolders in docs/src/

    Ensure `en` is always first.
    """
    return ['en'] + [f.name for f in DOCS_SRC_PATH.iterdir() if f.is_dir() and f.name != "en"]


ALLOWED_DOC_LANGUAGES = get_allowed_doc_languages()
ALLOWED_VERSION_TYPES = ["release", "bug", "feature"]



@task
def version(_c: Context):
    """Show the current version."""
    with open("src/echo_words/__about__.py", "r") as f:
        version_line = f.readline()
        version_num = version_line.split('"')[1]
        print(version_num)
        return version_num


def ver_task_factory(version_type: str):
    @task
    def ver(c: Context):
        """Bump the version."""
        c.run(f"./scripts/verup.sh {version_type}")

    return ver


@task
def reqs(c: Context):
    """Upgrade requirements including pre-commit."""
    c.run("pre-commit autoupdate")
    c.run("uv lock --upgrade")
    

@contextmanager
def docs_rendered(language: str):
    """Render docs sources for language specified.

    Copy language agnostic assets from en to non-en folders.
    Substitute language and site dir in config copy.

    Returns config copy path.
    """
    config_template_path = DOCS_PATH / "mkdocs.yml"
    common_path = DOCS_PATH / "common"
    src_path = DOCS_SRC_PATH / language

    build_docs_path = Path('build') / "docs"
    build_config_path = build_docs_path / "mkdocs.yml"
    build_src_path = build_docs_path / "src" / language
    site_dir = Path("site") if language == "en" else Path("site") / language

    config = config_template_path.read_text()
    config = config.replace("LANGUAGE", language)
    config = config.replace("SITE_DIR", str(site_dir))

    build_docs_path.mkdir(parents=True, exist_ok=True)
    build_config_path.write_text(config)
    shutil.rmtree(build_src_path, ignore_errors=True)
    shutil.copytree(src_path, build_src_path)
    if common_path.is_dir():
        shutil.copytree(common_path, build_src_path, dirs_exist_ok=True)
    yield build_config_path


def docs_task_factory(language: str):
    @task
    def docs(c: Context):
        """Docs preview for the language specified."""
        with docs_rendered(language) as config_copy_path:
            port = 8001
            c.run(f"open -a 'Google Chrome' http://127.0.0.1:{port}")
            c.run(f"zensical serve --config-file {config_copy_path} --dev-addr localhost:{port}")
    return docs


@task
def build_docs(c: Context):
    """Build docs in docs/site/."""
    for language in ALLOWED_DOC_LANGUAGES:
        with docs_rendered(language) as config_copy_path:
            c.run(f"zensical build --config-file {config_copy_path}")


@task
def uv(c: Context):
    """Install or upgrade uv."""
    c.run("curl -LsSf https://astral.sh/uv/install.sh | sh")


@task
def pre(c):
    """Run pre-commit checks"""
    c.run("pre-commit run --verbose --all-files")


def _run_build(c: Context):
    if not WEBAPP_PATH.is_dir():
        raise RuntimeError(f"Cannot build the PWA: {WEBAPP_PATH}/ is missing.")

    lock = WEBAPP_PATH / "package-lock.json"
    node_lock = WEBAPP_PATH / "node_modules" / ".package-lock.json"
    needs_install = (
        not node_lock.exists()
        or not lock.exists()
        or lock.stat().st_mtime > node_lock.stat().st_mtime
    )
    if needs_install:
        c.run(f"npm --prefix {WEBAPP_PATH} ci --no-audit --no-fund")

    c.run(f"npm --prefix {WEBAPP_PATH} run build")
    index = STATIC_PATH / "index.html"
    if not index.is_file():
        raise RuntimeError(f"The Vite build did not produce {index}.")
    print(f"Built {STATIC_PATH}/")


@task(name="build-static")
def build_static(c: Context):
    """Build the Vue 3 PWA from webapp/ into _static/. Run after any webapp/ change."""
    _run_build(c)


def _ensure_languages_config():
    """Bootstrap the languages table so a fresh checkout can start the app."""
    configured = os.environ.get("ECHOWORDS_LANGUAGES_CONFIG") or DEFAULT_LANGUAGES_CONFIG
    target = Path(configured).expanduser()
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(LANGUAGES_EXAMPLE, target)
    print(f"Created {target} from {LANGUAGES_EXAMPLE} — edit it to taste.")


@task(help={"port": "TCP port to listen on (default 8080).",
            "rebuild": "Rebuild _static/ from webapp/ before starting."})
def dev(c: Context, port=8080, rebuild=False):
    """Run the web app locally with uvicorn --reload (http://127.0.0.1:<port>).

    Serves the built bundle. For frontend work with hot reload run
    `npm --prefix webapp run dev` alongside it and open port 5173,
    which proxies /api here.
    """
    _ensure_languages_config()
    if rebuild or not (STATIC_PATH / "index.html").is_file():
        _run_build(c)
    c.run(
        f"uv run uvicorn echo_words.api:app --reload --reload-dir src "
        f"--host 127.0.0.1 --port {port}",
        pty=True,
    )


@task
def test(c: Context):
    """Run the Python suite and, when webapp/ is installed, the frontend one."""
    c.run("uv run pytest", pty=True)
    if (WEBAPP_PATH / "node_modules").is_dir():
        c.run(f"npm --prefix {WEBAPP_PATH} run test")
    else:
        print(f"Skipped the frontend tests: {WEBAPP_PATH}/node_modules is missing "
              f"(inv build-static installs it).")


namespace = Collection.from_module(sys.modules[__name__])
for name in ALLOWED_VERSION_TYPES:
    namespace.add_task(ver_task_factory(name), name=f"ver-{name}")  # type: ignore[bad-argument-type]
for name in ALLOWED_DOC_LANGUAGES:
    namespace.add_task(docs_task_factory(name), name=f"docs-{name}")  # type: ignore[bad-argument-type]

