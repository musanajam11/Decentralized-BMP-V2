import { useEffect, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  NumberInput,
  PasswordInput,
  Select,
  Stack,
  Switch,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { IconDeviceFloppy, IconInfoCircle, IconShieldCheck } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { notifications } from "@mantine/notifications";
import { api, ApiError } from "../api";

interface AppSettings {
  open_registration: boolean;
  key_allotment_mode: "admin_issued" | "default_amount";
  key_default_amount: number;
}

interface TurnstileSettings {
  configured: boolean;
  site_key: string;
  secret_key_set: boolean;
  require_login: boolean;
  require_register: boolean;
}

interface TurnstilePatch {
  site_key?: string;
  secret_key?: string; // "__clear__" wipes the stored secret
  require_login?: boolean;
  require_register?: boolean;
}

export function AdminSettingsPage() {
  const qc = useQueryClient();
  const q = useQuery<AppSettings>({
    queryKey: ["admin", "settings"],
    queryFn: () => api.get("/admin/settings"),
  });

  const [draft, setDraft] = useState<AppSettings | null>(null);
  useEffect(() => {
    if (q.data) setDraft(q.data);
  }, [q.data]);

  const save = useMutation({
    mutationFn: (body: AppSettings) => api.patch<AppSettings>("/admin/settings", body),
    onSuccess: (data) => {
      qc.setQueryData(["admin", "settings"], data);
      notifications.show({ color: "green", message: "Settings saved" });
    },
    onError: (err) =>
      notifications.show({
        color: "red",
        title: "Save failed",
        message: err instanceof ApiError ? err.detail : "unknown error",
      }),
  });

  if (!draft) return null;
  const dirty = JSON.stringify(draft) !== JSON.stringify(q.data);

  return (
    <Stack maw={720}>
      <Title order={2}>Admin · Settings</Title>

      <Card withBorder radius="md" p="lg">
        <Stack>
          <Title order={4}>Account creation</Title>
          <Switch
            label="Open registration"
            description="If on, anyone can create an account. If off, an invite code is required."
            checked={draft.open_registration}
            onChange={(e) =>
              setDraft({ ...draft, open_registration: e.currentTarget.checked })
            }
          />
        </Stack>
      </Card>

      <Card withBorder radius="md" p="lg">
        <Stack>
          <Title order={4}>Server keys for new users</Title>
          <Select
            label="Allotment mode"
            data={[
              { value: "admin_issued", label: "Admin-issued only (new users start with 0 keys)" },
              { value: "default_amount", label: "Grant a default number of keys on signup" },
            ]}
            value={draft.key_allotment_mode}
            allowDeselect={false}
            onChange={(v) =>
              v &&
              setDraft({ ...draft, key_allotment_mode: v as AppSettings["key_allotment_mode"] })
            }
          />
          <NumberInput
            label="Default keys granted on signup"
            description="How many BeamMP server keys each new account can mint by default. Only used when 'Grant a default number of keys on signup' is selected."
            min={0}
            max={10000}
            value={draft.key_default_amount}
            onChange={(v) =>
              typeof v === "number" &&
              setDraft({ ...draft, key_default_amount: v })
            }
            disabled={draft.key_allotment_mode !== "default_amount"}
          />
          <Alert variant="light" icon={<IconInfoCircle />}>
            Per-user allotments can also be tuned individually on the
            <b> Admin · Users</b> page. Existing users are not affected when
            this default is changed.
          </Alert>
        </Stack>
      </Card>

      <Group>
        <Button
          leftSection={<IconDeviceFloppy size={16} />}
          loading={save.isPending}
          disabled={!dirty}
          onClick={() => save.mutate(draft)}
        >
          Save changes
        </Button>
        <Button
          variant="subtle"
          disabled={!dirty}
          onClick={() => q.data && setDraft(q.data)}
        >
          Discard
        </Button>
        {!dirty && (
          <Text c="dimmed" size="sm">
            All changes saved
          </Text>
        )}
      </Group>

      <TurnstilePanel />
    </Stack>
  );
}


function TurnstilePanel() {
  const qc = useQueryClient();
  const q = useQuery<TurnstileSettings>({
    queryKey: ["admin", "settings", "turnstile"],
    queryFn: () => api.get("/admin/settings/turnstile"),
  });

  const [siteKey, setSiteKey] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [requireLogin, setRequireLogin] = useState(true);
  const [requireRegister, setRequireRegister] = useState(true);
  const [clearedSecret, setClearedSecret] = useState(false);

  useEffect(() => {
    if (q.data) {
      setSiteKey(q.data.site_key);
      setSecretKey("");
      setRequireLogin(q.data.require_login);
      setRequireRegister(q.data.require_register);
      setClearedSecret(false);
    }
  }, [q.data]);

  const save = useMutation({
    mutationFn: (body: TurnstilePatch) =>
      api.post<TurnstileSettings>("/admin/settings/turnstile", body),
    onSuccess: (data) => {
      qc.setQueryData(["admin", "settings", "turnstile"], data);
      notifications.show({ color: "green", message: "Turnstile settings saved" });
    },
    onError: (err) =>
      notifications.show({
        color: "red",
        title: "Save failed",
        message: err instanceof ApiError ? err.detail : "unknown error",
      }),
  });

  const onSave = () => {
    const body: TurnstilePatch = {
      site_key: siteKey.trim(),
      require_login: requireLogin,
      require_register: requireRegister,
    };
    if (clearedSecret) body.secret_key = "__clear__";
    else if (secretKey.trim()) body.secret_key = secretKey.trim();
    save.mutate(body);
  };

  if (!q.data) return null;

  return (
    <Card withBorder radius="md" p="lg">
      <Stack>
        <Group justify="space-between">
          <Group gap="xs">
            <IconShieldCheck size={20} />
            <Title order={4}>Cloudflare Turnstile</Title>
          </Group>
          {q.data.configured ? (
            <Badge color="green" variant="light">
              Active
            </Badge>
          ) : (
            <Badge color="gray" variant="light">
              Not configured
            </Badge>
          )}
        </Group>
        <Text size="sm" c="dimmed">
          Bot-protection challenge shown on the login &amp; sign-up forms. Get
          your site key + secret from the{" "}
          <a
            href="https://dash.cloudflare.com/?to=/:account/turnstile"
            target="_blank"
            rel="noreferrer"
          >
            Cloudflare dashboard → Turnstile
          </a>
          . Leave both blank to disable Turnstile entirely.
        </Text>
        <TextInput
          label="Site key"
          placeholder="0x4AAAAAAAxxxxxxxxxxxxxxx"
          value={siteKey}
          onChange={(e) => setSiteKey(e.currentTarget.value)}
          spellCheck={false}
          autoComplete="off"
        />
        <PasswordInput
          label="Secret key"
          description={
            q.data.secret_key_set
              ? "A secret is stored. Type a new one to replace it, or use 'Clear stored secret' to wipe it."
              : "No secret stored yet."
          }
          placeholder={q.data.secret_key_set ? "•••••••••• (set)" : "0x4AAAAAAAxxxxxxxxxxxxxxx"}
          value={secretKey}
          onChange={(e) => {
            setSecretKey(e.currentTarget.value);
            setClearedSecret(false);
          }}
          spellCheck={false}
          autoComplete="off"
          disabled={clearedSecret}
        />
        {q.data.secret_key_set && (
          <Group>
            <Button
              variant="light"
              color="red"
              size="xs"
              onClick={() => {
                setSecretKey("");
                setClearedSecret(true);
              }}
              disabled={clearedSecret}
            >
              {clearedSecret ? "Will clear on save" : "Clear stored secret"}
            </Button>
          </Group>
        )}
        <Switch
          label="Require challenge on Sign in"
          description="When Turnstile is configured, gate /auth/login behind a successful challenge."
          checked={requireLogin}
          onChange={(e) => setRequireLogin(e.currentTarget.checked)}
        />
        <Switch
          label="Require challenge on Sign up"
          description="Strongly recommended — blocks automated account creation."
          checked={requireRegister}
          onChange={(e) => setRequireRegister(e.currentTarget.checked)}
        />
        {!q.data.configured && (
          <Alert variant="light" color="yellow" icon={<IconInfoCircle />}>
            Turnstile is currently disabled. Both a site key and a secret key
            are required to start enforcing the challenge.
          </Alert>
        )}
        <Group>
          <Button
            leftSection={<IconDeviceFloppy size={16} />}
            loading={save.isPending}
            onClick={onSave}
          >
            Save Turnstile settings
          </Button>
        </Group>
      </Stack>
    </Card>
  );
}
