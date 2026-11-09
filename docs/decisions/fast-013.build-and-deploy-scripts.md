# Decisions — fast-013.build-and-deploy-scripts
**Stage:** — · **Feature:** fast/013.build-and-deploy-scripts

`build.sh` and `deploy.sh`: building the prod image on a developer machine,
shipping it through a shared store, and starting it on the server from a
pre-built image. The contract is `deployment.md`'s "Prod topology" → "Build and
deploy". User decisions 1–4 are DEC-F013-1, -3, -4 and -5. Written at
finalization (2026-11-09).

### DEC-F013-1 — The version comes from exactly one `vX.Y.Z` tag on HEAD
- **Status:** accepted
- **Stage:** — · **Feature:** fast/013.build-and-deploy-scripts · **Step:** —
- **Date:** 2026-10-08 · **Decided by:** user
- **Question:** What version does a build carry, and where is it resolved?
- **Decision:** HEAD must carry exactly one tag matching `v<MAJOR>.<MINOR>.<PATCH>` (digits only, e.g. `v0.0.1`). The `v` is stripped and the image is tagged both `iezious/rphelper:latest` and `iezious/rphelper:<version>` (e.g. `:0.0.1`). No matching tag fails the build with a clear error. The tag is resolved by `build.sh` on the host.
- **Reason:** A shipped image must name a release; resolving on the host is forced, because `.dockerignore` excludes `.git` and nothing inside the image build can see tags.
- **Lands in:** `build.sh`
- **Cites:** `deployment.md` "Build and deploy"

### DEC-F013-2 — `git tag --points-at HEAD`; two matching tags fail as ambiguous
- **Status:** accepted
- **Stage:** — · **Feature:** fast/013.build-and-deploy-scripts · **Step:** —
- **Date:** 2026-10-08 · **Decided by:** planner
- **Question:** Which git command detects the version tag?
- **Decision:** `git -C <repo root> tag --points-at HEAD`, filtered to the `v<d>.<d>.<d>` pattern. Zero matches fail; two or more fail as ambiguous.
- **Reason:** It lists every tag on HEAD, so a stray non-version tag cannot hide the version tag, and its newline-separated output is trivially stubbed in tests. Failing on two never guesses which version to ship.
- **Rejected:** `git describe --exact-match` — reports one tag, which may be the stray one.
- **Lands in:** `build.sh`

### DEC-F013-3 — The store is `$DOCKER_STORE/rphelper`
- **Status:** accepted
- **Stage:** — · **Feature:** fast/013.build-and-deploy-scripts · **Step:** —
- **Date:** 2026-10-08 · **Decided by:** user (store); planner (trailing-slash normalization)
- **Question:** Where does the build leave its artifacts for the server?
- **Decision:** `$DOCKER_STORE/rphelper`. `DOCKER_STORE` must be set on both machines; both scripts fail when it is unset or empty. A trailing slash is normalized away (paths and messages show `/mnt/nas/docker/rphelper`, not `//rphelper`). `build.sh` creates the store directory if missing; `deploy.sh` requires it to exist.
- **Reason:** The user's existing shared-store convention (the value on their machines ends in a slash). A deploy against a missing store is a misconfiguration to report, not a directory to create.
- **Lands in:** `build.sh`, `deploy.sh`
- **Cites:** `deployment.md` "Build and deploy"

### DEC-F013-4 — Compose restructure: dev takes the standard name; prod is image-based
- **Status:** accepted
- **Stage:** — · **Feature:** fast/013.build-and-deploy-scripts · **Step:** —
- **Date:** 2026-10-08 · **Decided by:** user
- **Question:** Which compose file is which once prod is deployed from a pre-built image?
- **Decision:** `docker-compose.dev.yml` is renamed `docker-compose.yml`, so the local default is plain `docker compose up`. The old `build:`-based prod compose is removed. A new `docker-compose.prod.yml` carries the old prod content — `ports: ["8193:80"]`, `env_file: .env`, `./data:/app/data`, the status-only healthcheck **with its comment about never asserting the body**, `restart: unless-stopped` — with `image: iezious/rphelper:latest` in place of `build:`. `build.sh` copies it into the store under the name `docker-compose.yml`, because on the server it is the only compose file.
- **Reason:** Prod is never built on the server, so its compose has no business carrying a `build:` key; each machine gets the standard name for the compose it actually runs.
- **Supersedes:** the compose layout of DEC-F001-7 (prod at `docker-compose.yml`, dev at `docker-compose.dev.yml`).
- **Lands in:** `docker-compose.yml`, `docker-compose.prod.yml`, `build.sh`
- **Cites:** `deployment.md` "Dev topology", "Prod topology" (Compose)

### DEC-F013-5 — No `.env` templating; deploy refuses to restart without `.env`
- **Status:** accepted
- **Stage:** — · **Feature:** fast/013.build-and-deploy-scripts · **Step:** —
- **Date:** 2026-10-08 · **Decided by:** user
- **Question:** BookWriter's deploy script creates `.env` from `.env.example` when missing. Does RPHelper's?
- **Decision:** No. `deploy.sh` never writes `.env`; it refuses to restart the stack when `.env` is absent, with a clear message.
- **Reason:** Secrets are placed on the server by hand; a template would start the stack with placeholder credentials. Compose's `env_file: .env` would fail anyway, and an early message beats a compose error.
- **Rejected:** BookWriter's templating.
- **Lands in:** `deploy.sh`
- **Cites:** `deployment.md` "Build and deploy" (the deliberate deviation)

### DEC-F013-6 — The archive is written to a temp file in the store and renamed on success
- **Status:** accepted
- **Stage:** — · **Feature:** fast/013.build-and-deploy-scripts · **Step:** —
- **Date:** 2026-10-08 · **Decided by:** planner
- **Question:** How is the image archive written so deploy never loads a bad one?
- **Decision:** `docker save` is given both image references and piped to `7z a`, writing to a fresh temporary name inside the store directory (`.rphelper-latest.XXXXXX.7z`, from `mktemp -u`); only after the pipe succeeds is it moved to `rphelper-latest.7z`. An `EXIT` trap removes the temp file on failure.
- **Reason:** A failed build must never leave a truncated archive where deploy will load it; and `7z a` onto an existing archive updates it rather than replacing it, so writing straight onto the last build's archive would be wrong even on success. The temp file sits in the store so the final move is a same-filesystem rename. Both references are saved so `docker load` restores `:latest` and `:<version>`.
- **Lands in:** `build.sh`

### DEC-F013-7 — `deploy.sh` mirrors BookWriter's `update.sh`
- **Status:** accepted
- **Stage:** — · **Feature:** fast/013.build-and-deploy-scripts · **Step:** —
- **Date:** 2026-10-08 · **Decided by:** user (reference shape); planner (ordering)
- **Question:** What does the deploy script do, and in what order?
- **Decision:** `--images | --config | --all` (default `all`) plus `--no-restart`; an unknown argument prints usage and exits 1. Every precondition — among them `DOCKER_STORE` set, the store directory present, and `.env` present when restarting — is checked before any docker call. `images`/`all` loads with `7z x -so <archive> | docker load`, before `config`/`all` copies `<store>/docker-compose.yml` next to the script; then `mkdir -p data`, `cd` to the script's directory, and when restarting `docker compose up -d` then `docker image prune -f`; finally `docker compose ps`. `build.sh` stages `deploy.sh` into the store beside the archive and the compose file.
- **Reason:** One deploy shape across the user's two projects; checking everything first means a refused deploy changes nothing, and loading images before the compose is copied means a new compose never points at an image that is not there yet.
- **Lands in:** `deploy.sh`, `build.sh`
- **Cites:** `deployment.md` "Build and deploy"

### DEC-F013-8 — Script conventions: strict mode, self-location, offline tests
- **Status:** accepted
- **Stage:** — · **Feature:** fast/013.build-and-deploy-scripts · **Step:** —
- **Date:** 2026-10-08 · **Decided by:** planner
- **Question:** How are the two scripts written and tested?
- **Decision:** `#!/usr/bin/env bash` and `set -euo pipefail` in both, so a failing `docker save` or `7z` inside a pipe aborts the script. Each resolves its own directory from `${BASH_SOURCE[0]}` (the `start.sh` style): `build.sh` treats it as the repo root (build context, git `-C` target, source of `docker-compose.prod.yml` and `deploy.sh`), `deploy.sh` as the deploy directory. Backend tests run them as `bash <path>` against `tmp_path` with stub `docker`, `7z` and `git` prepended to `PATH`, offline, skipping when `bash` is absent; they do not depend on the executable bit (which git does record as `100755`).
- **Reason:** `pipefail` is what makes a pipe's failure a script failure; self-location makes the scripts independent of the caller's working directory and testable from a copy in a temp directory; the backend suite blocks the network and caps each test at 60 s.
- **Lands in:** `build.sh`, `deploy.sh`, `backend/tests/` (the script tests)
