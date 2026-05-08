import {
  Card,
  Group,
  NumberInput,
  Select,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useAuth } from "../auth";

interface AdminUser {
  id: number;
  username: string;
  email: string | null;
  role: "USER" | "ADMIN";
  key_allotment: number;
  keys_in_use: number;
  created_at: string;
  last_login_at: string | null;
}

export function AdminPage() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const users = useQuery<AdminUser[]>({
    queryKey: ["admin", "users"],
    queryFn: () => api.get("/admin/users"),
  });

  const setAllot = useMutation({
    mutationFn: (v: { id: number; n: number }) =>
      api.patch<AdminUser>(`/admin/users/${v.id}/allotment`, { key_allotment: v.n }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }),
  });
  const setRole = useMutation({
    mutationFn: (v: { id: number; role: "USER" | "ADMIN" }) =>
      api.patch<AdminUser>(`/admin/users/${v.id}/role`, { role: v.role }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }),
  });

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Admin · Users</Title>
        <Text c="dimmed">
          Default new-user allotment is set via <code>DEFAULT_KEY_ALLOTMENT</code> in the
          backend <code>.env</code>.
        </Text>
      </Group>
      <Card withBorder radius="md" p={0}>
        <Table striped highlightOnHover verticalSpacing="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>User</Table.Th>
              <Table.Th>Role</Table.Th>
              <Table.Th>Keys in use</Table.Th>
              <Table.Th>Allotment</Table.Th>
              <Table.Th>Last login</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {users.data?.map((u) => (
              <Table.Tr key={u.id}>
                <Table.Td>
                  <Stack gap={0}>
                    <Text fw={600}>{u.username}</Text>
                    {u.email && (
                      <Text size="xs" c="dimmed">
                        {u.email}
                      </Text>
                    )}
                  </Stack>
                </Table.Td>
                <Table.Td>
                  <Select
                    size="xs"
                    w={110}
                    data={["USER", "ADMIN"]}
                    value={u.role}
                    disabled={u.id === me?.id}
                    onChange={(v) =>
                      v && setRole.mutate({ id: u.id, role: v as "USER" | "ADMIN" })
                    }
                  />
                </Table.Td>
                <Table.Td>{u.keys_in_use}</Table.Td>
                <Table.Td>
                  <NumberInput
                    size="xs"
                    w={110}
                    min={0}
                    max={9999}
                    value={u.key_allotment}
                    onChange={(v) =>
                      typeof v === "number" && setAllot.mutate({ id: u.id, n: v })
                    }
                  />
                </Table.Td>
                <Table.Td>
                  {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "—"}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Card>
    </Stack>
  );
}
