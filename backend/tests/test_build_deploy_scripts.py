"""Execution tests for ``build.sh`` and ``deploy.sh`` (fast/013.build-and-deploy-scripts).

Every expected value comes from the plan's Interface intent and Definition of done
(DoD-1..DoD-21). Each test copies the script under test into its own ``tmp_path`` and runs
it as ``bash <script>`` with stub ``docker``, ``7z`` and ``git`` executables prepended to
``PATH`` (the rest of ``PATH`` kept so coreutils resolve). The stubs follow the plan's stub
contracts and append one record per invocation -- command, cwd, whether ``<cwd>/data``
existed, argv -- to a per-test log. No network, no Docker daemon, no shared state.

Stub behaviour:

- ``git``: for ``... tag --points-at ...`` prints ``$STUB_GIT_TAGS``; ``$STUB_GIT_EXIT`` != 0 fails.
- ``docker build``: exits ``$STUB_DOCKER_BUILD_EXIT``.
- ``docker save``: writes ``$STUB_SAVE_PAYLOAD`` to stdout, exits ``$STUB_DOCKER_SAVE_EXIT``.
- ``docker load``: copies stdin to ``$STUB_LOAD_CAPTURE``, exits ``$STUB_DOCKER_LOAD_EXIT``.
- ``7z a``: the single non-switch argument after ``a`` is the archive; stdin is **appended** to
  it (an existing archive is updated, never replaced -- like real ``7z a``); exits ``$STUB_7Z_EXIT``.
- ``7z x``: the single non-switch argument after ``x`` is the archive; its bytes go to stdout;
  exits ``$STUB_7Z_EXIT``.
"""

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BASH = shutil.which("bash")

pytestmark = [
    pytest.mark.skipif(BASH is None, reason="bash is not available"),
    pytest.mark.skipif(sys.platform == "win32", reason="the stubbed-PATH harness needs a POSIX bash environment"),
]

SEP = "\x1f"
RUN_TIMEOUT = 30

IMAGE_LATEST = "iezious/rphelper:latest"
ARCHIVE_NAME = "rphelper-latest.7z"
STAGED = {ARCHIVE_NAME, "docker-compose.yml", "deploy.sh"}

SAVE_PAYLOAD = "FAKE-DOCKER-SAVE-STREAM fast/013\n"
OLD_ARCHIVE = b"OLD-ARCHIVE-FROM-A-PREVIOUS-BUILD\n"
STORE_ARCHIVE = b"FAKE-7Z-ARCHIVE-CONTENT fast/013\n"
STORE_COMPOSE = b"# store compose fixture\nservices:\n  rphelper:\n    image: iezious/rphelper:latest\n"
PROD_COMPOSE_FIXTURE = b"# prod compose fixture\nservices:\n  rphelper:\n    image: iezious/rphelper:latest\n"
ENV_CONTENT = b"RPHELPER_FIXTURE=1\n"

RESTART_SEQUENCE = [["compose", "up", "-d"], ["image", "prune", "-f"], ["compose", "ps"]]

LOG_PREFIX = r"""
line="__NAME__"
line+=$'\x1f'"$PWD"
if [ -d "$PWD/data" ]; then line+=$'\x1f'1; else line+=$'\x1f'0; fi
for a in "$@"; do line+=$'\x1f'"$a"; done
printf '%s\n' "$line" >> "$STUB_LOG"
"""

DOCKER_BODY = r"""
case "${1:-}" in
  build)
    exit "${STUB_DOCKER_BUILD_EXIT:-0}" ;;
  save)
    printf '%s' "${STUB_SAVE_PAYLOAD:-}"
    exit "${STUB_DOCKER_SAVE_EXIT:-0}" ;;
  load)
    cat > "$STUB_LOAD_CAPTURE"
    exit "${STUB_DOCKER_LOAD_EXIT:-0}" ;;
esac
exit 0
"""

GIT_BODY = r"""
if [ "${STUB_GIT_EXIT:-0}" != "0" ]; then
  echo "fatal: stub git failure" >&2
  exit "$STUB_GIT_EXIT"
fi
case " $* " in
  *" tag "*"--points-at"*) printf '%s' "${STUB_GIT_TAGS:-}" ;;
esac
exit 0
"""

SEVENZ_BODY = r"""
mode=""
archive=""
for a in "$@"; do
  if [ -z "$mode" ]; then mode="$a"; continue; fi
  case "$a" in
    -*) ;;
    *) if [ -z "$archive" ]; then archive="$a"; fi ;;
  esac
done
case "$mode" in
  a)
    cat >> "$archive" || exit 2
    exit "${STUB_7Z_EXIT:-0}" ;;
  x)
    cat -- "$archive" || exit 2
    exit "${STUB_7Z_EXIT:-0}" ;;
esac
exit 0
"""


# --- harness -------------------------------------------------------------------------


@dataclass
class Call:
    name: str
    cwd: Path
    data_present: bool
    args: list[str]


@dataclass
class Run:
    returncode: int
    stdout: str
    stderr: str
    calls: list[Call] = field(default_factory=list)

    @property
    def output(self) -> str:
        return self.stdout + self.stderr

    def of(self, name: str) -> list[Call]:
        return [call for call in self.calls if call.name == name]

    def docker(self, subcommand: str) -> list[Call]:
        return [call for call in self.of("docker") if call.args[:1] == [subcommand]]

    def docker_args_except_load(self) -> list[list[str]]:
        return [call.args for call in self.of("docker") if call.args[:1] != ["load"]]


class Sandbox:
    """Per-test filesystem: stub bin dir, call log, a DOCKER_STORE and an unrelated cwd."""

    def __init__(self, tmp_path: Path) -> None:
        assert BASH is not None
        self.root = tmp_path
        self.bin = tmp_path / "stub-bin"
        self.bin.mkdir()
        for name, body in (("docker", DOCKER_BODY), ("7z", SEVENZ_BODY), ("git", GIT_BODY)):
            stub = self.bin / name
            text = f"#!{BASH}\n" + LOG_PREFIX.replace("__NAME__", name) + body
            stub.write_text(text, encoding="utf-8", newline="\n")
            stub.chmod(0o755)
        self.log = tmp_path / "stub-calls.log"
        self.load_capture = tmp_path / "docker-load-capture.bin"
        self.docker_store = tmp_path / "store"
        self.docker_store.mkdir()
        self.store = self.docker_store / "rphelper"
        self.elsewhere = tmp_path / "elsewhere"
        self.elsewhere.mkdir()
        self.repo = tmp_path / "repo"
        self.deploy_dir = tmp_path / "server-app"
        # A minimal environment: a developer's own DOCKER_STORE must never leak in.
        self.env: dict[str, str] = {
            "PATH": f"{self.bin}{os.pathsep}{os.environ.get('PATH', '')}",
            "HOME": str(tmp_path),
            "LC_ALL": "C",
            "STUB_LOG": str(self.log),
            "STUB_LOAD_CAPTURE": str(self.load_capture),
            "STUB_SAVE_PAYLOAD": SAVE_PAYLOAD,
            "STUB_GIT_TAGS": "v0.0.1\n",
            "DOCKER_STORE": str(self.docker_store),
        }

    # -- build.sh --

    def prepare_build(self) -> Path:
        """A throwaway repo root holding build.sh, deploy.sh and docker-compose.prod.yml."""
        self.repo.mkdir()
        script = self.repo / "build.sh"
        shutil.copyfile(REPO_ROOT / "build.sh", script)
        deploy = self.repo / "deploy.sh"
        shutil.copyfile(REPO_ROOT / "deploy.sh", deploy)
        deploy.chmod(0o755)
        (self.repo / "docker-compose.prod.yml").write_bytes(PROD_COMPOSE_FIXTURE)
        return script

    def seed_old_archive(self) -> Path:
        self.store.mkdir(parents=True, exist_ok=True)
        archive = self.store / ARCHIVE_NAME
        archive.write_bytes(OLD_ARCHIVE)
        return archive

    # -- deploy.sh --

    def prepare_deploy(self) -> Path:
        """A deploy dir holding deploy.sh and .env, and a populated store dir."""
        self.deploy_dir.mkdir()
        script = self.deploy_dir / "deploy.sh"
        shutil.copyfile(REPO_ROOT / "deploy.sh", script)
        (self.deploy_dir / ".env").write_bytes(ENV_CONTENT)
        self.store.mkdir()
        (self.store / ARCHIVE_NAME).write_bytes(STORE_ARCHIVE)
        (self.store / "docker-compose.yml").write_bytes(STORE_COMPOSE)
        return script

    # -- running --

    def run(self, script: Path, *args: str, cwd: Path | None = None) -> Run:
        assert BASH is not None
        result = subprocess.run(
            [BASH, str(script), *args],
            cwd=cwd or self.elsewhere,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=RUN_TIMEOUT,
            check=False,
        )
        return Run(result.returncode, result.stdout, result.stderr, self.calls())

    def calls(self) -> list[Call]:
        if not self.log.exists():
            return []
        calls: list[Call] = []
        for line in self.log.read_text(encoding="utf-8").splitlines():
            name, cwd, data, *args = line.split(SEP)
            calls.append(Call(name, Path(cwd), data == "1", args))
        return calls

    def store_listing(self) -> set[str]:
        return {entry.name for entry in self.store.iterdir()} if self.store.is_dir() else set()


def build_tags(args: list[str]) -> list[str]:
    """Every ``-t`` / ``--tag`` value of a ``docker build`` argv."""
    tags: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg in ("-t", "--tag") and index + 1 < len(args):
            tags.append(args[index + 1])
            index += 2
            continue
        if arg.startswith("--tag="):
            tags.append(arg.split("=", 1)[1])
        index += 1
    return tags


def archive_argument(call: Call, subcommand: str) -> Path:
    """The single non-switch argument after ``subcommand`` in a ``7z`` argv, resolved against its cwd."""
    assert call.args[:1] == [subcommand], call.args
    operands = [arg for arg in call.args[1:] if not arg.startswith("-")]
    assert len(operands) == 1, f"expected one non-switch 7z argument, got {operands}"
    return (call.cwd / operands[0]).resolve()


def same_path(left: Path | str, right: Path) -> bool:
    return Path(left).resolve() == right.resolve()


def mentions_version_form(text: str) -> bool:
    # DoD-3: "contains `v` + `X.Y.Z` or an example like `v0.0.1`" (a malformed tag such as
    # v1.2.3-rc1 echoed back does not count).
    return bool(re.search(r"vX\.Y\.Z|v\d+\.\d+\.\d+(?![\w.-])", text))


@pytest.fixture
def sandbox(tmp_path: Path) -> Sandbox:
    return Sandbox(tmp_path)


# --- build.sh: DoD-1 -----------------------------------------------------------------


def test_dod1_build_tags_latest_and_version_and_saves_both(sandbox: Sandbox) -> None:
    # DoD-1: HEAD tagged v0.0.1 -> exit 0, docker build -t latest -t 0.0.1, docker save with both refs.
    script = sandbox.prepare_build()
    sandbox.env["STUB_GIT_TAGS"] = "v0.0.1\n"
    run = sandbox.run(script)

    assert run.returncode == 0, run.output
    builds = run.docker("build")
    assert len(builds) == 1, run.calls
    assert sorted(build_tags(builds[0].args)) == sorted([IMAGE_LATEST, "iezious/rphelper:0.0.1"])
    saves = run.docker("save")
    assert len(saves) == 1, run.calls
    assert {IMAGE_LATEST, "iezious/rphelper:0.0.1"} <= set(saves[0].args[1:])


# --- build.sh: DoD-2 -----------------------------------------------------------------


def test_dod2_build_picks_the_single_version_tag_among_others(sandbox: Sandbox) -> None:
    # DoD-2: non-version tags alongside one vX.Y.Z tag -> version 1.2.3.
    script = sandbox.prepare_build()
    sandbox.env["STUB_GIT_TAGS"] = "release\nv1.2\nv1.2.3-rc1\nv1.2.3\n"
    run = sandbox.run(script)

    assert run.returncode == 0, run.output
    builds = run.docker("build")
    assert len(builds) == 1, run.calls
    assert sorted(build_tags(builds[0].args)) == sorted([IMAGE_LATEST, "iezious/rphelper:1.2.3"])
    saves = run.docker("save")
    assert len(saves) == 1, run.calls
    assert {IMAGE_LATEST, "iezious/rphelper:1.2.3"} <= set(saves[0].args[1:])


# --- build.sh: DoD-3 -----------------------------------------------------------------


@pytest.mark.parametrize(
    "tags",
    [
        "",
        "1.2.3\n",
        "v1.2\n",
        "v1.2.3-rc1\n",
        "vX.Y.Z\n",
        "1.2.3\nv1.2\nv1.2.3-rc1\nvX.Y.Z\n",
    ],
    ids=["no-tag", "no-v", "two-parts", "suffix", "letters", "all-malformed"],
)
def test_dod3_build_without_a_version_tag_fails_before_docker(sandbox: Sandbox, tags: str) -> None:
    # DoD-3: no tag / only malformed tags -> non-zero, stderr names the vX.Y.Z form, docker never invoked.
    script = sandbox.prepare_build()
    sandbox.env["STUB_GIT_TAGS"] = tags
    run = sandbox.run(script)

    assert run.returncode != 0, run.output
    assert mentions_version_form(run.stderr), run.stderr
    assert run.of("docker") == []


def test_dod3_build_with_failing_git_fails_before_docker(sandbox: Sandbox) -> None:
    # DoD-3 / Interface intent (version resolution): a failing git -> error naming vX.Y.Z, no docker.
    script = sandbox.prepare_build()
    sandbox.env["STUB_GIT_EXIT"] = "128"
    run = sandbox.run(script)

    assert run.returncode != 0, run.output
    assert mentions_version_form(run.stderr), run.stderr
    assert run.of("docker") == []


# --- build.sh: DoD-4 -----------------------------------------------------------------


def test_dod4_build_with_two_version_tags_fails_before_docker(sandbox: Sandbox) -> None:
    # DoD-4: two matching version tags on HEAD -> non-zero, docker never invoked.
    script = sandbox.prepare_build()
    sandbox.env["STUB_GIT_TAGS"] = "v1.0.0\nv1.0.1\n"
    run = sandbox.run(script)

    assert run.returncode != 0, run.output
    assert run.of("docker") == []


# --- build.sh: DoD-5 -----------------------------------------------------------------


@pytest.mark.parametrize("value", [None, ""], ids=["unset", "empty"])
def test_dod5_build_requires_docker_store(sandbox: Sandbox, value: str | None) -> None:
    # DoD-5: DOCKER_STORE unset/empty -> non-zero, stderr mentions DOCKER_STORE, nothing created, no docker/git.
    script = sandbox.prepare_build()
    if value is None:
        del sandbox.env["DOCKER_STORE"]
    else:
        sandbox.env["DOCKER_STORE"] = value
    run = sandbox.run(script)

    assert run.returncode != 0, run.output
    assert "DOCKER_STORE" in run.stderr, run.stderr
    assert run.of("docker") == []
    assert run.of("git") == []  # Order of checks: DOCKER_STORE comes before version resolution.
    assert not sandbox.store.exists()
    assert list(sandbox.elsewhere.iterdir()) == []
    assert not (sandbox.repo / "rphelper").exists()


# --- build.sh: DoD-6 -----------------------------------------------------------------


def test_dod6_build_stages_archive_compose_and_deploy_script(sandbox: Sandbox) -> None:
    # DoD-6: store dir created; holds exactly the archive (docker save bytes), the prod compose
    # renamed to docker-compose.yml, and deploy.sh (executable bit kept, per Interface intent).
    script = sandbox.prepare_build()
    assert not sandbox.store.exists()
    run = sandbox.run(script)

    assert run.returncode == 0, run.output
    assert sandbox.store_listing() == STAGED
    archive = (sandbox.store / ARCHIVE_NAME).read_bytes()
    assert archive, "rphelper-latest.7z is empty"
    assert archive == SAVE_PAYLOAD.encode()
    assert (sandbox.store / "docker-compose.yml").read_bytes() == PROD_COMPOSE_FIXTURE
    assert (sandbox.store / "deploy.sh").read_bytes() == (sandbox.repo / "deploy.sh").read_bytes()
    assert os.access(sandbox.store / "deploy.sh", os.X_OK), "staged deploy.sh lost its executable bit"


def test_dod6_build_writes_archive_through_a_temp_path_in_the_store(sandbox: Sandbox) -> None:
    # DoD-6 / Interface intent step 2: `7z a` reads stdin (-si...) and writes a temp path inside the store dir.
    script = sandbox.prepare_build()
    run = sandbox.run(script)

    assert run.returncode == 0, run.output
    adds = [call for call in run.of("7z") if call.args[:1] == ["a"]]
    assert len(adds) == 1, run.calls
    assert any(arg.startswith("-si") for arg in adds[0].args[1:]), adds[0].args
    temp = archive_argument(adds[0], "a")
    assert temp.is_relative_to(sandbox.store.resolve()), temp
    assert temp != (sandbox.store / ARCHIVE_NAME).resolve()


# --- build.sh: DoD-7 -----------------------------------------------------------------


def test_dod7_build_tolerates_trailing_slash_in_docker_store(sandbox: Sandbox) -> None:
    # DoD-7: DOCKER_STORE with a trailing slash produces the same store layout (paths normalized).
    script = sandbox.prepare_build()
    sandbox.env["DOCKER_STORE"] = f"{sandbox.docker_store}/"
    run = sandbox.run(script)

    assert run.returncode == 0, run.output
    assert sandbox.store_listing() == STAGED
    assert (sandbox.store / ARCHIVE_NAME).read_bytes() == SAVE_PAYLOAD.encode()
    assert (sandbox.store / "docker-compose.yml").read_bytes() == PROD_COMPOSE_FIXTURE
    assert "//rphelper" not in run.output
    for call in run.of("7z"):
        assert not any("//" in arg for arg in call.args), call.args


# --- build.sh: DoD-8 -----------------------------------------------------------------


def test_dod8_failed_docker_build_keeps_previous_archive(sandbox: Sandbox) -> None:
    # DoD-8: docker build fails -> non-zero, previous archive byte-identical, no temp file left.
    script = sandbox.prepare_build()
    archive = sandbox.seed_old_archive()
    sandbox.env["STUB_DOCKER_BUILD_EXIT"] = "1"
    run = sandbox.run(script)

    assert run.returncode != 0, run.output
    assert archive.read_bytes() == OLD_ARCHIVE
    assert sandbox.store_listing() <= STAGED, sandbox.store_listing()


# --- build.sh: DoD-9 -----------------------------------------------------------------


@pytest.mark.parametrize("failing", ["STUB_7Z_EXIT", "STUB_DOCKER_SAVE_EXIT"], ids=["7z", "docker-save"])
def test_dod9_failed_archive_step_keeps_previous_archive(sandbox: Sandbox, failing: str) -> None:
    # DoD-9: 7z (or docker save) fails -> non-zero, previous archive byte-identical, no temp file left.
    script = sandbox.prepare_build()
    archive = sandbox.seed_old_archive()
    sandbox.env[failing] = "1"
    run = sandbox.run(script)

    assert run.returncode != 0, run.output
    assert archive.read_bytes() == OLD_ARCHIVE
    assert sandbox.store_listing() <= STAGED, sandbox.store_listing()


# --- build.sh: DoD-10 ----------------------------------------------------------------


def test_dod10_successful_build_fully_replaces_previous_archive(sandbox: Sandbox) -> None:
    # DoD-10: an old archive with different content is replaced, not updated/merged.
    script = sandbox.prepare_build()
    archive = sandbox.seed_old_archive()
    run = sandbox.run(script)

    assert run.returncode == 0, run.output
    assert archive.read_bytes() == SAVE_PAYLOAD.encode()
    assert sandbox.store_listing() == STAGED


# --- build.sh: DoD-11 ----------------------------------------------------------------


def test_dod11_build_resolves_repo_root_from_its_own_location(sandbox: Sandbox) -> None:
    # DoD-11: from an unrelated cwd, the docker build context and the git -C target are the script's dir.
    script = sandbox.prepare_build()
    run = sandbox.run(script, cwd=sandbox.elsewhere)

    assert run.returncode == 0, run.output
    builds = run.docker("build")
    assert len(builds) == 1, run.calls
    assert same_path(builds[0].cwd / builds[0].args[-1], sandbox.repo), builds[0].args

    gits = run.of("git")
    assert gits, "git was never invoked"
    for call in gits:
        assert "-C" in call.args, call.args
        target = call.args[call.args.index("-C") + 1]
        assert same_path(call.cwd / target, sandbox.repo), call.args
    assert list(sandbox.elsewhere.iterdir()) == []


# --- build.sh: DoD-12 ----------------------------------------------------------------


@pytest.mark.parametrize("arg", ["foo", "--help", "v1.0.0"])
def test_dod12_build_rejects_any_argument(sandbox: Sandbox, arg: str) -> None:
    # DoD-12: any argument -> non-zero, no docker.
    script = sandbox.prepare_build()
    run = sandbox.run(script, arg)

    assert run.returncode != 0, run.output
    assert run.of("docker") == []


# --- deploy.sh helpers ---------------------------------------------------------------


def assert_images_loaded(sandbox: Sandbox, run: Run) -> None:
    extracts = [call for call in run.of("7z") if call.args[:1] == ["x"]]
    assert len(extracts) == 1, run.calls
    assert "-so" in extracts[0].args, extracts[0].args
    assert archive_argument(extracts[0], "x") == (sandbox.store / ARCHIVE_NAME).resolve()
    assert len(run.docker("load")) == 1, run.calls
    assert sandbox.load_capture.read_bytes() == STORE_ARCHIVE


def assert_full_deploy(sandbox: Sandbox, run: Run) -> None:
    """DoD-13: compose copied, archive loaded, data/ made, up -> prune -> ps in the deploy dir."""
    assert run.returncode == 0, run.output
    assert (sandbox.deploy_dir / "docker-compose.yml").read_bytes() == STORE_COMPOSE
    assert_images_loaded(sandbox, run)
    assert (sandbox.deploy_dir / "data").is_dir()
    assert run.docker_args_except_load() == RESTART_SEQUENCE

    dockers = run.of("docker")
    load_index = next(i for i, call in enumerate(dockers) if call.args[:1] == ["load"])
    up_index = next(i for i, call in enumerate(dockers) if call.args[:2] == ["compose", "up"])
    assert load_index < up_index
    for call in run.docker("compose"):
        assert same_path(call.cwd, sandbox.deploy_dir), call
        assert call.data_present, f"data/ did not exist when `docker {' '.join(call.args)}` ran"
    assert (sandbox.deploy_dir / ".env").read_bytes() == ENV_CONTENT


# --- deploy.sh: DoD-13 ---------------------------------------------------------------


def test_dod13_default_deploy_loads_copies_and_restarts(sandbox: Sandbox) -> None:
    # DoD-13: default invocation copies compose, 7z x -so | docker load, mkdir data, up -d, prune -f, ps.
    script = sandbox.prepare_deploy()
    run = sandbox.run(script)
    assert_full_deploy(sandbox, run)


# --- deploy.sh: DoD-14 ---------------------------------------------------------------


def test_dod14_images_mode_loads_without_copying_compose(sandbox: Sandbox) -> None:
    # DoD-14: --images loads the image but does not copy the compose file.
    script = sandbox.prepare_deploy()
    run = sandbox.run(script, "--images")

    assert run.returncode == 0, run.output
    assert_images_loaded(sandbox, run)
    assert not (sandbox.deploy_dir / "docker-compose.yml").exists()


def test_dod14_config_mode_copies_compose_without_loading(sandbox: Sandbox) -> None:
    # DoD-14: --config copies the compose file but invokes no 7z and no docker load.
    script = sandbox.prepare_deploy()
    run = sandbox.run(script, "--config")

    assert run.returncode == 0, run.output
    assert (sandbox.deploy_dir / "docker-compose.yml").read_bytes() == STORE_COMPOSE
    assert run.of("7z") == []
    assert run.docker("load") == []


def test_dod14_all_mode_behaves_as_default(sandbox: Sandbox) -> None:
    # DoD-14: --all behaves as the default.
    script = sandbox.prepare_deploy()
    run = sandbox.run(script, "--all")
    assert_full_deploy(sandbox, run)


# --- deploy.sh: DoD-15 ---------------------------------------------------------------


def test_dod15_no_restart_skips_up_and_prune_and_needs_no_env(sandbox: Sandbox) -> None:
    # DoD-15: --no-restart -> no compose up, no image prune, still compose ps; .env not required.
    script = sandbox.prepare_deploy()
    (sandbox.deploy_dir / ".env").unlink()
    run = sandbox.run(script, "--no-restart")

    assert run.returncode == 0, run.output
    assert run.docker_args_except_load() == [["compose", "ps"]]
    assert same_path(run.docker("compose")[0].cwd, sandbox.deploy_dir)
    assert not (sandbox.deploy_dir / ".env").exists()


# --- deploy.sh: DoD-16 ---------------------------------------------------------------


@pytest.mark.parametrize("arg", ["--bogus", "images", "-x"])
def test_dod16_unknown_argument_prints_usage_and_exits_1(sandbox: Sandbox, arg: str) -> None:
    # DoD-16: an unknown argument -> exit 1, usage message, no docker.
    script = sandbox.prepare_deploy()
    run = sandbox.run(script, arg)

    assert run.returncode == 1, run.output
    assert "usage" in run.output.lower() or "--no-restart" in run.output, run.output
    assert run.of("docker") == []


# --- deploy.sh: DoD-17 ---------------------------------------------------------------


@pytest.mark.parametrize("value", [None, ""], ids=["unset", "empty"])
def test_dod17_deploy_requires_docker_store(sandbox: Sandbox, value: str | None) -> None:
    # DoD-17: DOCKER_STORE unset/empty -> non-zero, message mentions DOCKER_STORE, no docker.
    script = sandbox.prepare_deploy()
    if value is None:
        del sandbox.env["DOCKER_STORE"]
    else:
        sandbox.env["DOCKER_STORE"] = value
    run = sandbox.run(script)

    assert run.returncode != 0, run.output
    assert "DOCKER_STORE" in run.output, run.output
    assert run.of("docker") == []


def test_dod17_deploy_requires_existing_store_dir(sandbox: Sandbox) -> None:
    # DoD-17: $DOCKER_STORE/rphelper missing -> non-zero, no docker.
    script = sandbox.prepare_deploy()
    shutil.rmtree(sandbox.store)
    run = sandbox.run(script)

    assert run.returncode != 0, run.output
    assert run.of("docker") == []


# --- deploy.sh: DoD-18 ---------------------------------------------------------------


@pytest.mark.parametrize("args", [(), ("--images",), ("--all",)], ids=["default", "images", "all"])
def test_dod18_missing_archive_fails_without_loading(sandbox: Sandbox, args: tuple[str, ...]) -> None:
    # DoD-18: missing archive in --images/--all mode -> non-zero, no docker load.
    script = sandbox.prepare_deploy()
    (sandbox.store / ARCHIVE_NAME).unlink()
    run = sandbox.run(script, *args)

    assert run.returncode != 0, run.output
    assert run.docker("load") == []


@pytest.mark.parametrize("args", [(), ("--config",), ("--all",)], ids=["default", "config", "all"])
def test_dod18_missing_store_compose_fails(sandbox: Sandbox, args: tuple[str, ...]) -> None:
    # DoD-18: missing store compose in --config/--all mode -> non-zero.
    script = sandbox.prepare_deploy()
    (sandbox.store / "docker-compose.yml").unlink()
    run = sandbox.run(script, *args)

    assert run.returncode != 0, run.output


# --- deploy.sh: DoD-19 ---------------------------------------------------------------


@pytest.mark.parametrize(
    "args", [(), ("--images",), ("--config",), ("--all",)], ids=["default", "images", "config", "all"]
)
def test_dod19_restart_without_env_fails_before_docker(sandbox: Sandbox, args: tuple[str, ...]) -> None:
    # DoD-19: restart requested, no .env -> non-zero, message mentions .env, no docker, .env not created.
    script = sandbox.prepare_deploy()
    (sandbox.deploy_dir / ".env").unlink()
    run = sandbox.run(script, *args)

    assert run.returncode != 0, run.output
    assert ".env" in run.output, run.output
    assert run.of("docker") == []
    assert not (sandbox.deploy_dir / ".env").exists()


# --- deploy.sh: DoD-20 ---------------------------------------------------------------


def test_dod20_deploy_resolves_deploy_dir_from_its_own_location(sandbox: Sandbox) -> None:
    # DoD-20: from an unrelated cwd, compose copy and data/ land next to the script; compose runs there.
    script = sandbox.prepare_deploy()
    run = sandbox.run(script, cwd=sandbox.elsewhere)

    assert run.returncode == 0, run.output
    assert (sandbox.deploy_dir / "docker-compose.yml").read_bytes() == STORE_COMPOSE
    assert (sandbox.deploy_dir / "data").is_dir()
    assert list(sandbox.elsewhere.iterdir()) == []
    composes = run.docker("compose")
    assert composes, "docker compose was never invoked"
    for call in composes:
        assert same_path(call.cwd, sandbox.deploy_dir), call


# --- deploy.sh: DoD-21 ---------------------------------------------------------------


@pytest.mark.parametrize("failing", ["STUB_DOCKER_LOAD_EXIT", "STUB_7Z_EXIT"], ids=["docker-load", "7z-x"])
def test_dod21_failed_image_load_aborts_before_compose_up(sandbox: Sandbox, failing: str) -> None:
    # DoD-21: a failing docker load (or 7z x) -> non-zero, docker compose up skipped.
    script = sandbox.prepare_deploy()
    sandbox.env[failing] = "1"
    run = sandbox.run(script)

    assert run.returncode != 0, run.output
    assert not any(call.args[:2] == ["compose", "up"] for call in run.of("docker")), run.calls
