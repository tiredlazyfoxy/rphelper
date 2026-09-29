// The admin frame: Mantine AppShell with header and navbar, rendering its children
// in the main region. Carries the entry's `data-entry="admin"` marker.
import type * as React from "react";
import { observer } from "mobx-react-lite";
import { Link, useLocation } from "react-router-dom";
import { Anchor, AppShell, Burger, Group, NavLink, Title } from "@mantine/core";
import { closeNavbar, toggleNavbar, type AdminShellState } from "./adminShellState";
import { NAV_ITEMS, isNavItemActive } from "./navItems";

export type AdminShellProps = {
  shell: AdminShellState;
  children: React.ReactNode;
};

export const AdminShell = observer(function AdminShell(
  props: AdminShellProps,
): React.JSX.Element {
  const { shell, children } = props;
  const { pathname } = useLocation();

  return (
    <AppShell
      data-entry="admin"
      header={{ height: 56 }}
      navbar={{ width: 220, breakpoint: "sm", collapsed: { mobile: !shell.navbarOpened } }}
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group gap="sm" wrap="nowrap">
            <Burger
              opened={shell.navbarOpened}
              onClick={() => {
                toggleNavbar(shell);
              }}
              hiddenFrom="sm"
              size="sm"
              aria-label="Toggle navigation"
            />
            <Title order={4}>Admin</Title>
          </Group>
          <Anchor href="/">Back to app</Anchor>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="xs">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.path}
              component={Link}
              to={item.path}
              label={item.label}
              leftSection={<Icon size={18} stroke={1.5} />}
              active={isNavItemActive(pathname, item)}
              onClick={() => {
                closeNavbar(shell);
              }}
            />
          );
        })}
      </AppShell.Navbar>
      <AppShell.Main>{children}</AppShell.Main>
    </AppShell>
  );
});
