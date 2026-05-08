import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api, tokens } from "./api";

export interface Me {
  id: number;
  username: string;
  email: string | null;
  role: "USER" | "ADMIN";
  key_allotment: number;
  created_at: string;
}

interface AuthCtx {
  me: Me | null;
  loading: boolean;
  login: (username: string, password: string, turnstileToken?: string | null) => Promise<void>;
  register: (
    username: string,
    email: string | null,
    password: string,
    inviteCode: string | null,
    turnstileToken?: string | null,
  ) => Promise<void>;
  logout: () => Promise<void>;
  refreshMe: () => Promise<void>;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshMe = async () => {
    if (!tokens.access) {
      setMe(null);
      return;
    }
    try {
      setMe(await api.get<Me>("/auth/me"));
    } catch {
      setMe(null);
    }
  };

  useEffect(() => {
    // Pick up tokens delivered via OAuth fragment.
    if (location.hash.startsWith("#oauth_done&")) {
      const params = new URLSearchParams(location.hash.split("&").slice(1).join("&"));
      const a = params.get("access");
      const r = params.get("refresh");
      if (a && r) tokens.set(a, r);
      history.replaceState(null, "", location.pathname);
    }
    refreshMe().finally(() => setLoading(false));
  }, []);

  const login = async (username: string, password: string, turnstileToken?: string | null) => {
    const t = await api.post<{ access_token: string; refresh_token: string }>(
      "/auth/login",
      { username, password, turnstile_token: turnstileToken ?? null },
    );
    tokens.set(t.access_token, t.refresh_token);
    await refreshMe();
  };

  const register = async (
    username: string,
    email: string | null,
    password: string,
    inviteCode: string | null,
    turnstileToken?: string | null,
  ) => {
    const t = await api.post<{ access_token: string; refresh_token: string }>(
      "/auth/register",
      {
        username,
        email,
        password,
        invite_code: inviteCode,
        turnstile_token: turnstileToken ?? null,
      },
    );
    tokens.set(t.access_token, t.refresh_token);
    await refreshMe();
  };

  const logout = async () => {
    if (tokens.refresh) {
      try {
        await api.post("/auth/logout", { refresh_token: tokens.refresh });
      } catch {
        /* ignore */
      }
    }
    tokens.clear();
    setMe(null);
  };

  return (
    <Ctx.Provider value={{ me, loading, login, register, logout, refreshMe }}>
      {children}
    </Ctx.Provider>
  );
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
