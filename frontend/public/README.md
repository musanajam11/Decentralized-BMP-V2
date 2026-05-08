# Drop your branding here

The frontend looks for these files at runtime:

- `cm-logo.png`        — square icon (used as favicon and as the navbar mark when no wordmark is present)
- `cm-wordmark.png`    — wide wordmark (used in the navbar at full width)

Until you add them, the navbar falls back to a text wordmark and the favicon
will 404 silently. Suggested sizes:

- `cm-logo.png`     — 256×256 (transparent PNG)
- `cm-wordmark.png` — 600×140 (transparent PNG)

> Do **not** rename the files — `index.html` references `cm-logo.png` directly
> for the favicon, and `Layout.tsx` probes for `cm-wordmark.png` first then
> falls back to `cm-logo.png` then to the text wordmark.
