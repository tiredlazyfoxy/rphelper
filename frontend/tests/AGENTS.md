# tests

<!-- agent-ready:start -->

The Vitest suite for the frontend: one subfolder per entry mirroring `src/`, plus cross-cutting guards over the build configuration, conventions and dev-server helpers.

## Glossary

**Subfolders:**
- `admin/` — tests for the `admin` entry.
- `app/` — tests for the `app` entry (workspace, stream, composer, notes, search, settings).
- `bootstrap/` — tests for the `bootstrap` entry.
- `login/` — tests for the `login` entry.
- `shared/` — tests for the shared modules.

**Files:**
- `adminPrivacyAudit.test.ts` — the `admin` entry's half of the privacy-isolation audit.
- `build-config.test.ts` — build configuration, package manifest, tsconfigs and the TypeScript-only rule.
- `conventions.test.ts` — convention guards over `frontend/src`.
- `entries.test.tsx` — the four entry documents and their routers.
- `entry-routing.test.ts` — the Vite dev-server root routing (`dev/entryRouting.ts`).
- `harness.test.ts` — proves the Vitest harness is live.
- `ids-are-strings.test.ts` — guard that ids are typed as strings, never numbers.
- `proxy-log.test.ts` — the Vite dev `/api` proxy request log.
- `request-log.test.ts` — the Vite dev-server request log.
- `setup.ts` — Vitest setup module (jest-dom matchers), not a test.
- `stylesheets.test.ts` — the two hand-written stylesheets.

See also: docs/architecture/frontend-structure.md

<!-- agent-ready:end -->
