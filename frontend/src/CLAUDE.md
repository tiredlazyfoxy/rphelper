# src

<!-- agent-ready:start -->

The frontend sources, one folder per Vite entry document plus the code they share, and the only two hand-written stylesheets.

## Glossary

**Subfolders:**
- `admin/` — the `admin` entry: administrator shell with the users, LLM servers and database pages.
- `app/` — the `app` entry: the roleplayer's workspace (shell, characters, sessions, stream and composer, notes, search, settings).
- `bootstrap/` — the `bootstrap` entry: first-run create-administrator and restore-from-export.
- `login/` — the `login` entry: the login page.
- `shared/` — code every entry shares: the API client and errors, SSE reader, providers and theme, current user, notifications, shared components.

**Files:**
- `global.css` — the global resets stylesheet.
- `shell.css` — the `app` workspace's layout stylesheet (grid, nav rail width, the 820px threshold).

See also: docs/architecture/frontend-structure.md

<!-- agent-ready:end -->
