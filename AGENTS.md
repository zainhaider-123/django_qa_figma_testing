# AGENTS.md

Repo-specific guidance for OpenCode agents working in this codebase.

## What this is

A single-user Django QA tool that compares a Figma frame render against a
Playwright screenshot of a live site, producing a pixel-diff report.
**v2 design is synchronous** — no Celery, no Redis, no Postgres. SQLite only.
The full design lives in `plans/v2.md`; read it before non-trivial work.

## Stack

- Django 6.0.6, SQLite, python-decouple for env (`config(...)` in settings)
- django-allauth 65.18.0 with the **built-in Figma OAuth2 provider**
  (`allauth.socialaccount.providers.figma`) — do not hand-roll OAuth.
  Tokens live in allauth's `SocialToken`/`SocialAccount`; allauth handles
  refresh. Figma credentials are configured via a `SocialApp` row in admin,
  **not** hardcoded in `SOCIALACCOUNT_PROVIDERS`.
- Planned (per v2, not yet in `requirements.txt`): `Pillow`, `pixelmatch`,
  `playwright`. After adding `playwright`, run `playwright install chromium`.

## Project layout

- `qa_figma_testing_main/` — Django project config (settings, urls, wsgi/asgi)
- `figma_auth/` — Figma connection + API client app (currently stubs)
- `qa/` — **not yet created**; v2 adds it for `TestRun` model, comparison
  services, and report views
- `templates/` (project-wide, base.html) and `static/` at repo root
- `plans/` — design docs (`v1.md`, `v2.md`); `v2.md` is current

## Commands

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
python manage.py test                      # all tests
python manage.py test figma_auth           # single app
python manage.py test figma_auth.tests.Thing.test_method  # single test
```

Env is managed via `mise` (`mise.toml` pins `python = "latest"`); a local
`.venv/` exists. Activate the venv or use `mise` before running anything.

## Environment

`.env` (gitignored) is required — settings crash without it. Required vars:
`DJANGO_SECRET_KEY`, `DJANGO_DEBUG`. For Figma OAuth to work you also need
`FIGMA_CLIENT_ID`, `FIGMA_CLIENT_SECRET` in `.env`, **plus** a matching
`SocialApp` row in admin (client_id/secret + assigned Site). `.env.example`
is currently incomplete — when you touch env vars, update it too.

`FIGMA_REDIRECT_URI` is **not** needed — allauth uses
`/accounts/figma/login/callback/` automatically.

## Known incomplete setup (Phase 0, v2 plan)

These are intentionally not yet done; check before assuming "done":
- `SOCIALACCOUNT_PROVIDERS` still contains a leftover `'google'` entry — remove
  it; Figma config should come from the DB `SocialApp`, not this dict.
- `templates/base.html` is empty — needs a minimal HTML skeleton.
- `MEDIA_ROOT`/`MEDIA_URL` not yet configured (v2 stores figma PNGs,
  screenshots, and diff images there).
- `qa` app not yet created.

## Conventions

- Settings use `decouple.config(...)`; `DEBUG` is `cast=bool`, so `.env` values
  like `True`/`False` work.
- `ALLOWED_HOSTS` is auto-populated with `127.0.0.1`/`localhost` only when
  `DEBUG` is true.
- All v2 views must require login (`@login_required` / `LoginRequiredMixin`).
- Figma API rate limit is 300 req/min — be aware in any client code.