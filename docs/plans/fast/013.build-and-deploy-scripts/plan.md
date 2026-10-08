# Fast feature 013 — build-and-deploy-scripts — plan

## Goal

Add a host-side `build.sh` that builds the prod image as
`iezious/rphelper:latest` + `iezious/rphelper:<version>` (version from a
`vX.Y.Z` tag on HEAD), packs it into a 7z archive and stages archive, prod
compose and `deploy.sh` into `$DOCKER_STORE/rphelper`; and a `deploy.sh` that,
on the deploy server, loads the image from the store, copies the compose next to
itself and (re)starts the stack. Rename the dev compose to `docker-compose.yml`
and replace the build-based prod compose with an image-based
`docker-compose.prod.yml`.

## Source files

- `build.sh` — new; repo-root build-and-stage script (executable).
- `deploy.sh` — new; repo-root deploy script, staged into the store (executable).
- `docker-compose.prod.yml` — new; image-based prod compose (old prod content, `image:` instead of `build:`).
- `docker-compose.yml` — replaced; now holds the former dev compose content, usage comment updated.
- `docker-compose.dev.yml` — deleted (renamed to `docker-compose.yml`).
- `.env.example` — comment on line 2 now names `docker-compose.prod.yml`.
- `backend/.gitignore` — comment on line 15 now names `docker-compose.yml`.

## Test files

- `backend/tests/test_deployment_files.py` — modified; static checks retargeted to the new compose layout and the two scripts.
- `backend/tests/test_build_deploy_scripts.py` — new; executes both scripts under `bash` with stubbed `docker` / `7z` / `git`.

## Interface intent

Shell scripts have no type signatures; the "interface" is the command line, the
environment, the external commands invoked and the filesystem effects. The
skeleton stub for each script is a valid bash script that exits non-zero with a
"not implemented" message.

### `build.sh`

- **Invocation:** `build.sh` with no arguments. Any argument → usage message,
  non-zero exit, no `docker` call.
- **Environment:** `DOCKER_STORE` (required, non-empty; a trailing slash is
  tolerated and normalized). Store dir = `$DOCKER_STORE/rphelper`.
- **Repo root:** the directory containing the script, resolved from
  `${BASH_SOURCE[0]}` — never the caller's cwd. Inputs read from it:
  `docker-compose.prod.yml` and `deploy.sh` (both must exist, else fail before
  any `docker` call); it is also the `docker build` context.
- **Version resolution:** runs `git -C <repo root> tag --points-at HEAD`, whose
  stdout is a newline-separated tag list. Selects tags matching exactly
  `v<digits>.<digits>.<digits>`. Exactly one match → version is the tag without
  the leading `v`. Zero matches, two or more matches, or a failing `git` → error
  to stderr naming the expected `vX.Y.Z` form, non-zero exit, no `docker` call.
- **Order of checks:** `DOCKER_STORE`, then required input files, then version
  — all before any `docker` invocation.
- **External commands, in order on success:**
  1. `docker build -t iezious/rphelper:latest -t iezious/rphelper:<version> <repo root>`.
  2. `docker save iezious/rphelper:latest iezious/rphelper:<version>` piped into
     `7z a` reading from stdin (`-si…` switch), writing to a temporary archive
     path inside the store dir that did not previously exist. Contract for stubs:
     every `7z` switch begins with `-`; the single non-switch argument after the
     `a` subcommand is the archive path to write.
  3. The temp archive is moved to `<store>/rphelper-latest.7z`, replacing any
     previous one.
- **Staging (success):** `<store>/rphelper-latest.7z`,
  `<store>/docker-compose.yml` (a copy of `docker-compose.prod.yml`, renamed) and
  `<store>/deploy.sh` (a copy of `deploy.sh`, executable bit kept). The store dir
  is created if missing.
- **Failure behaviour:** strict mode (`set -euo pipefail`); a non-zero exit from
  `docker build`, `docker save` or `7z` aborts with a non-zero exit, leaves no
  temp archive behind, and does **not** replace or create
  `<store>/rphelper-latest.7z`.
- **Output:** prints the resolved version and the store path; final line(s)
  confirm what was staged.

### `deploy.sh`

- **Invocation:** `deploy.sh [--images|--config|--all] [--no-restart]`, default
  mode `all`, restart on by default. Any other argument → usage line to stdout or
  stderr, exit 1, no `docker` call.
- **Environment:** `DOCKER_STORE` (required, non-empty, trailing slash
  tolerated). Store dir `$DOCKER_STORE/rphelper` **must already exist**, else
  error + non-zero exit.
- **Deploy dir:** the directory containing the script (from `${BASH_SOURCE[0]}`),
  not the caller's cwd.
- **`.env` precondition:** when restart is on and `<deploy dir>/.env` does not
  exist → error naming `.env`, non-zero exit, before any `docker` call. Never
  creates or templates `.env`.
- **`images` / `all`:** `<store>/rphelper-latest.7z` must exist (else error,
  non-zero). Runs `7z x -so <archive>` piped into `docker load`. Contract for
  stubs: the single non-switch argument after `x` is the archive path; archive
  content goes to stdout.
- **`config` / `all`:** `<store>/docker-compose.yml` must exist (else error,
  non-zero). Copies it to `<deploy dir>/docker-compose.yml`, overwriting.
- **Always:** `mkdir -p <deploy dir>/data`; subsequent compose commands run
  with cwd = deploy dir.
- **Restart on:** `docker compose up -d`, then `docker image prune -f`.
  **Restart off:** neither is invoked.
- **Always last:** `docker compose ps`.
- Strict mode (`set -euo pipefail`); a failing `7z` or `docker load` aborts
  non-zero.

### `docker-compose.prod.yml`

Single service `rphelper` with `image: iezious/rphelper:latest` and **no
`build:` key**; `ports: ["8193:80"]`, `env_file: .env`, volume
`./data:/app/data`, the `curl -f http://localhost/api/health` healthcheck with
its existing comment explaining that it asserts the status code and never the
body, `restart: unless-stopped`. Content otherwise carried over from the current
`docker-compose.yml`.

### `docker-compose.yml`

Byte-for-byte the current `docker-compose.dev.yml` except the header usage
comment, which becomes `docker compose up` (no `-f` flag).

## Definition of done

Build script:

- DoD-1 `[test]` With HEAD tagged `v0.0.1` (git stub lists it), `build.sh` exits 0 and calls `docker build` with both `-t iezious/rphelper:latest` and `-t iezious/rphelper:0.0.1`, and `docker save` with both references.
- DoD-2 `[test]` When the tag list contains non-version tags alongside one `vX.Y.Z` tag (e.g. `release`, `v1.2`, `v1.2.3-rc1`, `v1.2.3`), the version used is `1.2.3`.
- DoD-3 `[test]` With no tag, or only malformed tags (`1.2.3`, `v1.2`, `v1.2.3-rc1`, `vX.Y.Z`), `build.sh` exits non-zero, stderr mentions the `vX.Y.Z` form (contains `v` + `X.Y.Z` or an example like `v0.0.1`), and `docker` is never invoked.
- DoD-4 `[test]` With two matching version tags on HEAD, `build.sh` exits non-zero and `docker` is never invoked.
- DoD-5 `[test]` With `DOCKER_STORE` unset or empty, `build.sh` exits non-zero, stderr mentions `DOCKER_STORE`, and neither `docker` nor `git` side effects create anything in the store.
- DoD-6 `[test]` On success, `$DOCKER_STORE/rphelper/` is created if missing and contains `rphelper-latest.7z` (non-empty, containing the bytes the `docker save` stub emitted), `docker-compose.yml` identical to the repo's `docker-compose.prod.yml`, and `deploy.sh` identical to the repo's `deploy.sh`; no other files are left in the store dir.
- DoD-7 `[test]` A `DOCKER_STORE` with a trailing slash produces the same store layout as without one.
- DoD-8 `[test]` If `docker build` fails, `build.sh` exits non-zero and a pre-existing `rphelper-latest.7z` in the store is left byte-identical; no temp file remains in the store.
- DoD-9 `[test]` If `7z` (or `docker save`) fails, `build.sh` exits non-zero, a pre-existing `rphelper-latest.7z` is left byte-identical, and no temp file remains in the store.
- DoD-10 `[test]` A pre-existing `rphelper-latest.7z` with different content is fully replaced on success (its content equals the new `docker save` bytes — not an updated/merged archive).
- DoD-11 `[test]` `build.sh` resolves the repo root from its own location: invoked from an unrelated cwd, it builds with the script's directory as the `docker build` context and passes it to `git -C`.
- DoD-12 `[test]` `build.sh` invoked with any argument exits non-zero without invoking `docker`.

Deploy script:

- DoD-13 `[test]` Default invocation (no args) with store containing archive + compose and `.env` present: copies `<store>/docker-compose.yml` into the script dir, runs `7z x -so <store>/rphelper-latest.7z` piped into `docker load` (the load stub receives the archive bytes), creates `data/` in the script dir, then invokes `docker compose up -d`, `docker image prune -f`, `docker compose ps` in that order; exits 0.
- DoD-14 `[test]` `--images` loads the image but does not copy the compose file; `--config` copies the compose file but invokes no `7z` and no `docker load`; `--all` behaves as the default.
- DoD-15 `[test]` `--no-restart` invokes neither `docker compose up` nor `docker image prune`, still invokes `docker compose ps`, and does not require `.env`.
- DoD-16 `[test]` An unknown argument exits 1 with a usage message and invokes no `docker`.
- DoD-17 `[test]` `DOCKER_STORE` unset/empty → non-zero exit, message mentions `DOCKER_STORE`; store dir missing → non-zero exit; neither invokes `docker`.
- DoD-18 `[test]` Missing archive in `--images`/`--all` mode → non-zero exit, no `docker load`; missing store compose in `--config`/`--all` mode → non-zero exit.
- DoD-19 `[test]` Restart requested and no `.env` in the script dir → non-zero exit, message mentions `.env`, no `docker` invoked, and no `.env` is created.
- DoD-20 `[test]` `deploy.sh` resolves its deploy dir from its own location: invoked from an unrelated cwd, the compose copy and `data/` land next to the script and compose commands run with that dir as cwd.
- DoD-21 `[test]` A failing `docker load` (or `7z x`) makes `deploy.sh` exit non-zero and skip `docker compose up`.

Compose files and static checks:

- DoD-22 `[test]` `docker-compose.prod.yml` exists, references `image: iezious/rphelper:latest`, contains no `build:` key, and keeps `8193:80`, `env_file: .env`, `./data:/app/data`, the `curl -f` `/api/health` healthcheck, and `restart: unless-stopped` (the static checks formerly run against the old `docker-compose.yml` now run against it).
- DoD-23 `[test]` `docker-compose.dev.yml` no longer exists; `docker-compose.yml` exists and is the dev compose (has the `api` and `ui` services, no `iezious/rphelper` image), and its usage comment is `docker compose up` without `-f`.
- DoD-24 `[test]` `test_deployment_files.py`'s `SOURCE_FILES` covers `docker-compose.prod.yml`, `build.sh` and `deploy.sh` and drops `docker-compose.dev.yml`; none of the deployment source files (incl. `.env.example`, `backend/.gitignore`) mentions `docker-compose.dev.yml`; `.env.example` names `docker-compose.prod.yml`.
- DoD-25 `[test]` Both scripts start with a bash shebang and enable `set -euo pipefail`.
- DoD-26 `[manual/live]` `build.sh` and `deploy.sh` are committed with the executable bit (git mode `100755`).
- DoD-27 `[manual/live]` A repo-wide grep (excluding `docs/`) finds no remaining `docker-compose.dev.yml` reference.
- DoD-28 `[manual/live]` Real run: tag `v0.0.1`, `build.sh` produces a loadable archive in `$DOCKER_STORE/rphelper`; on the server `deploy.sh` loads it, `docker images` shows both `iezious/rphelper:latest` and `:0.0.1`, and the stack comes up healthy on :8193.
- DoD-29 `[manual/live]` `docker compose up` with the renamed dev compose starts the dev pair as before.
- DoD-30 `[manual/live]` Backend gates green: `<py> -m pytest`, `<py> -m mypy app`, `<py> -m ruff check .`.

## Out of scope

- Pushing to a registry; creating git tags; dirty-working-tree checks.
- `.env` templating or creation of any kind on the deploy server.
- A Windows `build.ps1` / `deploy.ps1`; CI.
- Changes to the `Dockerfile`, nginx or supervisord configs, `start.sh`, `start.ps1`.
- Content changes to the dev compose beyond the usage comment.
- Pruning old versioned images or old archives in the store beyond what `docker image prune -f` does.
- Editing `docs/architecture/` (recorded in `outcome.md`) or earlier plans' text that mentions `docker-compose.dev.yml`.
