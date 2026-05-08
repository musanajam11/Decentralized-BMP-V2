import { Alert, Badge, Button, Card, Code, Group, Stack, Switch, Text, Textarea, TextInput, Title } from "@mantine/core";
import { IconBroadcast, IconDeviceFloppy, IconInfoCircle, IconSend } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";
import { api, ApiError } from "../api";

interface PublishStatus {
  enabled: boolean;
  configured: boolean;
  bmr_url: string;
  heartbeat_path: string;
  display_name: string;
  region: string;
  description: string;
  public_servers: number;
}

interface PublishStatusPatch {
  enabled?: boolean;
  display_name?: string;
  region?: string;
  description?: string;
}

interface PublishPushResult {
  pushed: boolean;
  reason: string;
  detail?: string | null;
  public_servers?: number | null;
}

const REASON_LABELS: Record<string, string> = {
  ok: "Heartbeat accepted by BMR",
  bmr_api_key_unset: "BMR_API_KEY is not set on this backend",
  publish_disabled: "Publishing toggle is off",
  transport_error: "Could not reach BMR (network/DNS/TLS)",
};

function reasonLabel(r: string): string {
  if (REASON_LABELS[r]) return REASON_LABELS[r];
  if (r.startsWith("bmr_status_")) return `BMR rejected the heartbeat (HTTP ${r.slice("bmr_status_".length)})`;
  return r;
}

export function PublishPage() {
  const qc = useQueryClient();
  const q = useQuery<PublishStatus>({
    queryKey: ["publish"],
    queryFn: () => api.get("/publish/status"),
    refetchInterval: 30_000,
  });

  const patch = useMutation({
    mutationFn: (body: PublishStatusPatch) =>
      api.patch<PublishStatus>("/publish/status", body),
    onSuccess: (data, vars) => {
      qc.setQueryData(["publish"], data);
      if ("enabled" in vars) {
        notifications.show({
          color: data.enabled ? "green" : "gray",
          message: data.enabled ? "Publishing enabled" : "Publishing disabled",
        });
      } else {
        notifications.show({ color: "green", message: "Listing details saved" });
      }
    },
    onError: (err) =>
      notifications.show({
        color: "red",
        title: "Could not update publish settings",
        message: err instanceof ApiError ? err.detail : "unknown error",
      }),
  });

  const [lastPush, setLastPush] = useState<PublishPushResult | null>(null);
  const testPush = useMutation({
    mutationFn: () => api.post<PublishPushResult>("/publish/push", {}),
    onSuccess: (data) => {
      setLastPush(data);
      notifications.show({
        color: data.pushed ? "green" : "red",
        title: data.pushed ? "Heartbeat pushed" : "Heartbeat not sent",
        message: reasonLabel(data.reason),
      });
    },
    onError: (err) => {
      let detail: string;
      let reason: string;
      if (err instanceof ApiError) {
        reason = `client_status_${err.status}`;
        detail = err.detail || `HTTP ${err.status}`;
      } else if (err instanceof Error) {
        reason = "client_error";
        detail = `${err.name}: ${err.message}`;
      } else {
        reason = "client_error";
        detail = String(err);
      }
      // eslint-disable-next-line no-console
      console.error("[publish] test push failed", err);
      setLastPush({ pushed: false, reason, detail });
      notifications.show({ color: "red", title: "Test push failed", message: detail });
    },
  });

  if (!q.data) return null;
  return <PublishPageInner s={q.data} patch={patch} testPush={testPush} lastPush={lastPush} />;
}

interface InnerProps {
  s: PublishStatus;
  patch: ReturnType<typeof useMutation<PublishStatus, unknown, PublishStatusPatch>>;
  testPush: ReturnType<typeof useMutation<PublishPushResult, unknown, void>>;
  lastPush: PublishPushResult | null;
}

function PublishPageInner({ s, patch, testPush, lastPush }: InnerProps) {
  const [displayName, setDisplayName] = useState(s.display_name);
  const [region, setRegion] = useState(s.region);
  const [description, setDescription] = useState(s.description);

  // Refresh form when server-side values change (heartbeat refetch).
  useEffect(() => { setDisplayName(s.display_name); }, [s.display_name]);
  useEffect(() => { setRegion(s.region); }, [s.region]);
  useEffect(() => { setDescription(s.description); }, [s.description]);

  const dirty =
    displayName !== s.display_name ||
    region !== s.region ||
    description !== s.description;

  return (
    <Stack maw={720}>
      <Group justify="space-between">
        <Title order={2}>Public Listing (BMR)</Title>
        <Badge size="lg" color={s.enabled ? "green" : "gray"} variant="light">
          <Group gap={4}>
            <IconBroadcast size={14} />
            {s.enabled ? "Publishing" : "Not publishing"}
          </Group>
        </Badge>
      </Group>

      <Text c="dimmed">
        When publishing is on, this backend pushes the list of its <b>public</b>
        {" "}server keys to BMR at <Code>{s.bmr_url}</Code> so it appears in
        Content Manager's backend picker. With it off, your backend is still
        reachable directly at its own domain — it just isn't listed publicly.
        Per-server visibility is controlled on the <b>Server Keys</b> page.
      </Text>

      <Card withBorder radius="md" p="lg">
        <Stack>
          <Switch
            size="lg"
            label="Publish this backend to BMR"
            description="Sends a heartbeat every 60 seconds with your public servers."
            checked={s.enabled}
            disabled={!s.configured || patch.isPending}
            onChange={(e) => patch.mutate({ enabled: e.currentTarget.checked })}
          />
          {!s.configured && (
            <Alert color="yellow" icon={<IconInfoCircle />}>
              Publishing is locked off because <Code>BMR_API_KEY</Code> is not
              set in the backend <Code>.env</Code>. Without it BMR would refuse
              the heartbeat anyway.
            </Alert>
          )}
        </Stack>
      </Card>

      <Card withBorder radius="md" p="lg">
        <Stack gap="sm">
          <div>
            <Title order={4}>Listing details</Title>
            <Text c="dimmed" size="sm">
              These are what Content Manager shows in its backend picker. The
              next heartbeat (within 60 s) overwrites BMR's stored copy with
              these values.
            </Text>
          </div>
          <TextInput
            label="Backend display name"
            description="Up to 80 characters."
            value={displayName}
            maxLength={80}
            onChange={(e) => setDisplayName(e.currentTarget.value)}
          />
          <TextInput
            label="Region"
            description={'Free-form. Conventional values: "us-east", "us-west", "eu-west", "asia-sg".'}
            value={region}
            maxLength={64}
            onChange={(e) => setRegion(e.currentTarget.value)}
          />
          <Textarea
            label="Description"
            description="Optional. Up to 512 characters."
            value={description}
            maxLength={512}
            autosize
            minRows={2}
            maxRows={6}
            onChange={(e) => setDescription(e.currentTarget.value)}
          />
          <Group justify="flex-end" gap="xs">
            <Button
              variant="default"
              disabled={!dirty || patch.isPending}
              onClick={() => {
                setDisplayName(s.display_name);
                setRegion(s.region);
                setDescription(s.description);
              }}
            >
              Reset
            </Button>
            <Button
              leftSection={<IconDeviceFloppy size={16} />}
              loading={patch.isPending}
              disabled={!dirty}
              onClick={() =>
                patch.mutate({
                  display_name: displayName,
                  region,
                  description,
                })
              }
            >
              Save
            </Button>
          </Group>
          <Group justify="space-between" pt="xs">
            <Text c="dimmed" size="sm">Public servers currently active</Text>
            <Badge variant="light">{s.public_servers}</Badge>
          </Group>
        </Stack>
      </Card>
      <Card withBorder radius="md" p="lg">
        <Stack gap="xs">
          <Group justify="space-between">
            <div>
              <Title order={4}>Test publish</Title>
              <Text c="dimmed" size="sm">
                Send an immediate heartbeat to BMR and show the result. Bypasses
                the 60 s timer but still respects the publish toggle and key.
              </Text>
            </div>
            <Button
              leftSection={<IconSend size={16} />}
              onClick={() => testPush.mutate()}
              loading={testPush.isPending}
            >
              Send heartbeat now
            </Button>
          </Group>
          {lastPush && (
            <Alert
              color={lastPush.pushed ? "green" : "red"}
              icon={<IconInfoCircle />}
              title={lastPush.pushed ? "Pushed" : "Not pushed"}
            >
              <Stack gap={4}>
                <Text size="sm">{reasonLabel(lastPush.reason)}</Text>
                {lastPush.public_servers !== undefined && lastPush.public_servers !== null && (
                  <Text size="sm" c="dimmed">
                    Servers included in payload: <b>{lastPush.public_servers}</b>
                  </Text>
                )}
                {lastPush.detail && (
                  <Code block fz="xs" style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                    {lastPush.detail}
                  </Code>
                )}
              </Stack>
            </Alert>
          )}
        </Stack>
      </Card>
    </Stack>
  );
}
