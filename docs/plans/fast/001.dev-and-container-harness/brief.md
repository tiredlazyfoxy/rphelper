# fast/001.dev-and-container-harness — Dev and container harness
<!-- roadmap:start -->
- **Stage:** 001.instance · **Track:** fast · **Size:** S
- **Depends on:** `001.backend-foundation`, `002.frontend-foundation`

## Definition
Makes the two topologies real so nobody discovers the production shape late. After this feature a developer starts the backend and the UI in two terminals from one script, and an operator brings the whole thing up as one container on one published port with a healthcheck that answers only when the entire chain does. Every nginx directive the streaming path will later depend on is already in place, in both the dev-compose and production configs.

## Scope
**In:**
- `start.ps1` with its app and ui invocations
- the two-stage Dockerfile
- `docker-compose.yml` with the 8193-to-80 publish, the data volume, the env file and the health check against `/api/health`
- the `supervisord` config
- both nginx configs with the per-entry SPA fallbacks, the `/api/` proxy including HTTP/1.1, the cleared hop-by-hop connection header, buffering and cache disabled, the 300s read timeout and the 64m body limit, plus the asset cache-control blocks

**Out:**
- TLS in any form
- metrics or alerting
- the non-buffering response header the application itself asserts, which lands with `019`

## Open questions for the planner
- Sized S on the grounds that all six artifacts are configuration with no branching logic and no test surface of their own. If the harvest disagrees — six files spanning both the dev and the production topology is close to the fast track's ceiling — `/fast-feature` should promote it to `/planner` rather than stretching the pass.
<!-- roadmap:end -->
