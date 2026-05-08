import { useEffect } from "react";
import { Route, Routes, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "./auth";
import { Layout } from "./components/Layout";
import { LoginPage } from "./pages/LoginPage";
import { DashboardPage } from "./pages/DashboardPage";
import { KeysPage } from "./pages/KeysPage";
import { InvitesPage } from "./pages/InvitesPage";
import { AdminPage } from "./pages/AdminPage";
import { AdminSettingsPage } from "./pages/AdminSettingsPage";
import { PublishPage } from "./pages/PublishPage";
import { DownloadsPage } from "./pages/DownloadsPage";
import { MessagesPage } from "./pages/MessagesPage";
import { useApplyTheme } from "./themeBg";

function Gate({ children, admin = false }: { children: JSX.Element; admin?: boolean }) {
  const { me, loading } = useAuth();
  if (loading) return null;
  if (!me) return <Navigate to="/login" replace />;
  if (admin && me.role !== "ADMIN") return <Navigate to="/" replace />;
  return children;
}

function ThemedShell({ children }: { children: React.ReactNode }) {
  const theme = useApplyTheme();
  const { me } = useAuth();
  // Toggle the global wallpaper on the <body>:
  //   - the login screen renders its own .auth-bg wrapper, so we skip
  //     the body background while signed-out (avoids double rendering)
  //   - while signed in, honour the admin's "auth pages only" switch
  useEffect(() => {
    const hasBg = !!theme?.background_url;
    const signedIn = !!me;
    const enable = hasBg && signedIn && !theme?.apply_to_auth_only;
    document.body.classList.toggle("app-bg-on", enable);
    return () => { document.body.classList.remove("app-bg-on"); };
  }, [me, theme?.background_url, theme?.apply_to_auth_only]);
  return <>{children}</>;
}

export function App() {
  return (
    <AuthProvider>
      <ThemedShell>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<Gate><Layout /></Gate>}>
            <Route index element={<DashboardPage />} />
            <Route path="messages" element={<MessagesPage />} />
            <Route path="downloads" element={<DownloadsPage />} />
            <Route path="keys" element={<KeysPage />} />
            <Route path="invites" element={<Gate admin><InvitesPage /></Gate>} />
            <Route path="publish" element={<Gate admin><PublishPage /></Gate>} />
            <Route path="admin" element={<Gate admin><AdminPage /></Gate>} />
            <Route path="admin/settings" element={<Gate admin><AdminSettingsPage /></Gate>} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </ThemedShell>
    </AuthProvider>
  );
}
