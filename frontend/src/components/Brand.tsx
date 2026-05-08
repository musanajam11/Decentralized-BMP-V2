import { useEffect, useState } from "react";
import { Group, Image, Text } from "@mantine/core";

/** Tries /cm-wordmark.png, then /cm-logo.png, finally falls back to text. */
export function Brand() {
  const [src, setSrc] = useState<string | null>("/cm-wordmark.png");

  useEffect(() => {
    if (!src) return;
    const img = new window.Image();
    img.onload = () => {
      /* keep current src */
    };
    img.onerror = () => {
      setSrc((cur) => (cur === "/cm-wordmark.png" ? "/cm-logo.png" : null));
    };
    img.src = src;
  }, [src]);

  if (!src) {
    return (
      <Text fw={800} size="lg" c="blue">
        Decentralized<Text span c="dimmed">·BMP</Text>
      </Text>
    );
  }
  return (
    <Group gap="xs">
      <Image src={src} h={32} fit="contain" alt="Decentralized BMP" />
    </Group>
  );
}
