// Runtime theme bootstrap: fetches the admin-configured wallpaper from
// `/theme` and pushes the values into CSS custom properties on :root so
// the rules in `styles.css` (`.auth-bg::before`, `body.app-bg-on::before`,
// the AppShell overrides) react automatically.
//
// `/theme` is public so the login screen can render the same wallpaper
// before the user is authenticated.
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "./api";

export interface ThemeConfig {
  background_url: string;
  background_blur_px: number;
  background_dim_pct: number;
  apply_to_auth_only: boolean;
}

export const THEME_QUERY_KEY = ["theme"] as const;

export function useTheme() {
  return useQuery<ThemeConfig>({
    queryKey: THEME_QUERY_KEY,
    queryFn: () => api.get<ThemeConfig>("/theme"),
    staleTime: 60_000,
  });
}

/** Escape characters that would break out of a CSS `url("…")` value. */
function cssEscapeUrl(url: string): string {
  return url.replace(/\\/g, "%5C").replace(/"/g, "%22");
}

export function applyThemeVars(theme: ThemeConfig | undefined): void {
  if (typeof document === "undefined" || !theme) return;
  const root = document.documentElement;
  if (theme.background_url) {
    root.style.setProperty(
      "--bg-image",
      `url("${cssEscapeUrl(theme.background_url)}")`,
    );
  } else {
    root.style.setProperty("--bg-image", "none");
  }
  root.style.setProperty("--bg-blur", `${theme.background_blur_px}px`);
  // 0% dim → brightness(1.0); 100% dim → brightness(0.1) (clamped so the
  // image is never completely invisible).
  const brightness = Math.max(0.1, 1 - theme.background_dim_pct / 100);
  root.style.setProperty("--bg-brightness", String(brightness));
}

/**
 * Side-effect hook: keeps the :root CSS variables in sync with the
 * admin's theme. Returns the resolved theme so callers can use it for
 * conditional logic (e.g. toggling the body background class).
 *
 * The effect intentionally depends on the *primitive* fields rather
 * than the query object — that way React Query refetches don't trigger
 * a no-op CSS rewrite, which the browser would otherwise treat as a
 * change worth re-evaluating (causing visible flicker on the blurred
 * backdrop).
 */
export function useApplyTheme(): ThemeConfig | undefined {
  const q = useTheme();
  const t = q.data;
  const url = t?.background_url;
  const blur = t?.background_blur_px;
  const dim = t?.background_dim_pct;
  useEffect(() => {
    if (t) applyThemeVars(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, blur, dim]);
  return t;
}
