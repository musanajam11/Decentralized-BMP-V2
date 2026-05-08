import { useEffect, useState } from "react";
import { Outlet, NavLink, useNavigate } from "react-router-dom";
import {
  AppShell,
  Burger,
  Group,
  NavLink as MantineNavLink,
  Badge,
  Button,
  Indicator,
  Text,
  Box,
  ActionIcon,
  useMantineColorScheme,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import {
  IconDashboard,
  IconKey,
  IconUsersGroup,
  IconBroadcast,
  IconDownload,
  IconLogout,
  IconMail,
  IconSun,
  IconMoon,
  IconTicket,
  IconSettings,
} from "@tabler/icons-react";

import { api } from "../api";
import { useAuth } from "../auth";
import { Brand } from "./Brand";

export function Layout() {
  const [opened, { toggle }] = useDisclosure();
  const { me, logout } = useAuth();
  const nav = useNavigate();
  const { colorScheme, toggleColorScheme } = useMantineColorScheme();
  const [busy, setBusy] = useState(false);
  const [unread, setUnread] = useState(0);

  // Poll for unread message count so the navbar badge stays current.
  useEffect(() => {
    if (!me) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const r = await api.get<{ inbox: number; threads: number }>("/messages/unread");
        if (!cancelled) setUnread(r.inbox);
      } catch {
        /* ignore — badge is best-effort */
      }
    };
    tick();
    const t = setInterval(tick, 30_000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [me]);

  if (!me) return null;

  const items: { to: string; label: string; icon: typeof IconDashboard; admin?: boolean; badge?: number }[] = [
    { to: "/", label: "Dashboard", icon: IconDashboard },
    { to: "/messages", label: "Messages", icon: IconMail, badge: unread },
    { to: "/downloads", label: "Downloads", icon: IconDownload },
    { to: "/keys", label: "Server Keys", icon: IconKey },
    { to: "/invites", label: "Invites", icon: IconTicket, admin: true },
    { to: "/publish", label: "Publish", icon: IconBroadcast, admin: true },
    { to: "/admin", label: "Admin · Users", icon: IconUsersGroup, admin: true },
    { to: "/admin/settings", label: "Admin · Settings", icon: IconSettings, admin: true },
  ];

  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{ width: 240, breakpoint: "sm", collapsed: { mobile: !opened } }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="sm">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <Brand />
          </Group>
          <Group gap="xs">
            <Badge color={me.role === "ADMIN" ? "violet" : "blue"} variant="light">
              {me.username} · {me.role}
            </Badge>
            <ActionIcon
              variant="subtle"
              onClick={() => toggleColorScheme()}
              aria-label="toggle color scheme"
            >
              {colorScheme === "dark" ? <IconSun size={18} /> : <IconMoon size={18} />}
            </ActionIcon>
            <Button
              variant="subtle"
              leftSection={<IconLogout size={16} />}
              loading={busy}
              onClick={async () => {
                setBusy(true);
                await logout();
                nav("/login");
              }}
            >
              Sign out
            </Button>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="sm">
        {items
          .filter((i) => !i.admin || me.role === "ADMIN")
          .map((i) => (
            <NavLink
              key={i.to}
              to={i.to}
              end={i.to === "/"}
              style={{ textDecoration: "none" }}
            >
              {({ isActive }) => (
                <MantineNavLink
                  active={isActive}
                  label={i.label}
                  leftSection={
                    i.badge && i.badge > 0 ? (
                      <Indicator label={i.badge > 9 ? "9+" : i.badge} size={14} color="red" offset={-2}>
                        <i.icon size={18} />
                      </Indicator>
                    ) : (
                      <i.icon size={18} />
                    )
                  }
                />
              )}
            </NavLink>
          ))}
        <Box mt="auto" pt="md">
          <Text size="xs" c="dimmed" ta="center">
            Decentralized-BMP V2
          </Text>
        </Box>
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
