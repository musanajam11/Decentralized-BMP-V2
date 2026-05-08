import { useState } from "react";
import {
  ActionIcon,
  Badge,
  Button,
  Card,
  Code,
  Group,
  NumberInput,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { IconCopy, IconPlus, IconTrash } from "@tabler/icons-react";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../api";

interface Invite {
  id: number;
  code: string;
  created_by: string;
  created_at: string;
  used_by: string | null;
  used_at: string | null;
}

export function InvitesPage() {
  const qc = useQueryClient();
  const [count, setCount] = useState<number | "">(1);

  const list = useQuery<Invite[]>({
    queryKey: ["invites"],
    queryFn: () => api.get("/invites"),
  });

  const mint = useMutation({
    mutationFn: (n: number) => api.post<Invite[]>("/invites", { count: n }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["invites"] }),
    onError: (err) =>
      notifications.show({
        color: "red",
        title: "Could not mint invites",
        message: err instanceof ApiError ? err.detail : "unknown error",
      }),
  });

  const revoke = useMutation({
    mutationFn: (id: number) => api.delete(`/invites/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["invites"] }),
  });

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Invite Codes</Title>
        <Group>
          <NumberInput
            value={count}
            onChange={(v) => setCount(typeof v === "number" ? v : "")}
            min={1}
            max={100}
            w={100}
          />
          <Button
            leftSection={<IconPlus size={16} />}
            onClick={() => typeof count === "number" && mint.mutate(count)}
            loading={mint.isPending}
            disabled={count === "" || count < 1}
          >
            Mint
          </Button>
        </Group>
      </Group>
      <Text c="dimmed" size="sm">
        Invite codes gate signup when open registration is off. Hand them out
        to people you want to let in.
      </Text>

      <Card withBorder radius="md" p={0}>
        <Table striped highlightOnHover verticalSpacing="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>Code</Table.Th>
              <Table.Th>Status</Table.Th>
              <Table.Th>Created</Table.Th>
              <Table.Th />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {list.data?.map((inv) => (
              <Table.Tr key={inv.id}>
                <Table.Td>
                  <Group gap="xs">
                    <Code>{inv.code}</Code>
                    <ActionIcon
                      variant="subtle"
                      onClick={() => {
                        navigator.clipboard.writeText(inv.code);
                        notifications.show({ message: "Invite code copied" });
                      }}
                    >
                      <IconCopy size={14} />
                    </ActionIcon>
                  </Group>
                </Table.Td>
                <Table.Td>
                  {inv.used_by ? (
                    <Badge color="gray" variant="light">
                      Used by {inv.used_by}
                    </Badge>
                  ) : (
                    <Badge color="green" variant="light">
                      Available
                    </Badge>
                  )}
                </Table.Td>
                <Table.Td>{new Date(inv.created_at).toLocaleString()}</Table.Td>
                <Table.Td>
                  {!inv.used_by && (
                    <ActionIcon
                      color="red"
                      variant="subtle"
                      onClick={() => revoke.mutate(inv.id)}
                    >
                      <IconTrash size={16} />
                    </ActionIcon>
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
            {list.data && list.data.length === 0 && (
              <Table.Tr>
                <Table.Td colSpan={4}>
                  <Text c="dimmed" ta="center" py="md">
                    No invite codes yet.
                  </Text>
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Card>
    </Stack>
  );
}
