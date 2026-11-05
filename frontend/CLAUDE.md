# frontend

<!-- agent-ready:start -->

The React 19 + TypeScript + Vite frontend, built as four entry documents (`app`, `admin`, `login`, `bootstrap`) that call the backend same-origin under `/api/...`. TypeScript only; commands (build, test, typecheck) are in the root `CLAUDE.md`.

## Glossary

**Subfolders:**
- `dev/` — dev-server-only helpers wired by `vite.config.ts`: entry routing that mirrors prod nginx, and the proxy / request logs.
- `src/` — the sources, one folder per entry plus `shared/` and the two stylesheets.
- `tests/` — the Vitest suite, mirroring `src/` plus cross-cutting guards.

**Files:**
- `.gitignore` — keeps `node_modules`, build output and test / Vite caches out of git.
- `package-lock.json` — the npm lockfile.
- `package.json` — the npm manifest: dependencies and the `build` / `test` / `typecheck` / `dev` scripts.
- `tsconfig.json` — TypeScript config for `src` and `tests`.
- `tsconfig.node.json` — TypeScript config for the Node-side `vite.config.ts`.
- `vite.config.ts` — the multi-entry Vite build, the Vitest config and the dev server / `/api` proxy on port 8193.

See also: docs/architecture/frontend-structure.md

<!-- agent-ready:end -->
