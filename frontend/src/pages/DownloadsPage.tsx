// Decentralized-BMP V2 — public downloads page.
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Lists the modified BeamMP-Server / Launcher / client mod binaries that
// this backend serves out of /builds/*. Pulls the inventory from
// /builds/manifest so missing files don't show up as broken links.
import { useEffect, useState } from "react";
import {
  Alert,
  Anchor,
  Badge,
  Box,
  Button,
  Card,
  Code,
  Group,
  Loader,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import {
  IconBrandWindows,
  IconBrandDebian,
  IconDownload,
} from "@tabler/icons-react";

import { ApiError, api, apiBaseUrl } from "../api";

type ManifestEntry = {
  url: string;
  filename: string;
  size: number;
  sha256: string;
};

type Manifest = {
  builds: Partial<Record<"server_windows" | "server_linux", ManifestEntry>>;
  public_origin: string;
};

const META: Record<keyof Manifest["builds"], { title: string; subtitle: string; icon: typeof IconBrandWindows }> = {
  server_windows: {
    title: "BeamMP Server (Windows)",
    subtitle:
      "Modified BeamMP-Server.exe pre-pointed at this backend. Drop in and run.",
    icon: IconBrandWindows,
  },
  server_linux: {
    title: "BeamMP Server (Linux / Debian 12)",
    subtitle:
      "Modified BeamMP-Server x86_64 binary pre-pointed at this backend.",
    icon: IconBrandDebian,
  },
};

const ORDER: (keyof Manifest["builds"])[] = ["server_windows", "server_linux"];

function formatBytes(n: number): string {
  if (!n) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i += 1;
  }
  return `${v.toFixed(v >= 100 || i === 0 ? 0 : 1)} ${units[i]}`;
}

export function DownloadsPage() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api
      .get<Manifest>("/builds/manifest")
      .then((m) => {
        if (cancelled) return;
        setManifest(m);
        setError(null);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof ApiError ? e.detail : "Failed to load downloads.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Build absolute URLs in case the backend was reached via a relative API
  // base — clicking a link should always download from the backend itself.
  const absolute = (url: string): string => {
    if (/^https?:\/\//i.test(url)) return url;
    return `${apiBaseUrl}${url}`;
  };

  const entries = manifest
    ? ORDER.flatMap((k) => {
        const entry = manifest.builds[k];
        return entry ? [{ key: k, entry }] : [];
      })
    : [];

  return (
    <Stack>
      <Box>
        <Title order={2}>Downloads</Title>
        <Text c="dimmed" size="sm" mt={4}>
          Modified BeamMP server binaries served by this backend. Each one
          has been patched at build time so the backend / auth host points
          at this instance ({manifest?.public_origin ?? "—"}) instead of the
          official BeamMP servers. Players don't need to download anything
          from here — BeamNG Content Manager bundles its own launcher and the
          launcher distributes the client mod automatically when joining.
        </Text>
      </Box>

      {loading && (
        <Group>
          <Loader size="sm" /> <Text size="sm">Loading downloads…</Text>
        </Group>
      )}

      {error && (
        <Alert color="red" title="Couldn't load downloads">
          {error}
        </Alert>
      )}

      {!loading && !error && entries.length === 0 && (
        <Alert color="yellow" title="No builds published yet">
          The operator hasn't published any binaries from this backend. Once
          the <Code>/data/builds</Code> directory contains the BeamMP-Server
          and Launcher binaries, they'll appear here automatically.
        </Alert>
      )}

      <SimpleGrid cols={{ base: 1, md: 2 }}>
        {entries.map(({ key, entry }) => {
          const meta = META[key];
          const Icon = meta.icon;
          const href = absolute(entry.url);
          return (
            <Card key={key} withBorder padding="lg" radius="md">
              <Stack gap="sm">
                <Group justify="space-between" align="flex-start">
                  <Group gap="sm" align="flex-start">
                    <Icon size={28} />
                    <Box>
                      <Text fw={600}>{meta.title}</Text>
                      <Text size="xs" c="dimmed">
                        {meta.subtitle}
                      </Text>
                    </Box>
                  </Group>
                  <Badge variant="light">{formatBytes(entry.size)}</Badge>
                </Group>

                <Text size="xs" c="dimmed" style={{ wordBreak: "break-all" }}>
                  <strong>SHA-256:</strong> <Code>{entry.sha256}</Code>
                </Text>

                <Group justify="space-between">
                  <Anchor href={href} size="xs" target="_blank" rel="noopener noreferrer">
                    {entry.filename}
                  </Anchor>
                  <Button
                    component="a"
                    href={href}
                    download={entry.filename}
                    leftSection={<IconDownload size={16} />}
                    size="sm"
                  >
                    Download
                  </Button>
                </Group>
              </Stack>
            </Card>
          );
        })}
      </SimpleGrid>
    </Stack>
  );
}
