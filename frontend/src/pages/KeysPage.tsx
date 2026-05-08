import { useState } from "react";
import {
  ActionIcon,
  Badge,
  Button,
  Card,
  Code,
  Group,
  Modal,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import { IconCopy, IconPlus, IconTrash, IconWorld, IconLock } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { notifications } from "@mantine/notifications";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";

interface Key {
  id: number;
  key: string;
  server_name: string;
  owner: string;
  public: boolean;
  created_at: string;
}

export function KeysPage() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("My Server");
  const [makePublic, setMakePublic] = useState(false);

  const list = useQuery<Key[]>({ queryKey: ["keys"], queryFn: () => api.get("/keys") });

  const create = useMutation({
    mutationFn: () => api.post<Key>("/keys", { server_name: name, public: makePublic }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["keys"] });
      setOpen(false);
      setMakePublic(false);
    },
    onError: (e) =>
      notifications.show({
        color: "red",
        title: "Failed to mint key",
        message: e instanceof ApiError ? e.detail : "unknown error",
      }),
  });

  const togglePublic = useMutation({
    mutationFn: ({ id, pub }: { id: number; pub: boolean }) =>
      api.patch<Key>(`/keys/${id}`, { public: pub }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["keys"] }),
    onError: (e) =>
      notifications.show({
        color: "red",
        title: "Could not change visibility",
        message: e instanceof ApiError ? e.detail : "unknown error",
      }),
  });

  const del = useMutation({
    mutationFn: (id: number) => api.delete(`/keys/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["keys"] }),
  });

  const used = list.data?.length ?? 0;
  const limit = me?.key_allotment ?? 0;
  const atLimit = me?.role !== "ADMIN" && used >= limit;

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Server Keys</Title>
        <Button
          leftSection={<IconPlus size={16} />}
          onClick={() => setOpen(true)}
          disabled={atLimit}
        >
          Mint key
        </Button>
      </Group>
      <Text c="dimmed">
        Using <b>{used}</b> of <b>{limit}</b> allotted keys
        {me?.role === "ADMIN" && " (admins are unmetered)"}.
      </Text>

      <Card withBorder radius="md" p={0}>
        <Table striped highlightOnHover verticalSpacing="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Server name</Table.Th>
              <Table.Th>Key</Table.Th>
              <Table.Th>Visibility</Table.Th>
              <Table.Th>Created</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {list.data?.map((k) => (
              <Table.Tr key={k.id}>
                <Table.Td>{k.server_name}</Table.Td>
                <Table.Td>
                  <Group gap="xs">
                    <Code>{k.key.slice(0, 12)}…</Code>
                    <ActionIcon
                      variant="subtle"
                      onClick={() => {
                        navigator.clipboard.writeText(k.key);
                        notifications.show({ message: "Copied" });
                      }}
                    >
                      <IconCopy size={14} />
                    </ActionIcon>
                  </Group>
                </Table.Td>
                <Table.Td>
                  <Group gap="xs">
                    <Tooltip
                      label={
                        k.public
                          ? "Listed on BMR when this backend publishes."
                          : "Private — not listed anywhere outside this backend."
                      }
                    >
                      <Badge
                        color={k.public ? "green" : "gray"}
                        variant="light"
                        leftSection={
                          k.public ? <IconWorld size={12} /> : <IconLock size={12} />
                        }
                      >
                        {k.public ? "Public" : "Private"}
                      </Badge>
                    </Tooltip>
                    <Switch
                      size="sm"
                      checked={k.public}
                      onChange={(e) =>
                        togglePublic.mutate({ id: k.id, pub: e.currentTarget.checked })
                      }
                    />
                  </Group>
                </Table.Td>
                <Table.Td>{new Date(k.created_at).toLocaleString()}</Table.Td>
                <Table.Td>
                  <ActionIcon color="red" variant="subtle" onClick={() => del.mutate(k.id)}>
                    <IconTrash size={16} />
                  </ActionIcon>
                </Table.Td>
              </Table.Tr>
            ))}
            {list.data && list.data.length === 0 && (
              <Table.Tr>
                <Table.Td colSpan={5}>
                  <Text c="dimmed" ta="center" py="md">
                    No keys yet — mint one to register a BeamMP-Server.
                  </Text>
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Card>

      <Modal opened={open} onClose={() => setOpen(false)} title="Mint a server key">
        <Stack>
          <TextInput
            label="Server name"
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
          />
          <Switch
            label="Public"
            description="Public servers appear on BMR when this backend publishes. You can flip this any time."
            checked={makePublic}
            onChange={(e) => setMakePublic(e.currentTarget.checked)}
          />
          <Button loading={create.isPending} onClick={() => create.mutate()}>
            Mint
          </Button>
        </Stack>
      </Modal>
    </Stack>
  );
}
