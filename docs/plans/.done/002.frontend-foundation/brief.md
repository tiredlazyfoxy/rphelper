# 002.frontend-foundation — Frontend foundation
<!-- roadmap:start -->
- **Stage:** 001.instance · **Track:** multi-step · **Size:** M
- **Depends on:** —

## Definition
Stands the four-entry Vite build up with all four documents present but empty, so every later frontend feature has an entry to land in and a shared client to call through. After this feature each of `/bootstrap`, `/login`, `/admin` and `/` loads its own document, calls same-origin `/api`, and renders a Mantine-themed shell. It fixes the conventions that are invisible to fix later: ids are strings everywhere, per-page MobX store classes passed as props with no React context, mutations are never optimistic, and the two hand-written stylesheets are the only ones there will ever be.

## Scope
**In:**
- `vite.config.ts` with four `rollupOptions.input` entries and the `/api` dev proxy
- the four entry documents and their in-entry routers
- the API client with typed-error decoding
- `global.css` resets and `shell.css` as an empty declared file
- the Mantine theme
- the shared `IconButton` wrapper and the icon sizing convention
- the MobX per-page-store and draft-form conventions
- the `@mantine/notifications` provider for transient failure reasons only
- the TypeScript rule that an `id: number` is a defect

**Out:**
- any page content in any entry
- the admin gate and `AppShell` (`005`)
- the workspace grid (`008`)
- the SSE consumer (`019`)
- the markdown editor (`015`)

## Open questions for the planner
- Whether the four entries share a `src/shared/` folder or duplicate the client, given `overview.md` requires the roleplayer's bundle to carry no administrative code.
- Whether the typed-error decoder lives in the client or in each store.
<!-- roadmap:end -->
