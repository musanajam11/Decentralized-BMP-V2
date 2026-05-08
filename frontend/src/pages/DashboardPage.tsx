import { useState } from "react";
import {
  Button,
  Card,
  Group,
  PasswordInput,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useAuth } from "../auth";
import { api, ApiError } from "../api";

export function DashboardPage() {
  const { me } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);

  if (!me) return null;

  const submitPassword = async () => {
    if (next !== confirm) {
      notifications.show({ color: "yellow", message: "New passwords do not match." });
      return;
    }
    if (next.length < 8) {
      notifications.show({ color: "yellow", message: "New password is too short." });
      return;
    }
    setBusy(true);
    try {
      await api.post("/auth/change-password", {
        current_password: current,
        new_password: next,
      });
      setCurrent("");
      setNext("");
      setConfirm("");
      notifications.show({
        color: "green",
        title: "Password updated",
        message: "Other sessions have been signed out.",
      });
    } catch (err) {
      notifications.show({
        color: "red",
        title: "Could not change password",
        message: err instanceof ApiError ? err.detail : "unknown error",
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Stack>
      <Title order={2}>Welcome, {me.username}</Title>
      <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }}>
        <Card withBorder radius="md" p="lg">
          <Group justify="space-between">
            <Text c="dimmed">Role</Text>
            <Text fw={700}>{me.role}</Text>
          </Group>
        </Card>
        <Card withBorder radius="md" p="lg">
          <Group justify="space-between">
            <Text c="dimmed">Server-key allotment</Text>
            <Text fw={700}>{me.key_allotment}</Text>
          </Group>
        </Card>
        <Card withBorder radius="md" p="lg">
          <Group justify="space-between">
            <Text c="dimmed">Account created</Text>
            <Text fw={700}>{new Date(me.created_at).toLocaleDateString()}</Text>
          </Group>
        </Card>
      </SimpleGrid>

      <Card withBorder radius="md" p="lg" maw={460}>
        <Stack gap="sm">
          <Title order={4}>Change password</Title>
          <Text size="xs" c="dimmed">
            Updating your password will sign you out of any other sessions.
          </Text>
          <PasswordInput
            label="Current password"
            value={current}
            onChange={(e) => setCurrent(e.currentTarget.value)}
            autoComplete="current-password"
          />
          <PasswordInput
            label="New password"
            value={next}
            onChange={(e) => setNext(e.currentTarget.value)}
            autoComplete="new-password"
          />
          <PasswordInput
            label="Confirm new password"
            value={confirm}
            onChange={(e) => setConfirm(e.currentTarget.value)}
            autoComplete="new-password"
          />
          <Button
            onClick={submitPassword}
            loading={busy}
            disabled={!current || !next || !confirm}
          >
            Update password
          </Button>
        </Stack>
      </Card>
    </Stack>
  );
}
