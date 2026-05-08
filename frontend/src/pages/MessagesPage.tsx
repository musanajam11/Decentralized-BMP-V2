// Decentralized-BMP V2 — user/admin messaging UI
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Lightweight inbox: users open threads to the admin team; admins see and
// reply to every thread from the same screen. Polls every 15 s so an open
// conversation feels live without a websocket.
import { useEffect, useMemo, useState } from "react";
import {
  ActionIcon,
  Alert,
  Badge,
  Box,
  Button,
  Card,
  Divider,
  Group,
  Loader,
  Modal,
  ScrollArea,
  Stack,
  Text,
  TextInput,
  Textarea,
  Title,
  Tooltip,
} from "@mantine/core";
import { IconMessage, IconPlus, IconRefresh, IconSend } from "@tabler/icons-react";

import { ApiError, api } from "../api";
import { useAuth } from "../auth";

interface ThreadSummary {
  id: number;
  subject: string;
  status: "open" | "closed";
  user_id: number;
  user_username: string;
  created_at: number;
  updated_at: number;
  last_user_at: number | null;
  last_admin_at: number | null;
  unread: number;
}

interface Message {
  id: number;
  sender_id: number;
  sender_username: string;
  sender_role: "USER" | "ADMIN";
  body: string;
  created_at: number;
}

interface ThreadDetail extends ThreadSummary {
  messages: Message[];
}

const POLL_MS = 15_000;

function fmt(ts: number | null | undefined): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString();
}

export function MessagesPage() {
  const { me } = useAuth();
  const isAdmin = me?.role === "ADMIN";

  const [threads, setThreads] = useState<ThreadSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<ThreadDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const [composeOpen, setComposeOpen] = useState(false);
  const [composeSubject, setComposeSubject] = useState("");
  const [composeBody, setComposeBody] = useState("");
  const [composeBusy, setComposeBusy] = useState(false);

  const [replyBody, setReplyBody] = useState("");
  const [replyBusy, setReplyBusy] = useState(false);

  const refreshThreads = async () => {
    try {
      const list = await api.get<ThreadSummary[]>("/messages/threads");
      setThreads(list);
      setError(null);
      // Auto-select first thread if nothing chosen yet.
      if (selected == null && list.length > 0) {
        setSelected(list[0].id);
      }
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.detail : "Failed to load threads.");
    }
  };

  const refreshDetail = async (id: number) => {
    setLoadingDetail(true);
    try {
      const t = await api.get<ThreadDetail>(`/messages/threads/${id}`);
      setDetail(t);
      // Reading a thread clears unread on the server; sync our list copy.
      setThreads((prev) =>
        prev?.map((row) => (row.id === id ? { ...row, unread: 0 } : row)) ?? prev,
      );
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.detail : "Failed to load thread.");
    } finally {
      setLoadingDetail(false);
    }
  };

  useEffect(() => {
    refreshThreads();
    const t = setInterval(refreshThreads, POLL_MS);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selected != null) refreshDetail(selected);
    else setDetail(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  const submitCompose = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!composeSubject.trim() || !composeBody.trim()) return;
    setComposeBusy(true);
    try {
      const t = await api.post<ThreadDetail>("/messages/threads", {
        subject: composeSubject.trim(),
        body: composeBody.trim(),
      });
      setComposeOpen(false);
      setComposeSubject("");
      setComposeBody("");
      await refreshThreads();
      setSelected(t.id);
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.detail : "Failed to send.");
    } finally {
      setComposeBusy(false);
    }
  };

  const submitReply = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!detail || !replyBody.trim()) return;
    setReplyBusy(true);
    try {
      const t = await api.post<ThreadDetail>(`/messages/threads/${detail.id}/reply`, {
        body: replyBody.trim(),
      });
      setReplyBody("");
      setDetail(t);
      await refreshThreads();
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.detail : "Failed to send reply.");
    } finally {
      setReplyBusy(false);
    }
  };

  const toggleStatus = async () => {
    if (!detail) return;
    const action = detail.status === "open" ? "close" : "reopen";
    try {
      const t = await api.post<ThreadDetail>(`/messages/threads/${detail.id}/${action}`);
      setDetail(t);
      await refreshThreads();
    } catch (e: unknown) {
      setError(e instanceof ApiError ? e.detail : "Failed to update thread.");
    }
  };

  const sortedThreads = useMemo(
    () =>
      [...(threads ?? [])].sort(
        (a, b) =>
          Number(b.status === "open") - Number(a.status === "open") ||
          b.updated_at - a.updated_at,
      ),
    [threads],
  );

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>Messages</Title>
        <Group gap="xs">
          <Tooltip label="Refresh">
            <ActionIcon variant="subtle" onClick={refreshThreads}>
              <IconRefresh size={18} />
            </ActionIcon>
          </Tooltip>
          {!isAdmin && (
            <Button leftSection={<IconPlus size={16} />} onClick={() => setComposeOpen(true)}>
              New message
            </Button>
          )}
        </Group>
      </Group>

      {error && (
        <Alert color="red" onClose={() => setError(null)} withCloseButton>
          {error}
        </Alert>
      )}

      <Group align="flex-start" wrap="nowrap" style={{ minHeight: 480 }}>
        <Card withBorder padding="xs" radius="md" style={{ width: 320, flexShrink: 0 }}>
          <ScrollArea h={520}>
            {threads == null && (
              <Group justify="center" p="md">
                <Loader size="sm" />
              </Group>
            )}
            {threads && sortedThreads.length === 0 && (
              <Text c="dimmed" size="sm" p="sm">
                {isAdmin ? "No threads yet." : "You haven't started any threads. Click 'New message' to talk to the admins."}
              </Text>
            )}
            <Stack gap={4}>
              {sortedThreads.map((t) => {
                const active = t.id === selected;
                return (
                  <Card
                    key={t.id}
                    withBorder={active}
                    padding="xs"
                    radius="sm"
                    onClick={() => setSelected(t.id)}
                    style={{
                      cursor: "pointer",
                      background: active ? "var(--mantine-color-default-hover)" : undefined,
                    }}
                  >
                    <Group justify="space-between" wrap="nowrap" gap="xs">
                      <Box style={{ minWidth: 0, flex: 1 }}>
                        <Text fw={t.unread > 0 ? 700 : 500} truncate>
                          {t.subject}
                        </Text>
                        <Text size="xs" c="dimmed" truncate>
                          {isAdmin ? `${t.user_username} · ` : ""}{fmt(t.updated_at)}
                        </Text>
                      </Box>
                      <Stack gap={2} align="flex-end">
                        {t.unread > 0 && <Badge size="xs" color="red">{t.unread}</Badge>}
                        {t.status === "closed" && <Badge size="xs" color="gray">closed</Badge>}
                      </Stack>
                    </Group>
                  </Card>
                );
              })}
            </Stack>
          </ScrollArea>
        </Card>

        <Card withBorder padding="md" radius="md" style={{ flex: 1, minWidth: 0 }}>
          {!selected && (
            <Group justify="center" align="center" h={400}>
              <Text c="dimmed" size="sm">
                <IconMessage size={20} style={{ verticalAlign: "middle" }} />{" "}
                Select a thread to view it.
              </Text>
            </Group>
          )}
          {selected && loadingDetail && !detail && (
            <Group justify="center" p="xl">
              <Loader />
            </Group>
          )}
          {detail && (
            <Stack>
              <Group justify="space-between" align="flex-start">
                <Box>
                  <Title order={4}>{detail.subject}</Title>
                  <Text size="xs" c="dimmed">
                    Started by {detail.user_username} · {fmt(detail.created_at)}
                  </Text>
                </Box>
                <Group gap="xs">
                  <Badge color={detail.status === "open" ? "green" : "gray"}>
                    {detail.status}
                  </Badge>
                  <Button size="xs" variant="subtle" onClick={toggleStatus}>
                    {detail.status === "open" ? "Close" : "Reopen"}
                  </Button>
                </Group>
              </Group>
              <Divider />
              <ScrollArea h={360}>
                <Stack gap="sm">
                  {detail.messages.map((m) => {
                    const mine = me ? m.sender_id === me.id : false;
                    return (
                      <Card
                        key={m.id}
                        withBorder
                        padding="sm"
                        radius="md"
                        style={{
                          alignSelf: mine ? "flex-end" : "flex-start",
                          maxWidth: "85%",
                          background:
                            m.sender_role === "ADMIN"
                              ? "var(--mantine-color-violet-light)"
                              : undefined,
                        }}
                      >
                        <Group justify="space-between" gap="xs">
                          <Text size="xs" fw={600}>
                            {m.sender_username}{" "}
                            <Badge size="xs" color={m.sender_role === "ADMIN" ? "violet" : "blue"} variant="light">
                              {m.sender_role}
                            </Badge>
                          </Text>
                          <Text size="xs" c="dimmed">{fmt(m.created_at)}</Text>
                        </Group>
                        <Text size="sm" mt={4} style={{ whiteSpace: "pre-wrap" }}>
                          {m.body}
                        </Text>
                      </Card>
                    );
                  })}
                </Stack>
              </ScrollArea>
              <Divider />
              {detail.status === "open" ? (
                <form onSubmit={submitReply}>
                  <Stack gap="xs">
                    <Textarea
                      placeholder={isAdmin ? "Reply to this user…" : "Reply to the admins…"}
                      value={replyBody}
                      onChange={(e) => setReplyBody(e.currentTarget.value)}
                      autosize
                      minRows={2}
                      maxRows={8}
                      maxLength={4000}
                      required
                    />
                    <Group justify="flex-end">
                      <Button
                        type="submit"
                        leftSection={<IconSend size={16} />}
                        loading={replyBusy}
                        disabled={!replyBody.trim()}
                      >
                        Send
                      </Button>
                    </Group>
                  </Stack>
                </form>
              ) : (
                <Text c="dimmed" size="sm">
                  This thread is closed. Reopen it to reply.
                </Text>
              )}
            </Stack>
          )}
        </Card>
      </Group>

      <Modal
        opened={composeOpen}
        onClose={() => setComposeOpen(false)}
        title="New message to admins"
        size="lg"
      >
        <form onSubmit={submitCompose}>
          <Stack>
            <TextInput
              label="Subject"
              value={composeSubject}
              onChange={(e) => setComposeSubject(e.currentTarget.value)}
              maxLength={120}
              required
            />
            <Textarea
              label="Message"
              value={composeBody}
              onChange={(e) => setComposeBody(e.currentTarget.value)}
              autosize
              minRows={4}
              maxRows={12}
              maxLength={4000}
              required
            />
            <Group justify="flex-end">
              <Button variant="subtle" onClick={() => setComposeOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={composeBusy} leftSection={<IconSend size={16} />}>
                Send
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>
    </Stack>
  );
}
