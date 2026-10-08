"""File-contract tests for the deployment harness (fast/001.dev-and-container-harness).

Every assertion is derived from the plan's Definition of done, its Interface intent and
``docs/architecture/deployment.md`` (authoritative for directive values). The artifacts are
read as plain text from the repo root; nothing is executed. Live behaviour (DoD-16..19) is
the verifier's requires-live-run record, and DoD-15 (ruff clean) is a verifier gate.

Retargeted by fast/013.build-and-deploy-scripts (its DoD-22..25, tagged ``f013``): the prod
compose now lives in ``docker-compose.prod.yml`` (image-based), the dev compose took the
standard ``docker-compose.yml`` name, and ``build.sh`` / ``deploy.sh`` joined the deployment
files. The fast/001 compose checks (DoD-10) now run against ``docker-compose.prod.yml``.
"""

import configparser
import re
from pathlib import Path

import pytest
from pydantic import AliasChoices, AliasPath

from app.config import Settings

# Repo root = the test file's grandparent's parent (backend/tests/<file> -> repo root).
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

PROD_COMPOSE = "docker-compose.prod.yml"
DEV_COMPOSE = "docker-compose.yml"
# The retired dev compose name, split so a repo-wide grep for it (fast/013 DoD-27) stays clean.
OLD_DEV_COMPOSE = "docker-compose" + ".dev.yml"

SOURCE_FILES = (
    "start.ps1",
    "Dockerfile",
    DEV_COMPOSE,
    PROD_COMPOSE,
    "build.sh",
    "deploy.sh",
    "docker/nginx.conf",
    "docker/nginx.dev.conf",
    "docker/supervisord.conf",
    ".env.example",
    ".dockerignore",
    ".gitignore",
    "backend/.gitignore",
)

SCRIPTS = ("build.sh", "deploy.sh")

PROD_NGINX = "docker/nginx.conf"
DEV_NGINX = "docker/nginx.dev.conf"
NGINX_CONFIGS = (PROD_NGINX, DEV_NGINX)

PROD_UPSTREAM = "http://127.0.0.1:8184/api/"
DEV_UPSTREAM = "http://host.docker.internal:8184/api/"

HASHED_ASSET_CACHE = '"public, max-age=31536000, immutable"'
INDEX_NO_CACHE = '"no-cache"'

FORBIDDEN_LOG_VARIABLES = re.compile(r"\$(?:args|query_string|request_uri|request)(?![A-Za-z0-9_])")


# --- helpers -------------------------------------------------------------------------


def read_text(relative: str) -> str:
    path = REPO_ROOT / relative
    assert path.is_file(), f"{relative} is missing at the repo root"
    return path.read_text(encoding="utf-8")


def squash(text: str) -> str:
    """Collapse every whitespace run to a single space and trim."""
    return re.sub(r"\s+", " ", text).strip()


def strip_hash_comments(text: str) -> str:
    """Drop ``#`` comments (nginx / YAML / Dockerfile style) up to end of line."""
    return re.sub(r"#[^\n]*", "", text)


def nginx_text(relative: str) -> str:
    return strip_hash_comments(read_text(relative))


def balanced_block(text: str, open_index: int, opener: str = "{", closer: str = "}") -> str:
    """Return the text between the opener at ``open_index`` and its matching closer."""
    assert text[open_index] == opener
    depth = 0
    for index in range(open_index, len(text)):
        char = text[index]
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[open_index + 1 : index]
    raise AssertionError("unbalanced block")


def location_blocks(text: str) -> list[tuple[str, str]]:
    """Every ``location <spec> { body }`` as ``(squashed spec, body)``."""
    blocks: list[tuple[str, str]] = []
    for match in re.finditer(r"\blocation\s+([^{;]*?)\s*\{", text):
        body = balanced_block(text, match.end() - 1)
        blocks.append((squash(match.group(1)), body))
    return blocks


def find_location(text: str, spec: str) -> str | None:
    """Body of the location whose spec equals ``spec``, ignoring whitespace (`=/x` == `= /x`)."""
    for found_spec, body in location_blocks(text):
        if found_spec.replace(" ", "") == spec.replace(" ", ""):
            return body
    return None


def api_block(text: str) -> str:
    body = find_location(text, "^~ /api/")
    assert body is not None, "no `location ^~ /api/` block"
    return body


def cache_block(text: str, marker: str) -> tuple[str, str]:
    """The regex location (``~`` / ``~*``) whose body carries ``marker``."""
    matches = [
        (spec, body) for spec, body in location_blocks(text) if spec.startswith("~") and marker in squash(body)
    ]
    assert len(matches) == 1, f"expected exactly one regex location carrying {marker}, found {len(matches)}"
    return matches[0]


def statements(text: str, keyword: str) -> list[str]:
    """Every ``<keyword> ... ;`` statement, whitespace-squashed."""
    return [squash(m.group(0)) for m in re.finditer(rf"(?<![\w$]){keyword}\s[^;]*;", text)]


def try_files_fallback(body: str) -> str:
    """The final argument of the block's ``try_files`` directive."""
    found = re.findall(r"\btry_files\s+([^;]*);", body)
    assert len(found) == 1, f"expected one try_files directive, found {len(found)}"
    return found[0].split()[-1]


# --- DoD-1 ---------------------------------------------------------------------------


@pytest.mark.parametrize("relative", SOURCE_FILES)
def test_dod1_source_file_exists(relative: str) -> None:
    # DoD-1: every Source file exists at its repo-root path.
    assert (REPO_ROOT / relative).is_file(), f"{relative} does not exist"


# --- DoD-2 / DoD-3 -------------------------------------------------------------------


@pytest.mark.parametrize("relative", NGINX_CONFIGS)
def test_dod2_api_block_carries_streaming_body_and_header_directives(relative: str) -> None:
    # DoD-2: the `location ^~ /api/` block holds every directive from deployment.md :348-363.
    body = squash(api_block(nginx_text(relative)))
    required = (
        r"proxy_http_version 1\.1;",
        r"proxy_set_header Connection (?:''|\"\");",
        r"proxy_buffering off;",
        r"proxy_cache off;",
        r"proxy_read_timeout 300s;",
        r"client_max_body_size 64m;",
        r"proxy_set_header Host \$host;",
        r"proxy_set_header X-Real-IP \$remote_addr;",
        r"proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;",
    )
    for pattern in required:
        assert re.search(pattern, body), f"{relative} /api/ block lacks `{pattern}`"


@pytest.mark.parametrize(("relative", "upstream"), [(PROD_NGINX, PROD_UPSTREAM), (DEV_NGINX, DEV_UPSTREAM)])
def test_dod3_api_block_proxies_to_the_right_upstream(relative: str, upstream: str) -> None:
    # DoD-3: prod -> 127.0.0.1:8184/api/, dev -> host.docker.internal:8184/api/.
    body = squash(api_block(nginx_text(relative)))
    passes = re.findall(r"proxy_pass (\S+);", body)
    assert passes == [upstream]


# --- DoD-4 ---------------------------------------------------------------------------


def test_dod4_api_block_identical_once_upstream_normalised() -> None:
    # DoD-4: the /api/ bodies match byte-for-byte (modulo whitespace) after host normalisation.
    prod = squash(api_block(nginx_text(PROD_NGINX)))
    dev = squash(api_block(nginx_text(DEV_NGINX))).replace("host.docker.internal:8184", "127.0.0.1:8184")
    assert prod == dev


@pytest.mark.parametrize("marker", [HASHED_ASSET_CACHE, INDEX_NO_CACHE])
def test_dod4_cache_blocks_identical(marker: str) -> None:
    # DoD-4: both cache-control location blocks are identical in the two configs.
    prod_spec, prod_body = cache_block(nginx_text(PROD_NGINX), marker)
    dev_spec, dev_body = cache_block(nginx_text(DEV_NGINX), marker)
    assert prod_spec == dev_spec
    assert squash(prod_body) == squash(dev_body)


@pytest.mark.parametrize("keyword", ["log_format", "access_log"])
def test_dod4_log_lines_identical(keyword: str) -> None:
    # DoD-4: the log_format line and the access_log line are identical in the two configs.
    prod = statements(nginx_text(PROD_NGINX), keyword)
    dev = statements(nginx_text(DEV_NGINX), keyword)
    assert prod, f"prod config has no {keyword}"
    assert prod == dev


# --- DoD-5 ---------------------------------------------------------------------------


@pytest.mark.parametrize("relative", NGINX_CONFIGS)
def test_dod5_cache_control_blocks_present(relative: str) -> None:
    # DoD-5: hashed-asset immutable cache block and index.html no-cache block (deployment.md :434-441).
    text = nginx_text(relative)
    asset_spec, asset_body = cache_block(text, HASHED_ASSET_CACHE)
    assert re.search(r"add_header Cache-Control \"public, max-age=31536000, immutable\";", squash(asset_body))
    for extension in ("js", "css", "woff2?", "png", "svg", "jpg", "webp"):
        assert extension in asset_spec, f"{relative} asset cache regex misses {extension}"

    index_spec, index_body = cache_block(text, INDEX_NO_CACHE)
    assert re.search(r"add_header Cache-Control \"no-cache\";", squash(index_body))
    assert "index" in index_spec and "html" in index_spec


# --- DoD-6 ---------------------------------------------------------------------------


@pytest.mark.parametrize("relative", NGINX_CONFIGS)
def test_dod6_path_only_access_log(relative: str) -> None:
    # DoD-6: a named log_format built on $uri, no query-bearing variables, used by access_log.
    text = nginx_text(relative)
    formats = statements(text, "log_format")
    access = statements(text, "access_log")
    assert formats, f"{relative} declares no log_format"
    assert access, f"{relative} declares no access_log"

    for line in formats + access:
        assert not FORBIDDEN_LOG_VARIABLES.search(line), f"{relative} logs a query-bearing variable: {line}"

    uri_formats = {line.split()[1] for line in formats if re.search(r"\$uri(?![A-Za-z0-9_])", line)}
    assert uri_formats, f"{relative} has no log_format containing $uri"

    for line in access:
        tokens = line.rstrip(";").split()
        assert len(tokens) >= 3, f"{relative} access_log names no format: {line}"
        assert tokens[1] == "/dev/stdout", f"{relative} access_log does not go to stdout: {line}"
        assert tokens[2] in uri_formats, f"{relative} access_log does not use the path-only format: {line}"


def server_block_span(text: str) -> tuple[int, int]:
    """``(start, end)`` of the single ``server { ... }`` block, braces included."""
    matches = list(re.finditer(r"(?<![\w$])server\s*\{", text))
    assert len(matches) == 1, f"expected exactly one server block, found {len(matches)}"
    open_index = matches[0].end() - 1
    body = balanced_block(text, open_index)
    return matches[0].start(), open_index + len(body) + 2


def without_location_bodies(text: str) -> str:
    """``text`` with every ``location ... { body }`` removed (outermost blocks)."""
    result: list[str] = []
    cursor = 0
    for match in re.finditer(r"\blocation\s+[^{;]*?\s*\{", text):
        if match.start() < cursor:
            continue  # nested inside a block already removed
        body = balanced_block(text, match.end() - 1)
        result.append(text[cursor : match.start()])
        cursor = match.end() + len(body) + 1
    result.append(text[cursor:])
    return "".join(result)


@pytest.mark.parametrize("relative", NGINX_CONFIGS)
def test_dod6_access_log_not_at_file_top_level(relative: str) -> None:
    # DoD-6 (amended): no access_log at file top level (http context) -- only inside the server block.
    text = nginx_text(relative)
    start, end = server_block_span(text)
    top_level = text[:start] + text[end:]
    assert not statements(top_level, "access_log"), f"{relative} declares access_log at file top level"


@pytest.mark.parametrize("relative", NGINX_CONFIGS)
def test_dod6_access_log_declared_at_server_level(relative: str) -> None:
    # DoD-6 (amended): the access_log directive sits directly inside `server { ... }` (not in a location).
    text = nginx_text(relative)
    start, end = server_block_span(text)
    server_level = without_location_bodies(text[start:end])
    assert statements(server_level, "access_log"), f"{relative} has no server-level access_log"


@pytest.mark.parametrize("relative", NGINX_CONFIGS)
def test_dod6_no_location_declares_access_log(relative: str) -> None:
    # DoD-6 (amended) / Interface intent: no location block declares its own access_log.
    offenders = [spec for spec, body in location_blocks(nginx_text(relative)) if statements(body, "access_log")]
    assert not offenders, f"{relative} declares access_log in location(s) {offenders}"


def test_dod6_dockerfile_does_not_touch_main_nginx_conf() -> None:
    # DoD-6 (amended): the Dockerfile contains no reference to /etc/nginx/nginx.conf.
    assert "/etc/nginx/nginx.conf" not in read_text("Dockerfile")


# --- DoD-7 ---------------------------------------------------------------------------


@pytest.mark.parametrize("relative", NGINX_CONFIGS)
@pytest.mark.parametrize("entry", ["bootstrap", "login", "admin"])
def test_dod7_entry_prefix_falls_back_to_own_index(relative: str, entry: str) -> None:
    # DoD-7: /bootstrap/, /login/, /admin/ each fall back to their own index.html.
    body = find_location(nginx_text(relative), f"/{entry}/")
    assert body is not None, f"{relative} has no `location /{entry}/`"
    assert try_files_fallback(body) == f"/{entry}/index.html"


@pytest.mark.parametrize("relative", NGINX_CONFIGS)
def test_dod7_no_app_prefix_location(relative: str) -> None:
    # DoD-7: neither config contains `location /app/`.
    specs = [spec for spec, _ in location_blocks(nginx_text(relative))]
    assert all(not re.fullmatch(r"(?:\^~)?/app/", spec.replace(" ", "")) for spec in specs), specs


@pytest.mark.parametrize("relative", NGINX_CONFIGS)
@pytest.mark.parametrize("entry", ["login", "bootstrap", "admin"])
def test_dod7_slashless_entry_redirects_302_to_slash_form(relative: str, entry: str) -> None:
    # DoD-7 (`= /login`), plus the same rule for `= /bootstrap` / `= /admin` from Interface intent.
    body = find_location(nginx_text(relative), f"= /{entry}")
    assert body is not None, f"{relative} has no `location = /{entry}`"
    assert re.search(rf"\breturn 302 /{entry}/;", squash(body)), f"{relative} `= /{entry}` is not a relative 302"


@pytest.mark.parametrize("relative", NGINX_CONFIGS)
def test_dod7_absolute_redirect_off(relative: str) -> None:
    # DoD-7: both configs set `absolute_redirect off`.
    assert re.search(r"\babsolute_redirect\s+off\s*;", nginx_text(relative))


# --- DoD-8 ---------------------------------------------------------------------------


@pytest.mark.parametrize(("relative", "fallback"), [(PROD_NGINX, "/index.html"), (DEV_NGINX, "/app/index.html")])
def test_dod8_catch_all_fallback(relative: str, fallback: str) -> None:
    # DoD-8: prod catch-all -> /index.html; dev catch-all -> /app/index.html.
    body = find_location(nginx_text(relative), "/")
    assert body is not None, f"{relative} has no catch-all `location /`"
    assert try_files_fallback(body) == fallback


# --- DoD-9 ---------------------------------------------------------------------------


def load_supervisord() -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.read_string(read_text("docker/supervisord.conf"))
    return parser


def program_commands(parser: configparser.ConfigParser) -> dict[str, str]:
    return {
        section: parser.get(section, "command", fallback="")
        for section in parser.sections()
        if section.startswith("program:")
    }


def test_dod9_supervisord_nodaemon() -> None:
    # DoD-9: `[supervisord]` has nodaemon=true.
    parser = load_supervisord()
    assert parser.has_section("supervisord")
    assert parser.get("supervisord", "nodaemon", fallback="").strip().lower() == "true"


def test_dod9_exactly_one_uvicorn_on_loopback_8184() -> None:
    # DoD-9: exactly one program runs uvicorn, bound to 127.0.0.1:8184, no --workers, no --reload.
    parser = load_supervisord()
    uvicorn = {name: cmd for name, cmd in program_commands(parser).items() if "uvicorn" in cmd}
    assert len(uvicorn) == 1, f"expected exactly one uvicorn program, found {sorted(uvicorn)}"
    section, command = next(iter(uvicorn.items()))
    assert re.search(r"--host[ =]127\.0\.0\.1(?![\d.])", command), command
    assert re.search(r"--port[ =]8184(?!\d)", command), command
    assert "app.main:app" in command
    assert "--workers" not in command
    assert "--reload" not in command
    assert parser.get(section, "directory", fallback="").strip() == "/app"


def test_dod9_nginx_program_in_foreground() -> None:
    # DoD-9: a program runs nginx with `daemon off`.
    commands = program_commands(load_supervisord())
    nginx = [cmd for cmd in commands.values() if "nginx" in cmd and "uvicorn" not in cmd]
    assert len(nginx) == 1, f"expected one nginx program, found {len(nginx)}"
    assert re.search(r"daemon\s+off", nginx[0]), nginx[0]


# --- DoD-10 --------------------------------------------------------------------------


def compose_text() -> str:
    # fast/013 DoD-22: the prod compose moved to docker-compose.prod.yml.
    return strip_hash_comments(read_text(PROD_COMPOSE))


def healthcheck_block(text: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^(\s*)healthcheck:\s*(.*)$", line)
        if match:
            indent = len(match.group(1))
            block = [match.group(2)]
            for follower in lines[index + 1 :]:
                if follower.strip() and len(follower) - len(follower.lstrip()) <= indent:
                    break
                block.append(follower)
            return "\n".join(block)
    raise AssertionError(f"{PROD_COMPOSE} has no healthcheck")


def test_dod10_compose_ports_env_volume_restart() -> None:
    # DoD-10: publishes 8193:80, env_file .env, ./data:/app/data, restart unless-stopped.
    text = compose_text()
    assert re.search(r"(?<![\d])8193:80(?!\d)", text)
    assert re.search(r"env_file:\s*(?:\[\s*)?(?:-\s*)?[\"']?\.env(?![\w.])", text)
    assert re.search(r"(?<![\w.])\./data:/app/data(?![\w/])", text)
    assert re.search(r"restart:\s*[\"']?unless-stopped", text)


def test_dod10_healthcheck_curl_status_only() -> None:
    # DoD-10: healthcheck runs `curl -f http://localhost/api/health` and never inspects the body.
    block = healthcheck_block(compose_text())
    assert "curl" in block
    assert re.search(r"(?<![\w-])-f(?![\w-])", block)
    assert "http://localhost/api/health" in block
    assert "grep" not in block
    assert "jq" not in block
    assert '"status"' not in block
    assert not re.search(r"\bok\b", block, re.IGNORECASE)


# --- DoD-11 --------------------------------------------------------------------------


def dockerfile_stages() -> list[str]:
    text = strip_hash_comments(read_text("Dockerfile"))
    text = re.sub(r"\\\r?\n", " ", text)  # join line continuations
    parts = re.split(r"(?im)^\s*(?=FROM\s)", text)
    return [part for part in parts if re.match(r"(?i)FROM\s", part)]


def test_dod11_two_stages_runtime_python_slim() -> None:
    # DoD-11: two FROM stages; the runtime (last) one is python:3.12-slim.
    stages = dockerfile_stages()
    assert len(stages) == 2, f"expected two FROM stages, found {len(stages)}"
    assert "python:3.12-slim" in stages[-1].splitlines()[0]


def test_dod11_runtime_installs_uv_locked_backend_and_curl() -> None:
    # DoD-11: runtime runs `uv sync --frozen --no-dev` and installs curl (and nginx, supervisor).
    runtime = dockerfile_stages()[-1]
    syncs = re.findall(r"\buv sync\b[^\n]*", runtime)
    assert any("--frozen" in s and "--no-dev" in s for s in syncs), syncs
    installs = re.findall(r"\bapt(?:-get)? install\b[^\n]*", runtime)
    for package in ("curl", "nginx", "supervisor"):
        assert any(re.search(rf"(?<![\w-]){package}(?![\w-])", line) for line in installs), package


def test_dod11_frontend_stage_checks_four_entries_and_copies_root_document() -> None:
    # DoD-11: fail-fast check references all four dist/<entry>/index.html; app/index.html -> root index.html.
    text = read_text("Dockerfile")
    for entry in ("bootstrap", "login", "admin", "app"):
        assert f"dist/{entry}/index.html" in text, f"Dockerfile never references dist/{entry}/index.html"
    copies = re.findall(r"\bapp/index\.html[\"']?\s+[\"']?(\S*?)index\.html", text)
    entry_dir = re.compile(r"(?:bootstrap|login|admin|app)/$")
    root_copies = [dest for dest in copies if not entry_dir.search(dest)]
    assert root_copies, "app/index.html is never copied to a root index.html"


# --- DoD-12 --------------------------------------------------------------------------


def start_script_params() -> dict[str, str]:
    """Map each param-block variable (lower-cased) to the attribute text preceding it."""
    text = read_text("start.ps1")
    match = re.search(r"(?i)\bparam\s*\(", text)
    assert match, "start.ps1 has no param() block"
    block = balanced_block(text, match.end() - 1, "(", ")")
    params: dict[str, str] = {}
    previous = 0
    for var in re.finditer(r"\$(\w+)", block):
        params.setdefault(var.group(1).lower(), block[previous : var.start()])
        previous = var.end()
    return params


@pytest.mark.parametrize(("name", "alias"), [("app", "api"), ("ui", "web")])
def test_dod12_start_script_switch_parameters(name: str, alias: str) -> None:
    # DoD-12: `-app` (alias `-api`) and `-ui` (alias `-web`) switch parameters.
    params = start_script_params()
    assert name in params, f"start.ps1 declares no ${name} parameter"
    prefix = params[name]
    assert re.search(r"(?i)\[switch\]", prefix), f"${name} is not a switch"
    assert re.search(rf"(?i)alias\s*\([^)]*[\"']{alias}[\"']", prefix), f"${name} lacks alias {alias}"


def test_dod12_start_script_literals() -> None:
    # DoD-12: uvicorn and vite launch literals.
    text = read_text("start.ps1")
    for literal in ("--port 8184", "--host 127.0.0.1", "--reload", "app.main:app", ".venv/Scripts/python"):
        assert literal in text, f"start.ps1 lacks `{literal}`"
    assert "--port 8193" in text
    assert "vite" in text


# --- DoD-13 --------------------------------------------------------------------------


def settings_aliases() -> set[str]:
    aliases: set[str] = set()
    for name, field in Settings.model_fields.items():
        found: set[str] = set()
        candidates: list[object] = [field.validation_alias, field.alias]
        for candidate in candidates:
            if isinstance(candidate, str):
                found.add(candidate)
            elif isinstance(candidate, AliasChoices):
                for choice in candidate.choices:
                    if isinstance(choice, str):
                        found.add(choice)
                    elif isinstance(choice, AliasPath) and isinstance(choice.path[0], str):
                        found.add(choice.path[0])
            elif isinstance(candidate, AliasPath) and isinstance(candidate.path[0], str):
                found.add(candidate.path[0])
        aliases |= found or {name.upper()}
    return aliases


def test_dod13_env_example_mentions_every_settings_alias() -> None:
    # DoD-13: every validation alias of every Settings field appears in .env.example.
    text = read_text(".env.example")
    aliases = settings_aliases()
    assert aliases, "Settings exposes no fields"
    missing = sorted(
        alias for alias in aliases if not re.search(rf"(?<![A-Za-z0-9_]){re.escape(alias)}(?![A-Za-z0-9_])", text)
    )
    assert not missing, f".env.example misses {missing}"


@pytest.mark.parametrize("name", ["SEARCH_CSE_KEY", "SEARCH_CSE_ID"])
def test_dod13_env_example_mentions_unprefixed_search_credentials(name: str) -> None:
    # DoD-13: the two unprefixed search credentials are included.
    assert re.search(rf"(?<![A-Za-z0-9_]){name}(?![A-Za-z0-9_])", read_text(".env.example"))


# --- DoD-14 --------------------------------------------------------------------------


@pytest.mark.parametrize("name", [".venv", "node_modules", "dist", "data", ".git"])
def test_dod14_dockerignore_excludes(name: str) -> None:
    # DoD-14: .dockerignore excludes .venv, node_modules, dist, data and .git.
    patterns = [
        line.strip()
        for line in read_text(".dockerignore").splitlines()
        if line.strip() and not line.strip().startswith(("#", "!"))
    ]
    excluded = {p.rstrip("/").split("/")[-1] for p in patterns}
    assert name in excluded, f".dockerignore does not exclude {name}"


def test_dod14_gitignore_drops_bookwriter_sink() -> None:
    # DoD-14: .gitignore no longer contains BOOKWRITER (and the dead /logs/ entry is gone, per Interface intent).
    text = read_text(".gitignore")
    assert "BOOKWRITER" not in text
    assert "/logs/" not in [line.strip() for line in text.splitlines()]


# --- fast/013 DoD-22 -----------------------------------------------------------------
# The port / env_file / volume / restart / healthcheck checks are the DoD-10 tests above,
# which now read docker-compose.prod.yml through compose_text().


def test_f013_dod22_prod_compose_uses_published_image() -> None:
    # fast/013 DoD-22: docker-compose.prod.yml references image: iezious/rphelper:latest (and only it).
    images = re.findall(r"(?m)^\s*image:\s*[\"']?([^\s\"']+)", compose_text())
    assert images == ["iezious/rphelper:latest"], images


def test_f013_dod22_prod_compose_has_no_build_key() -> None:
    # fast/013 DoD-22: the prod compose is image-based -- no `build:` key anywhere.
    assert not re.search(r"(?m)^\s*build\s*:", compose_text())


# --- fast/013 DoD-23 -----------------------------------------------------------------


def test_f013_dod23_old_dev_compose_is_gone() -> None:
    # fast/013 DoD-23: the old dev compose file no longer exists.
    assert not (REPO_ROOT / OLD_DEV_COMPOSE).exists()


def test_f013_dod23_compose_yml_is_the_dev_compose() -> None:
    # fast/013 DoD-23: docker-compose.yml has the `api` and `ui` services and no iezious/rphelper image.
    raw = read_text(DEV_COMPOSE)
    body = strip_hash_comments(raw)
    assert re.search(r"(?m)^\s+api:\s*$", body), "docker-compose.yml has no `api` service"
    assert re.search(r"(?m)^\s+ui:\s*$", body), "docker-compose.yml has no `ui` service"
    assert "iezious/rphelper" not in raw


def test_f013_dod23_dev_compose_usage_comment_has_no_file_flag() -> None:
    # fast/013 DoD-23: the usage comment is `docker compose up`, without `-f`.
    comments = [line for line in read_text(DEV_COMPOSE).splitlines() if line.lstrip().startswith("#")]
    assert any(re.search(r"\bdocker compose up\b", line) for line in comments), comments
    assert not any(re.search(r"\bdocker[ -]compose\s+-f\b", line) for line in comments), comments


# --- fast/013 DoD-24 -----------------------------------------------------------------


def test_f013_dod24_source_files_cover_new_layout() -> None:
    # fast/013 DoD-24: SOURCE_FILES covers the prod compose and both scripts, and drops the old dev compose.
    for relative in (PROD_COMPOSE, "build.sh", "deploy.sh"):
        assert relative in SOURCE_FILES
    assert OLD_DEV_COMPOSE not in SOURCE_FILES


@pytest.mark.parametrize("relative", SOURCE_FILES)
def test_f013_dod24_no_source_file_mentions_old_dev_compose(relative: str) -> None:
    # fast/013 DoD-24: no deployment source file (incl. .env.example, backend/.gitignore) names the old file.
    assert OLD_DEV_COMPOSE not in read_text(relative)


def test_f013_dod24_env_example_names_prod_compose() -> None:
    # fast/013 DoD-24: .env.example names docker-compose.prod.yml.
    assert PROD_COMPOSE in read_text(".env.example")


# --- fast/013 DoD-25 -----------------------------------------------------------------


@pytest.mark.parametrize("relative", SCRIPTS)
def test_f013_dod25_script_has_bash_shebang(relative: str) -> None:
    # fast/013 DoD-25: both scripts start with a bash shebang.
    first_line = read_text(relative).splitlines()[0]
    assert re.fullmatch(r"#!\s*(?:/usr/bin/env\s+bash|/bin/bash|/usr/bin/bash)\s*", first_line), first_line


@pytest.mark.parametrize("relative", SCRIPTS)
def test_f013_dod25_script_enables_strict_mode(relative: str) -> None:
    # fast/013 DoD-25: both scripts enable `set -euo pipefail`.
    assert re.search(r"(?m)^\s*set\s+-euo\s+pipefail\s*$", read_text(relative))
