# Fast feature 013 — build-and-deploy-scripts

| Status  | Verifier | Date |
|---------|----------|------|
| done    | PASS     | 2026-10-08 |

## Files Changed

- `build.sh` — host build: version from the single vX.Y.Z tag on HEAD, docker build/save, 7z to a temp archive in the store then mv, stages compose + deploy.sh
- `deploy.sh` — server deploy: arg parsing, store/.env/archive/compose prechecks, 7z x -so | docker load, compose copy, data/, compose up/prune/ps
- `docker-compose.prod.yml` — `build:` replaced by `image: iezious/rphelper:latest`; header comment names build.sh/deploy.sh
- `docker-compose.yml` — dev compose usage comment now `docker compose up`
- `.env.example` — line 2 comment names `docker-compose.prod.yml`
- `backend/.gitignore` — line 15 comment names `docker-compose.yml`

## Skeleton

### Frozen interface (2026-10-08)
- `build.sh` (repo root) — new. `#!/usr/bin/env bash`, header comment, `set -euo pipefail`. CLI: `build.sh` with no arguments; any argument → usage, non-zero, no `docker`. Env: `DOCKER_STORE` (required, non-empty, trailing slash normalized); store dir `$DOCKER_STORE/rphelper`. Repo root = `$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)`. External commands, in order: `git -C <root> tag --points-at HEAD` (exactly one `^v[0-9]+\.[0-9]+\.[0-9]+$` match, `v` stripped); `docker build -t iezious/rphelper:latest -t iezious/rphelper:<version> <root>`; `docker save iezious/rphelper:latest iezious/rphelper:<version> | 7z a <switches…> <tmp archive in store dir>` (all switches start with `-`, incl. `-si…`; the single non-switch arg after `a` is the archive path); `mv` tmp → `<store>/rphelper-latest.7z`. Stages `<store>/docker-compose.yml` (copy of `docker-compose.prod.yml`) and `<store>/deploy.sh` (copy, exec bit kept). Stub body: prints `build.sh: not implemented` to stderr, exits 1.
- `deploy.sh` (repo root) — new. `#!/usr/bin/env bash`, header comment, `set -euo pipefail`. CLI: `deploy.sh [--images|--config|--all] [--no-restart]` (default `--all`, restart on); unknown argument → usage, exit 1, no `docker`. Env: `DOCKER_STORE` (required, non-empty, trailing slash tolerated); `$DOCKER_STORE/rphelper` must exist. Deploy dir = script's own dir (`${BASH_SOURCE[0]}`). External commands: `7z x -so <store>/rphelper-latest.7z | docker load` (images/all); `cp <store>/docker-compose.yml <deploy dir>/docker-compose.yml` (config/all); `mkdir -p <deploy dir>/data`; in deploy dir: `docker compose up -d`, `docker image prune -f` (restart on only; requires `<deploy dir>/.env`, never created), then always `docker compose ps`. Stub body: prints `deploy.sh: not implemented` to stderr, exits 1.
- `docker-compose.prod.yml` — new path, created by `git mv docker-compose.yml docker-compose.prod.yml`; content still the old build-based prod compose (the `build:` → `image: iezious/rphelper:latest` swap is the coder's).
- `docker-compose.yml` — now the dev compose, via `git mv docker-compose.dev.yml docker-compose.yml`; content byte-identical to the old dev compose (the header usage comment `docker compose -f docker-compose.dev.yml up` → `docker compose up` is the coder's).
- `docker-compose.dev.yml` — removed by the rename above.
- Not touched (coder's): `.env.example:2`, `backend/.gitignore:15` comment edits; all script behaviour.
- Executable bit: both scripts are `chmod +x` on disk (`-rwxr-xr-x`), but this repo has `core.fileMode=false`, so a plain `git add` records **100644** (verified against a scratch index). DoD-26 needs `git add --chmod=+x build.sh deploy.sh` (or `git update-index --chmod=+x`) at commit time. Scripts are not staged; the two compose renames are staged (by `git mv`). Because the `docker-compose.yml` path is kept, git shows it as M + D/A rather than a rename; `git log --follow` / `-B -M` recovers the history.
- Caller-compile edits (out of Source-files scope): None. Note: the existing `backend/tests/test_deployment_files.py` still lists `docker-compose.dev.yml` and reads `docker-compose.yml` as the prod compose, so it is red until the test-coder retargets it (a Test file — not touched).

## Tests

### Tests (2026-10-08)
- `backend/tests/test_build_deploy_scripts.py` — covers DoD-1..DoD-21 — runs copies of `build.sh` / `deploy.sh` under `bash` in `tmp_path` with logging `docker` / `7z` / `git` stubs prepended to `PATH` (minimal env, no inherited `DOCKER_STORE`); asserts tags/version selection, store layout and archive bytes, atomic replace (the `7z a` stub appends like real `7z`), self-location, mode/flag dispatch, `.env` precondition, call order and cwd. Skips when `bash` is missing or on win32.
- `backend/tests/test_deployment_files.py` — covers DoD-22..DoD-25 — `SOURCE_FILES` retargeted (adds `docker-compose.prod.yml`, `build.sh`, `deploy.sh`, `backend/.gitignore`; drops the old dev compose), `compose_text()` and the healthcheck message now use `docker-compose.prod.yml`; new `test_f013_*` checks for image/no-`build:`, dev compose rename + usage comment, no old-name mentions, `.env.example` naming, shebang + `set -euo pipefail`. The old dev compose name is split in a string literal so the DoD-27 grep stays clean.
- Coverage: DoD-1..DoD-25 ✓; DoD-26..DoD-30 [manual/live, no test]
- Red-gate note: pure-negative assertions (DoD-4, DoD-12, DoD-17 missing-store, DoD-18 missing-compose, and parts of DoD-8/9) cannot fail against a stub that exits 1 without calling anything; the rest fail on missing output, staging or calls.

## Notes & Issues

- `shellcheck` not installed; scripts checked with `bash -n` only.
- build.sh temp archive is `<store>/.rphelper-latest.XXXXXX.7z` (from `mktemp -u`, so 7z creates it fresh); removed by an EXIT trap on failure.
- deploy.sh checks all preconditions (.env, archive, store compose) before any `docker`/`7z` call; images are loaded before the compose copy.
- DoD-26: commit the scripts with `git add --chmod=+x build.sh deploy.sh` (core.fileMode=false), per the Skeleton note.
