# Fast feature 013 — build-and-deploy-scripts — outcome

Intended documentation changes, applied by the architect at finalization.

## `docs/architecture/deployment.md`

- **Section:** "Dev topology" — launch-path table and prose.
  **Change:** the third launch path is `docker-compose.yml` (renamed from
  `docker-compose.dev.yml`), started with plain `docker compose up`. "Dev-compose"
  wording stays, but the file name changes.
  **Reason:** the dev compose took the standard name so the local default is
  `docker compose up`; the prod compose moved to `docker-compose.prod.yml`.

- **Section:** "The app document at `/` — prod and dev" — dev mechanism paragraph
  listing the three dev launch paths.
  **Change:** `docker-compose.dev.yml` → `docker-compose.yml`.
  **Reason:** same rename.

- **Section:** "Prod topology" — Dockerfile paragraph and "Compose" block.
  **Change:** the prod compose is `docker-compose.prod.yml` and is
  **image-based** (`image: iezious/rphelper:latest`, no `build:`); it is never
  run from the repo, it is staged into the store as `docker-compose.yml` by
  `build.sh`. Drop or update the "Forward-looking; no feature has built an image
  yet" remark. The healthcheck invariant (status code, never the body) is
  unchanged and now lives in `docker-compose.prod.yml`.
  **Reason:** prod is deployed from a pre-built image, not built on the server.

- **Section:** new subsection under "Prod topology", e.g. "Build and deploy".
  **Change:** record the flow: `build.sh` (repo root) → requires exactly one
  `vMAJOR.MINOR.PATCH` tag on HEAD (via `git tag --points-at HEAD`; zero or
  several → fail), resolved **on the host** because `.dockerignore` excludes
  `.git`; tags the image `iezious/rphelper:latest` and `:<version without v>`;
  `docker save` of both refs piped to `7z`, written to a temp file in the store
  and renamed to `rphelper-latest.7z` only on success (a failed build never
  leaves a truncated archive; `7z a` on an existing archive would update rather
  than replace it); stages `docker-compose.yml` (from `docker-compose.prod.yml`)
  and `deploy.sh`. Store = `$DOCKER_STORE/rphelper` (env var required on both
  machines; build creates the dir, deploy requires it). `deploy.sh` mirrors
  BookWriter's `update.sh`: `--images|--config|--all`, `--no-restart`,
  `7z x -so | docker load`, compose copy, `data/`, `docker compose up -d`,
  `docker image prune -f`, `docker compose ps`.
  **Deliberate deviation from BookWriter:** no `.env`-from-`.env.example`
  templating; `deploy.sh` refuses to restart without `.env` instead. State why
  (secrets are hand-placed on the server; a template would start the stack with
  placeholder credentials).
  **Reason:** the build/deploy flow is deployment topology and otherwise lives
  only in the scripts.

- **Section:** "Configuration conventions" — ports-are-hardcoded bullet.
  **Change:** the list of places holding port literals names both
  `docker-compose.yml` (dev) and `docker-compose.prod.yml`.
  **Reason:** the file that held the prod port literal was renamed.

## `docs/architecture/quick-reference.md`

- **Section:** doc map, `deployment.md` row (line ~30).
  **Change:** `docker-compose.dev.yml` → `docker-compose.yml`; add "build and
  deploy (`build.sh` / `deploy.sh`, `$DOCKER_STORE/rphelper`, version from
  `vX.Y.Z` tag)" to the row's contents.
  **Reason:** rename + new subsection.

- **Section:** paths / commands block (wherever repo-root files are indexed).
  **Change:** list `build.sh`, `deploy.sh`, `docker-compose.yml` (dev),
  `docker-compose.prod.yml` (prod, image-based), archive name
  `rphelper-latest.7z`, image name `iezious/rphelper`.
  **Reason:** agent-first index of paths.

