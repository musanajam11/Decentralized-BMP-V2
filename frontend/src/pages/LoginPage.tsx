import { useEffect, useState } from "react";
import {
  Button,
  Center,
  Image,
  Paper,
  PasswordInput,
  Stack,
  TextInput,
  Title,
  Tabs,
  Alert,
} from "@mantine/core";
import { useNavigate, Navigate } from "react-router-dom";
import { useAuth } from "../auth";
import { ApiError } from "../api";
import { notifications } from "@mantine/notifications";
import { IconInfoCircle } from "@tabler/icons-react";
import { Turnstile } from "../components/Turnstile";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

interface AuthPolicy {
  open_registration: boolean;
  invite_required: boolean;
  password_min_length: number;
  turnstile_site_key: string | null;
  turnstile_required: { login: boolean; register: boolean };
}

export function LoginPage() {
  const { me, login, register } = useAuth();
  const nav = useNavigate();
  const [tab, setTab] = useState<string | null>("login");
  const [u, setU] = useState("");
  const [e, setE] = useState("");
  const [p, setP] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [policy, setPolicy] = useState<AuthPolicy | null>(null);
  const [turnstileToken, setTurnstileToken] = useState<string>("");

  useEffect(() => {
    fetch(`${API_BASE}/auth/policy`)
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => j && setPolicy(j as AuthPolicy))
      .catch(() => setPolicy(null));
  }, []);

  // Reset captcha token when switching tabs — Turnstile tokens are
  // single-use and tied to the action they were issued for.
  useEffect(() => {
    setTurnstileToken("");
  }, [tab]);

  if (me) return <Navigate to="/" replace />;

  const minLen = policy?.password_min_length ?? 12;
  const siteKey = policy?.turnstile_site_key ?? null;
  const captchaRequired =
    !!siteKey &&
    (tab === "login"
      ? policy?.turnstile_required.login
      : policy?.turnstile_required.register);
  const captchaSatisfied = !captchaRequired || !!turnstileToken;

  const submit = async () => {
    if (captchaRequired && !turnstileToken) {
      notifications.show({
        color: "yellow",
        message: "Please complete the verification challenge.",
      });
      return;
    }
    setBusy(true);
    try {
      if (tab === "login") {
        await login(u, p, turnstileToken || null);
      } else {
        await register(
          u,
          e || null,
          p,
          policy?.invite_required ? code : null,
          turnstileToken || null,
        );
      }
      nav("/");
    } catch (err) {
      // A failed Turnstile token can't be reused — clear it so the widget
      // re-renders for another attempt.
      setTurnstileToken("");
      notifications.show({
        color: "red",
        title: tab === "login" ? "Login failed" : "Registration failed",
        message: err instanceof ApiError ? err.detail : "unknown error",
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-bg">
      <Center mih="100dvh" p="md" w="100%">
        <Paper p="xl" radius="lg" withBorder maw={420} w="100%">
        <Stack gap="md">
          <Center>
            <Image src="/cm-logo.png" h={88} w={88} fit="contain" radius="md" />
          </Center>
          <Title order={3} ta="center">
            Decentralized BMP
          </Title>
          <Tabs value={tab} onChange={setTab}>
            <Tabs.List grow>
              <Tabs.Tab value="login">Sign in</Tabs.Tab>
              <Tabs.Tab value="register">Sign up</Tabs.Tab>
            </Tabs.List>
          </Tabs>

          {tab === "register" && policy?.invite_required && (
            <Alert variant="light" color="blue" icon={<IconInfoCircle />}>
              This backend is invite-only. Enter the code from your invite below.
            </Alert>
          )}

          <TextInput
            label="Username"
            value={u}
            onChange={(ev) => setU(ev.currentTarget.value)}
            autoComplete="username"
          />
          {tab === "register" && (
            <TextInput
              label="Email (optional)"
              value={e}
              onChange={(ev) => setE(ev.currentTarget.value)}
              autoComplete="email"
            />
          )}
          <PasswordInput
            label="Password"
            description={tab === "register" ? `${minLen} characters or more` : undefined}
            value={p}
            onChange={(ev) => setP(ev.currentTarget.value)}
            autoComplete={tab === "login" ? "current-password" : "new-password"}
          />
          {tab === "register" && policy?.invite_required && (
            <TextInput
              label="Invite code"
              value={code}
              onChange={(ev) => setCode(ev.currentTarget.value)}
              required
            />
          )}
          {captchaRequired && siteKey && (
            <div className="turnstile-wrap">
              <Turnstile
                key={tab ?? "login"}
                siteKey={siteKey}
                onToken={setTurnstileToken}
                onExpire={() => setTurnstileToken("")}
              />
            </div>
          )}
          <Button
            onClick={submit}
            loading={busy}
            disabled={!captchaSatisfied}
            fullWidth
          >
            {tab === "login" ? "Sign in" : "Create account"}
          </Button>
        </Stack>
      </Paper>
    </Center>
    </div>
  );
}
