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

function Gate({ children, admin = false }: { children: JSX.Element; admin?: boolean }) {
  const { me, loading } = useAuth();
  if (loading) return null;
  if (!me) return <Navigate to="/login" replace />;
  if (admin && me.role !== "ADMIN") return <Navigate to="/" replace />;
  return children;
}

export function App() {
  return (
    <AuthProvider>
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
    </AuthProvider>
  );
}
