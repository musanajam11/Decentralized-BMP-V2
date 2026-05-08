<!--
Thanks for the PR! A few quick checks:
-->

## What
<!-- One or two sentences. -->

## Why
<!-- Motivation / linked issue. Closes #123 -->

## Checklist
- [ ] `cd frontend && npm run typecheck` passes
- [ ] Backend still boots (`uvicorn app.main:create_app --factory`)
- [ ] No secrets, `.env`, `node_modules/`, or DB files committed
- [ ] `README.md` / `.env.example` updated if config keys changed
- [ ] If this is a security fix: see [SECURITY.md](../SECURITY.md) — coordinated disclosure preferred over a public PR
