# Fast feature 013 — build-and-deploy-scripts — context

No `brief.md`; no backlog item. The request is the user's own ("prepare the build
and deploy script"), with the decisions below confirmed by the user through the
orchestrator.

## What exists today

- `Dockerfile` (repo root) — the two-stage all-in-one image (`deployment.md`,
  "Prod topology"). Its build context is the repo root; `.dockerignore` excludes
  `.git`, so **nothing inside the image build can see git tags** — the version
  must be resolved on the host, by `build.sh`.
- `docker-compose.yml` (repo root) — today the **prod** compose, `build:`-based:
  service `rphelper`, `ports: ["8193:80"]`, `env_file: .env`,
  `./data:/app/data`, the `curl -f http://localhost/api/health` status-only
  healthcheck **with its comment about never asserting the body**,
  `restart: unless-stopped`.
- `docker-compose.dev.yml` (repo root) — the dev compose (`api` in
  `ghcr.io/astral-sh/uv`, `ui` in `node:22`, repo bind-mounted, 8193 published on
  `api`). Its header usage comment reads
  `docker compose -f docker-compose.dev.yml up`.
- `start.sh` — style reference for shell scripts: `#!/usr/bin/env bash`, a
  comment header, resolves its own directory from `${BASH_SOURCE[0]}`.
- `.env.example:2` — comment "Prod: docker-compose.yml reads…".
- `backend/.gitignore:15` — comment "# Container venv (docker-compose.dev.yml)".
- `.gitignore` already ignores `*.7z`.
- `backend/tests/test_deployment_files.py` — static text checks over deployment
  files ("nothing is executed"): a `SOURCE_FILES` list that currently includes
  `docker-compose.dev.yml`, and a `compose_text()` helper that reads
  `docker-compose.yml` (the prod compose today).
- No git tags exist in the repo yet.

## Reference — the sibling project's deploy script

BookWriter's `update.sh` (supplied by the user) is the shape `deploy.sh`
mirrors: `--images | --config | --all` (default `all`) plus `--no-restart`;
unknown argument prints usage and exits 1; requires `$DOCKER_STORE`; store dir
`$DOCKER_STORE/<project>` must exist; `images`/`all` loads the archive with
`7z x -so <archive> | docker load`; `config`/`all` copies
`<store>/docker-compose.yml` next to the script; `mkdir -p data`; `cd` to the
script dir; when restarting, `docker compose up -d` then `docker image prune -f`;
finally `docker compose ps`.

**Deliberate divergence:** BookWriter's `.env`-from-`.env.example` templating is
**dropped** (user decision). RPHelper's `deploy.sh` never writes `.env`; it
refuses to restart when `.env` is missing, because compose's `env_file: .env`
would fail anyway and a clear early message beats a compose error.

## User-confirmed decisions (binding)

1. **Version from tag.** HEAD must carry exactly one tag matching
   `v<MAJOR>.<MINOR>.<PATCH>` (digits only, e.g. `v0.0.1`). The `v` is stripped:
   the image is tagged `iezious/rphelper:latest` **and**
   `iezious/rphelper:0.0.1`. No matching tag → build fails with a clear error.
2. **Store.** `$DOCKER_STORE` (set on both machines; the user's value is
   `/mnt/nas/docker/` **with a trailing slash**). Store dir =
   `$DOCKER_STORE/rphelper`. Both scripts fail when `DOCKER_STORE` is unset or
   empty. Build creates the store dir if missing; deploy requires it to exist.
3. **Compose restructure.** `docker-compose.dev.yml` → `docker-compose.yml`
   (the dev compose takes the standard name; its usage comment becomes
   `docker compose up`). The old build-based prod compose is removed.
   A new `docker-compose.prod.yml` carries the old prod content with
   `image: iezious/rphelper:latest` in place of `build:`. `build.sh` stages it
   into the store **under the name `docker-compose.yml`** — on the deploy server
   it is the only compose, so it takes the standard name.
4. **No `.env` templating** in deploy.

## Planner decisions (this plan)

- **Version detection command:** `git -C <repo root> tag --points-at HEAD`,
  filtered to the `v<d>.<d>.<d>` pattern. Chosen over `describe --exact-match`
  because it sees *every* tag on HEAD (a stray non-version tag cannot hide the
  version tag) and because its output — a newline-separated tag list — is
  trivially stubbed in tests. Zero matching tags → fail; **two or more** matching
  tags → fail as ambiguous (never guess which version to ship).
- **Atomic archive:** the archive is written to a fresh temporary location
  **inside the store dir** (same filesystem, so the final `mv` is a rename) and
  only moved to `rphelper-latest.7z` after `docker save | 7z a` succeeded; the
  temp is removed on failure. Two reasons: a failed build must never leave a
  truncated archive where deploy will load it, and `7z a` onto an **existing**
  archive *updates* it rather than replacing it, so writing straight onto last
  build's `rphelper-latest.7z` would be wrong even on success.
- **Both tags in the archive:** `docker save` is given both image references so
  `docker load` on the server restores `:latest` and `:<version>`.
- **Self-location:** each script resolves its own directory from
  `${BASH_SOURCE[0]}`. `build.sh` treats that directory as the repo root (build
  context, git `-C` target, source of `docker-compose.prod.yml` and `deploy.sh`);
  `deploy.sh` treats it as the deploy directory. This is also what makes both
  scripts testable from a copy in a temp directory.
- **Strict mode:** `set -euo pipefail` in both, so a failing `docker save` or
  `7z` inside a pipe aborts the script.
- **`DOCKER_STORE` trailing slash** is normalized away (messages and paths show
  `/mnt/nas/docker/rphelper`, not `//rphelper`).

## Test constraints

- Backend pytest suite: parallel (`-n auto`), 60s per-test limit, conftest blocks
  non-loopback network. The script tests must be offline and fast.
- Script tests execute the scripts with `bash` via `subprocess` against
  `tmp_path`, with stub `docker`, `7z` and `git` executables **prepended** to
  `PATH` (the rest of `PATH` kept so coreutils resolve). Skip when
  `shutil.which("bash")` is `None`.
- Tests invoke scripts as `bash <path>` — they do not depend on the executable bit.

## Architecture references

- `docs/architecture/deployment.md` — "Dev topology" (launch-path table names
  `docker-compose.dev.yml`), "Prod topology" (Dockerfile, Compose block,
  healthcheck invariant — **must survive the move to `docker-compose.prod.yml`
  verbatim in spirit and comment**), "The app document at `/`" (names
  `docker-compose.dev.yml` as a dev launch path), "Configuration conventions"
  (ports are hardcoded literals in `docker-compose.yml`).
- `docs/architecture/quick-reference.md` — doc map row for `deployment.md` names
  `docker-compose.dev.yml`.
