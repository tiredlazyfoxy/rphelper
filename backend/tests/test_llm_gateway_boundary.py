"""Source-level boundary checks over ``backend/app/`` for the LLM gateway.

Plan 035 (llm-client-gateway), step 005 (remove the httpx client). These tests pin
three import boundaries by reading the ``import`` / ``from ... import`` statements of
every ``.py`` file under ``backend/app/`` with ``ast`` — never by string matching, and
never by importing the modules (so ``sys.modules`` state cannot mask a violation):

- DoD-1: the old httpx client module ``app/services/llm/client.py`` is gone, and no
  module imports ``app.services.llm.client``.
- DoD-2: only ``app/services/llm/gateway.py`` imports the library package ``llm``
  (or an ``llm.`` submodule). ``llm`` is matched as the exact top-level package of an
  absolute import, so RPHelper's own ``app.services.llm`` never counts.
- DoD-3: ``httpx`` is imported only by the ``web_search`` provider package
  (``app/services/web_search/``).
"""

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

#: ``backend/`` — module dotted names are computed relative to this directory.
BACKEND_DIRECTORY = Path(__file__).resolve().parent.parent
#: ``backend/app/`` — the scan root for every boundary check.
APP_DIRECTORY = BACKEND_DIRECTORY / "app"

CLIENT_MODULE = "app.services.llm.client"
CLIENT_FILE = APP_DIRECTORY / "services" / "llm" / "client.py"
GATEWAY_FILE = APP_DIRECTORY / "services" / "llm" / "gateway.py"
WEB_SEARCH_DIRECTORY = APP_DIRECTORY / "services" / "web_search"


def _module_name(path: Path) -> str:
    """The dotted module name of a file under ``backend/`` (``__init__.py`` names its package)."""
    parts = list(path.relative_to(BACKEND_DIRECTORY).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _package_parts(path: Path) -> list[str]:
    """The package a file's relative imports resolve against."""
    parts = _module_name(path).split(".")
    return parts if path.name == "__init__.py" else parts[:-1]


def imported_modules(source: str, path: Path) -> set[str]:
    """Every absolute module name an import statement in ``source`` can bind.

    ``import a.b`` yields ``a.b``; ``from a.b import c`` yields ``a.b`` and ``a.b.c`` (``c``
    may be a submodule). Relative imports are resolved against the file's package, so
    ``from . import client`` inside ``app/services/llm/`` yields ``app.services.llm.client``.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
            else:
                package = _package_parts(path)
                keep = len(package) - (node.level - 1)
                base_parts = package[:keep] if keep > 0 else []
                if node.module:
                    base_parts = [*base_parts, *node.module.split(".")]
                base = ".".join(base_parts)
            if base:
                found.add(base)
            found.update(f"{base}.{alias.name}" if base else alias.name for alias in node.names)
    return found


def absolute_import_roots(source: str) -> set[str]:
    """The top-level package of every *absolute* import in ``source``.

    Relative imports are skipped: they always name RPHelper's own ``app`` package, never a
    third-party library, so ``from . import llm``-style statements cannot count as ``llm``.
    """
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module is not None:
            roots.add(node.module.split(".")[0])
    return roots


def app_python_files() -> Iterator[Path]:
    """Every ``.py`` file under ``backend/app/``, in a stable order."""
    yield from sorted(APP_DIRECTORY.rglob("*.py"))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _relative(path: Path) -> str:
    return path.relative_to(BACKEND_DIRECTORY).as_posix()


# --- scanner sanity (keeps the boundary checks below from passing vacuously) ---------------


def test_app_scan_finds_python_files__S035_005_DoD1_DoD2_DoD3() -> None:
    """The scan root exists and holds modules, so an empty walk cannot pass the checks."""
    files = list(app_python_files())
    assert files, "no .py files found under backend/app/"
    assert GATEWAY_FILE in files


@pytest.mark.parametrize(
    "source",
    [
        "import llm",
        "import llm.tools",
        "from llm import LLMClient",
        "from llm.openai import OpenAIAPIClient",
        "import os, llm",
    ],
)
def test_root_scan_detects_the_library_package__S035_005_DoD2(source: str) -> None:
    """Every import form of the ``llm`` library is seen as top-level package ``llm``."""
    assert "llm" in absolute_import_roots(source)


@pytest.mark.parametrize(
    "source",
    [
        "import app.services.llm",
        "import app.services.llm.gateway",
        "from app.services.llm import gateway",
        "from app.services.llm.chat import ChatMessage",
        "from . import llm",
        "from .llm import chat",
        "import llm_tools",
        "from llmish import x",
    ],
)
def test_root_scan_ignores_rphelpers_own_llm_package__S035_005_DoD2(source: str) -> None:
    """``app.services.llm``, relative imports and look-alike names never count as ``llm``."""
    assert "llm" not in absolute_import_roots(source)


@pytest.mark.parametrize(
    ("source", "relative_path"),
    [
        ("import app.services.llm.client", "app/services/compose.py"),
        ("from app.services.llm.client import ProbeOutcome", "app/services/compose.py"),
        ("from app.services.llm import client", "app/services/compose.py"),
        ("from .client import ProbeOutcome", "app/services/llm/gateway.py"),
        ("from . import client", "app/services/llm/gateway.py"),
        ("from .llm.client import ProbeOutcome", "app/services/compose.py"),
        ("from ..llm import client", "app/services/search/vector.py"),
        ("from .services.llm.client import X", "app/__init__.py"),
    ],
)
def test_module_scan_detects_every_client_import_form__S035_005_DoD1(source: str, relative_path: str) -> None:
    """Absolute, from-package and relative imports of the client all resolve to its name."""
    assert CLIENT_MODULE in imported_modules(source, BACKEND_DIRECTORY / relative_path)


def test_module_scan_does_not_flag_sibling_modules__S035_005_DoD1() -> None:
    """Importing the gateway or chat module is not an import of the client."""
    source = "from app.services.llm.gateway import LlmGateway\nfrom . import chat\n"
    assert CLIENT_MODULE not in imported_modules(source, GATEWAY_FILE)


# --- DoD-1: the httpx client module is gone ------------------------------------------------


def test_client_module_file_does_not_exist__S035_005_DoD1() -> None:
    """``app/services/llm/client.py`` has been deleted."""
    assert not CLIENT_FILE.exists(), f"{_relative(CLIENT_FILE)} still exists"


def test_no_app_module_imports_the_client_module__S035_005_DoD1() -> None:
    """No module under ``backend/app/`` imports ``app.services.llm.client`` in any form."""
    offenders = [
        _relative(path) for path in app_python_files() if CLIENT_MODULE in imported_modules(_read(path), path)
    ]
    assert offenders == [], f"modules still importing {CLIENT_MODULE}: {offenders}"


# --- DoD-2: only the gateway imports the library -------------------------------------------


def test_only_the_gateway_imports_the_llm_library__S035_005_DoD2() -> None:
    """The set of ``backend/app/`` modules importing ``llm`` / ``llm.*`` is exactly the gateway."""
    importers = {_relative(path) for path in app_python_files() if "llm" in absolute_import_roots(_read(path))}
    assert importers == {_relative(GATEWAY_FILE)}


# --- DoD-3: httpx only in the web_search provider package ----------------------------------


def test_httpx_is_imported_only_by_the_web_search_package__S035_005_DoD3() -> None:
    """Every ``backend/app/`` module importing ``httpx`` lives under ``app/services/web_search/``."""
    offenders = [
        _relative(path)
        for path in app_python_files()
        if "httpx" in absolute_import_roots(_read(path)) and not path.is_relative_to(WEB_SEARCH_DIRECTORY)
    ]
    assert offenders == [], f"modules outside app/services/web_search/ importing httpx: {offenders}"


@pytest.mark.parametrize("source", ["import httpx", "from httpx import AsyncClient", "import httpx._client"])
def test_root_scan_detects_httpx__S035_005_DoD3(source: str) -> None:
    """Every import form of ``httpx`` is seen as top-level package ``httpx``."""
    assert "httpx" in absolute_import_roots(source)
