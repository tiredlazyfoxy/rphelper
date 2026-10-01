// The user menu at the foot of the left column (008 context.md D6): an upward-opening
// Mantine `Menu` whose trigger is the avatar plus, when the column is expanded, the
// username. Holds no MobX state — the menu's open flag is Mantine's own — so it is a plain
// component, not an `observer`. The signed-in user arrives as a prop, never through context.
import type * as React from "react";
import { useNavigate } from "react-router-dom";
import { Avatar, Group, Menu, Text, UnstyledButton } from "@mantine/core";
import { IconLogout, IconSettings, IconShield } from "@tabler/icons-react";

import type { CurrentUser } from "../shared/currentUser";
import { logOut } from "./logout";

/** Inline-control sizing from `ui-conventions.md`; stroke 1.5 is the one visual weight. */
const ITEM_ICON_SIZE = 16;
const ITEM_ICON_STROKE = 1.5;

const SETTINGS_PATH = "/settings";
/** Another entry and another document, so a real anchor — never a router `Link` (D6). */
const ADMIN_HREF = "/admin";

export type UserMenuProps = {
  /** The signed-in identity; `role` decides whether the "Admin area" item exists at all. */
  user: CurrentUser;
  /** True on the rail: the trigger shows the avatar alone, with no username text. */
  compact: boolean;
};

/**
 * The menu's trigger (accessible name "User menu" in both modes) and its dropdown:
 * "Settings" (in-entry router navigation to `/settings`), "Admin area" (a real
 * `<a href="/admin">`, rendered only for an administrator) and "Log out" (`logOut`).
 */
export function UserMenu(props: UserMenuProps): React.JSX.Element {
  const { user, compact } = props;
  const navigate = useNavigate();
  const initial = user.username.slice(0, 1).toUpperCase();

  return (
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
  );
}
