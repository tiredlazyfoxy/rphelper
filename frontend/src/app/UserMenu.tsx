// The user menu at the foot of the left column (008 context.md D6): an upward-opening
// Mantine `Menu` whose trigger is the avatar plus, when the column is expanded, the
// username. Holds no MobX state — the menu's open flag is Mantine's own — so it is a plain
// component, not an `observer`. The signed-in user arrives as a prop, never through context.
import type * as React from "react";
import { useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Avatar, Group, Menu, Text, UnstyledButton } from "@mantine/core";
import {
  IconDownload,
  IconLogout,
  IconSettings,
  IconShield,
  IconUpload,
} from "@tabler/icons-react";

import type { CurrentUser } from "../shared/currentUser";
import { ownDataExportPath, runExport } from "./exportDownloads";
import { runOwnedImport } from "./importUploads";
import { logOut } from "./logout";
import type { CharactersState } from "./charactersState";
import type { SessionsState } from "./sessionsState";

/** Inline-control sizing from `ui-conventions.md`; stroke 1.5 is the one visual weight. */
const ITEM_ICON_SIZE = 16;
const ITEM_ICON_STROKE = 1.5;

const SETTINGS_PATH = "/settings";
/** Another entry and another document, so a real anchor — never a router `Link` (D6). */
const ADMIN_HREF = "/admin";

/**
 * 031 007: the file types the own-data import offers. An export is a `.json` document, and
 * both the extension and the media type are listed so a picker on either platform filters.
 */
const IMPORT_ACCEPT = ".json,application/json";
/**
 * The hidden input's accessible name. Deliberately free of the words the delivered admin
 * clauses reject in a control name (030 pins "export", and the viewer clauses pin "view",
 * "open", "show" and their neighbours), so the picker reads as an import and nothing else.
 */
const IMPORT_INPUT_LABEL = "Choose a file to import";

export type UserMenuProps = {
  /** The signed-in identity; `role` decides whether the "Admin area" item exists at all. */
  user: CurrentUser;
  /** True on the rail: the trigger shows the avatar alone, with no username text. */
  compact: boolean;
  /**
   * 031 007: the one workspace characters state `App` creates, so a finished import can
   * reload the characters list. Threaded through `WorkspaceShell`, never read from context.
   */
  charactersState: CharactersState;
  /**
   * 031 007: the one workspace sessions state `App` creates — the session level of the
   * character tree — so a finished import can reload it too.
   */
  sessionsState: SessionsState;
};

/**
 * The menu's trigger (accessible name "User menu" in both modes) and its dropdown:
 * "Settings" (in-entry router navigation to `/settings`), "Admin area" (a real
 * `<a href="/admin">`, rendered only for an administrator), "Export my data" (030 006 —
 * every role, and no confirm: an export is not lossy), "Import…" (031 007 — every role,
 * and no confirm either: a roleplayer import is additive and destroys nothing) and
 * "Log out" (`logOut`).
 *
 * The returned element is a fragment, not the `Menu` alone: the hidden file input the
 * "Import…" item drives has to live OUTSIDE the dropdown. A `Menu` dropdown is portalled
 * and unmounts when it closes, and clicking an item closes it, so an input rendered inside
 * a `Menu.Item` is gone by the time the picker resolves and its `change` event never
 * reaches React. That is why this one control uses a hand-rolled input rather than
 * Mantine's `FileButton` (which the Sessions section, not being inside a menu, does use).
 */
export function UserMenu(props: UserMenuProps): React.JSX.Element {
  const { user, compact } = props;
  const navigate = useNavigate();
  const initial = user.username.slice(0, 1).toUpperCase();
  /** The hidden picker the "Import…" item clicks. Outside the `Menu`, so it survives close. */
  const importInputRef = useRef<HTMLInputElement | null>(null);

  /**
   * 030 006: the "Export my data" click. One click goes straight to the request — no
   * confirm, no success text, and no local state (the menu closes on choose). `runExport`
   * never rejects, so the bare `void` is the whole handler.
   */
  const onExportMyData = (): void => {
    void runExport(ownDataExportPath());
  };

  /**
   * 031 007: the "Import…" click. It opens the browser picker by clicking the hidden input
   * (`importInputRef.current?.click()`) and does nothing else — no confirm, no request, no
   * local state.
   */
  const onImportMyData = (): void => {
    importInputRef.current?.click();
  };

  /**
   * 031 007: a chosen file. It runs `runOwnedImport(file, props.charactersState,
   * props.sessionsState, navigate)` for the first file, then clears the input's value so
   * choosing the same file again fires `change` a second time (US-136.AC-2). An empty
   * choice does nothing. `runOwnedImport` never rejects, so there is nothing to catch.
   */
  const onImportFileChosen = (event: React.ChangeEvent<HTMLInputElement>): void => {
    const input = event.currentTarget;
    const file = input.files?.[0] ?? null;
    // Cleared before anything else, and only after the file is in hand: a file input keeps
    // its previous choice, so without this the second pick of the same file fires no
    // `change` at all and the repeat import would never start (US-136.AC-2).
    input.value = "";
    if (file === null) {
      return;
    }
    void runOwnedImport(file, props.charactersState, props.sessionsState, navigate);
  };

  return (
    <>
      <Menu position="top-start" withinPortal>
        <Menu.Target>
          <UnstyledButton aria-label="User menu" w="100%" p="xs">
            <Group gap="xs" wrap="nowrap">
              <Avatar size="sm" radius="xl">
                {initial}
              </Avatar>
              {!compact && (
                <Text size="sm" truncate>
                  {user.username}
                </Text>
              )}
            </Group>
          </UnstyledButton>
        </Menu.Target>
        <Menu.Dropdown>
          <Menu.Item
            leftSection={<IconSettings size={ITEM_ICON_SIZE} stroke={ITEM_ICON_STROKE} />}
            onClick={() => {
              void navigate(SETTINGS_PATH);
            }}
          >
            Settings
          </Menu.Item>
          {user.role === "admin" && (
            <Menu.Item
              component="a"
              href={ADMIN_HREF}
              leftSection={<IconShield size={ITEM_ICON_SIZE} stroke={ITEM_ICON_STROKE} />}
            >
              Admin area
            </Menu.Item>
          )}
          {/* 030 006: every role, and above "Log out". An export destroys nothing, so no
              confirm; success is the browser's download, so no notification. */}
          <Menu.Item
            leftSection={<IconDownload size={ITEM_ICON_SIZE} stroke={ITEM_ICON_STROKE} />}
            onClick={onExportMyData}
          >
            Export my data
          </Menu.Item>
          {/* 031 007: every role, beside "Export my data" and still above "Log out". A
              roleplayer import is additive, so no confirm either. */}
          <Menu.Item
            leftSection={<IconUpload size={ITEM_ICON_SIZE} stroke={ITEM_ICON_STROKE} />}
            onClick={onImportMyData}
          >
            Import…
          </Menu.Item>
          <Menu.Item
            leftSection={<IconLogout size={ITEM_ICON_SIZE} stroke={ITEM_ICON_STROKE} />}
            onClick={() => {
              void logOut();
            }}
          >
            Log out
          </Menu.Item>
        </Menu.Dropdown>
      </Menu>
      {/* The picker itself, outside the `Menu` so closing the dropdown cannot unmount it.
          `display: none` is Mantine's own `FileButton` idiom, and the `aria-label` is the
          control's whole accessible name since there is no visible text. */}
      <input
        ref={importInputRef}
        type="file"
        accept={IMPORT_ACCEPT}
        aria-label={IMPORT_INPUT_LABEL}
        style={{ display: "none" }}
        onChange={onImportFileChosen}
      />
    </>
  );
}
