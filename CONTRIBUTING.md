# Contributing

Thanks for considering a contribution to Decentralized-BMP V2.

## Quick start

```bash
# Backend
cd backend
python -m venv .venv && . .venv/Scripts/activate
pip install -r requirements.txt
uvicorn app.main:create_app --factory --reload --port 8420

# Frontend
cd frontend
npm install
npm run dev
npm run typecheck   # MUST pass before opening a PR
```

## Pull requests

1. Fork and create a topic branch off `main` (`feat/<thing>`, `fix/<thing>`, `docs/<thing>`).
2. Keep PRs focused — one logical change per PR.
3. Make sure:
   - `npm run typecheck` passes in `frontend/`.
   - The backend still imports cleanly and `uvicorn app.main:create_app --factory` boots.
   - You did **not** commit `.env`, `node_modules/`, build output, or DB files.
4. Update `README.md` / `.env.example` if you added or renamed a config key.
5. Open the PR against `main` with a short description of *what* and *why*.

## Code style

- **Python:** type-hinted, PEP 8, no new global state. Argon2 / JWT helpers live in `app/security.py` — don't reinvent them.
- **TypeScript:** strict mode, no `any` unless unavoidable, prefer Mantine components over hand-rolled markup.
- **Shell:** `bash` (`set -euo pipefail`), no aliases.

## Reporting bugs

Use [GitHub Issues](https://github.com/musanajam11/Decentralized-BMP-V2/issues). Include:

- What you ran (compose version, OS, deploy target).
- What you expected vs. what happened.
- Relevant logs (`docker compose logs backend --tail 200`).
- Whether `.env` was customised in any non-obvious way (don't paste secrets).

## Reporting security issues

**Don't** open a public issue. See [SECURITY.md](SECURITY.md).

## License

By contributing you agree that your contributions are licensed under the project's [AGPL-3.0-or-later](LICENSE).
