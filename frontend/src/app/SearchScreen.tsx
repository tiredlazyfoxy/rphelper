// The results page at `/search` (feature 029, step 005): the page's own search box (prefilled
// from `q`, focused on every arrival — D9), the five groups in UC-059 order with the archived
// and disabled markings, each row a link to its hit's target, and the inline loading / empty /
// failure states (U1, U3, U4, D7). Failures are shown here, never notified.
//
// The eleven module constants below are the frozen interface's literals (status.md
// `## Skeleton`, step 005) and are private: nothing but `SearchScreen` leaves this module, and
// the groups, rows and markings are expressed in Mantine props only — no stylesheet, no class
// name (D7).
import type * as React from "react";
import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react-lite";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import {
  Anchor,
  Badge,
  Box,
  Button,
  Group,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";

import type { MemoScope } from "./memosApi";
import { formatSessionStart } from "./sessionLabel";
import {
  SearchState,
  characterTarget,
  entryTarget,
  hasNoHits,
  loadSearch,
  memoTarget,
  searchHref,
  sessionTarget,
  setupTarget,
} from "./searchState";

/** The URL search parameter the query text lives in (D8). */
const QUERY_PARAM = "q";

/** The page box's accessible name — the literal the tests query the box by. */
const SEARCH_BOX_LABEL = "Search query";

/**
 * The five group headings, keyed by their `MySearchResults` key. Declaration order **is** the
 * render order (UC-059, US-075.AC-1), and each heading is also its region's accessible name.
 * Note that `memos` reads `Notes`.
 */
const GROUP_HEADINGS = {
  characters: "Characters",
  setups: "Setups",
  sessions: "Sessions",
  entries: "Entries",
  memos: "Notes",
} as const;

/** A note row's level label, by the hit's `scope` (US-119: a level label, never a title). */
const MEMO_LEVEL_LABELS: Record<MemoScope, string> = {
  user: "User note",
  character: "Character note",
  setup: "Setup note",
  session: "Session note",
};

/** The archived marking's badge text (U3, D7) — the tree's and session header's own literal. */
const ARCHIVED_BADGE = "Archived";

/** The disabled note's badge text (US-137.AC-2, D7). */
const DISABLED_BADGE = "Disabled";

/** Joins a row's two secondary parts (`<character> · <setup>`): U+00B7 between two spaces. */
const SECONDARY_SEPARATOR = " · ";

/** The `"loading"` state's only text. The ellipsis is U+2026, one character. */
const LOADING_TEXT = "Searching…";

/** The `"ready"` state's text when all five groups are empty. */
const NO_HITS_TEXT = "Nothing found.";

/** The `"failed"` state's heading; the envelope's own message is shown under it (U1). */
const FAILURE_HEADING = "Search failed";

/** The `"failed"` state's retry control, which re-runs the load for the current `q`. */
const RETRY_LABEL = "Retry";

type SearchGroupProps = {
  /** The group's heading text, which is also its region's accessible name. */
  heading: string;
  /** The group's rows, each one a `SearchRow` list item. */
  children: React.ReactNode;
};

/**
 * One group: a region named by its heading, the visible heading, and the list of its rows. The
 * five groups share this wrapper (the region is identical for all five) and differ only in the
 * rows their call sites map. Module-private, like `SearchRow`.
 */
function SearchGroup(props: SearchGroupProps): React.JSX.Element {
  return (
    <Box component="section" aria-label={props.heading}>
      <Stack gap="xs">
        <Title order={3}>{props.heading}</Title>
        <Box component="ul" m={0} p={0} style={{ listStyle: "none" }}>
          {props.children}
        </Box>
      </Stack>
    </Box>
  );
}

type SearchRowProps = {
  /** The hit's target (step 004): the row's link leads exactly here. */
  href: string;
  /** The row's primary first line, inside the link. */
  primary: string;
  /** The dimmed second line, already joined, also inside the link; absent when the kind has none. */
  secondary?: string;
  /** `ARCHIVED_BADGE` or `DISABLED_BADGE` beside the link; absent when the row wears neither. */
  badge?: string;
  /** Dims the primary text: the archived idiom (U3) and the disabled note's first half (D7). */
  dimmed?: boolean;
  /** Strikes the primary text through: the note wall's disabled idiom (D7). */
  struck?: boolean;
};

/**
 * One result row: a list item holding the link to the hit's target — whose content is **both**
 * the row's lines, the primary one and the dimmed secondary one — and the optional badge beside
 * it. Both lines belong inside the link because the whole of them is what identifies the row: a
 * session has no name, so its character and setup live in the secondary line alone, and a link
 * carrying only the formatted start could be neither recognised nor activated by that label. The
 * tree's `NavLink` row (`CharacterTree.tsx`) is the same shape — `label` and `description` inside
 * the anchor, the `Archived` badge an outside sibling — and it is the better accessible name.
 * Each line stays its own text node; the badge stays outside the link (U3, D7). Snippets arrive
 * here as plain strings and are rendered as text, never as markdown (D7).
 */
function SearchRow(props: SearchRowProps): React.JSX.Element {
  const { href, primary, secondary, badge, dimmed = false, struck = false } = props;
  return (
    <Box component="li">
      <Group gap="xs" wrap="nowrap" align="flex-start">
        <Anchor
          component={Link}
          to={href}
          display="block"
          flex={1}
          miw={0}
          c={dimmed ? "dimmed" : undefined}
        >
          {/* The markings sit on the line they mark, so the secondary line keeps the dimmed
              small styling it has everywhere and is never struck through. */}
          <Text
            component="span"
            display="block"
            c={dimmed ? "dimmed" : undefined}
            td={struck ? "line-through" : undefined}
          >
            {primary}
          </Text>
          {secondary !== undefined && (
            <Text component="span" display="block" size="sm" c="dimmed">
              {secondary}
            </Text>
          )}
        </Anchor>
        {badge !== undefined && (
          <Badge color="gray" variant="light" size="sm">
            {badge}
          </Badge>
        )}
      </Group>
    </Box>
  );
}

/**
 * The `/search` centre. Takes **no props**: it is the page store's owner (orchestrator
 * decision 10), so it creates its one `SearchState` here with `useState` and `App` passes it
 * nothing.
 *
 * The box is a `TextInput` named `SEARCH_BOX_LABEL` whose value is local while typing and is
 * reset from `q` on every change of it; Enter navigates in-entry to `searchHref(value)`. It is
 * focused on every arrival at `/search` (D9). Each change of `q` runs `loadSearch` with a fresh
 * `AbortController`; a blank `q` makes no request. `"idle"` renders only the box, `"loading"`
 * adds `LOADING_TEXT`, `"failed"` adds `FAILURE_HEADING` with the envelope's own message and a
 * `RETRY_LABEL` control, `"ready"` adds either `NO_HITS_TEXT` or the groups.
 */
export const SearchScreen = observer(function SearchScreen(): React.JSX.Element {
  // Decision 10: the page owns its state - created here, per mount, never a prop, never a
  // module singleton, so every fresh arrival at `/search` starts `"idle"`.
  const [state] = useState(() => new SearchState());
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const boxRef = useRef<HTMLInputElement>(null);
  const controllerRef = useRef<AbortController | null>(null);
  // The query's home is the URL (D8); the box follows it, never the other way round.
  const query = searchParams.get(QUERY_PARAM) ?? "";
  const [text, setText] = useState(query);

  // The box's value is component-local while typing, and is set from `q` whenever `q` changes -
  // including the arrival from the tree's input, which carries the same text.
  useEffect(() => {
    setText(query);
  }, [query]);

  // D9: focused on every navigation that lands on `/search`, keyed on the location's identity -
  // a second navigation to the same path gets a new key, so a rail press while already here
  // focuses the box again. Keyed on mount alone it would not.
  useEffect(() => {
    boxRef.current?.focus();
  }, [location.key]);

  // One load per `q`, with a fresh controller each time: the previous one is aborted before the
  // next starts, and the one alive at unmount is aborted too. A blank `q` issues no request at
  // all - `loadSearch` short-circuits it back to idle (D1, U4).
  useEffect(() => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    void loadSearch(state, query, controller.signal);
    return () => {
      controller.abort();
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, [state, query]);

  // U1: the failure is the whole page's, so `Retry` is one more load of the same `q`.
  const retry = (): void => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    void loadSearch(state, query, controller.signal);
  };

  // `GROUP_HEADINGS`' declaration order is UC-059's render order (US-075.AC-1), and a group
  // with no hits is not rendered at all. The rows stay inline per group, each `.map` over a
  // statically known hit type with that kind's own `*Target` helper (step 004).
  const renderGroups = (): React.JSX.Element | null => {
    const results = state.results;
    if (state.status !== "ready" || results === null || hasNoHits(state)) {
      return null;
    }
    return (
      <>
        {results.characters.length > 0 && (
          <SearchGroup heading={GROUP_HEADINGS.characters}>
            {results.characters.map((hit) => (
              <SearchRow
                key={hit.id}
                href={characterTarget(hit)}
                primary={hit.name}
                badge={hit.archived ? ARCHIVED_BADGE : undefined}
                dimmed={hit.archived}
              />
            ))}
          </SearchGroup>
        )}
        {results.setups.length > 0 && (
          <SearchGroup heading={GROUP_HEADINGS.setups}>
            {results.setups.map((hit) => (
              <SearchRow
                key={hit.id}
                href={setupTarget(hit)}
                primary={hit.name}
                secondary={hit.character_name}
                badge={hit.archived ? ARCHIVED_BADGE : undefined}
                dimmed={hit.archived}
              />
            ))}
          </SearchGroup>
        )}
        {results.sessions.length > 0 && (
          <SearchGroup heading={GROUP_HEADINGS.sessions}>
            {results.sessions.map((hit) => (
              <SearchRow
                key={hit.id}
                href={sessionTarget(hit)}
                primary={formatSessionStart(hit.created_at)}
                // The setup's name joins the character's only when the session has one.
                secondary={
                  hit.setup_name === null
                    ? hit.character_name
                    : `${hit.character_name}${SECONDARY_SEPARATOR}${hit.setup_name}`
                }
                badge={hit.archived ? ARCHIVED_BADGE : undefined}
                dimmed={hit.archived}
              />
            ))}
          </SearchGroup>
        )}
        {results.entries.length > 0 && (
          <SearchGroup heading={GROUP_HEADINGS.entries}>
            {results.entries.map((hit) => (
              <SearchRow
                key={hit.id}
                href={entryTarget(hit)}
                primary={hit.snippet}
                secondary={`${hit.character_name}${SECONDARY_SEPARATOR}${formatSessionStart(
                  hit.session_created_at,
                )}`}
              />
            ))}
          </SearchGroup>
        )}
        {results.memos.length > 0 && (
          <SearchGroup heading={GROUP_HEADINGS.memos}>
            {results.memos.map((hit) => (
              // US-119: a level label, never a title. US-137.AC-2 / D7: a disabled note wears
              // the wall's idiom plus the badge; an enabled or forced one wears neither.
              <SearchRow
                key={hit.id}
                href={memoTarget(hit)}
                primary={hit.snippet}
                secondary={MEMO_LEVEL_LABELS[hit.scope]}
                badge={hit.is_enabled ? undefined : DISABLED_BADGE}
                dimmed={!hit.is_enabled}
                struck={!hit.is_enabled}
              />
            ))}
          </SearchGroup>
        )}
      </>
    );
  };

  return (
    <Stack gap="lg">
      <TextInput
        ref={boxRef}
        label={SEARCH_BOX_LABEL}
        value={text}
        onChange={(event) => {
          setText(event.currentTarget.value);
        }}
        onKeyDown={(event) => {
          if (event.key !== "Enter") {
            return;
          }
          // U4: Enter is a navigation, not a filter - the URL carries the query.
          void navigate(searchHref(text));
        }}
      />
      {state.status === "loading" && <Text>{LOADING_TEXT}</Text>}
      {/* U1: the failure is shown here, inline and whole-page, and nothing is notified. */}
      {state.status === "failed" && (
        <Stack gap="xs" align="flex-start">
          <Title order={3}>{FAILURE_HEADING}</Title>
          {state.failure !== null && <Text>{state.failure}</Text>}
          <Button variant="default" onClick={retry}>
            {RETRY_LABEL}
          </Button>
        </Stack>
      )}
      {hasNoHits(state) && <Text>{NO_HITS_TEXT}</Text>}
      {renderGroups()}
    </Stack>
  );
});
