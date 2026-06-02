# AGENTS.md

## Cursor Cloud specific instructions

### Product

Single Flask app (**Novel Prep Math Studio**): SAT Math practice, placement diagnostic, course materials, and admin console. No npm frontend build; SQLite is embedded (`sat.db` by default, overridable via `DB_PATH`).

### System dependency (Ubuntu)

The dev venv requires **`python3.12-venv`** (or matching your `python3` version). If `python3 -m venv .venv` fails with `ensurepip is not available`, install it once per VM:

```bash
sudo apt-get update && sudo apt-get install -y python3.12-venv
```

### Install / refresh dependencies

From repo root (see also `run_dev.sh`):

```bash
test -f .env || cp .env.example .env
test -d .venv || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
```

### Run the app (dev)

```bash
./run_dev.sh
# or: .venv/bin/python app.py
```

Listens on **http://0.0.0.0:8888** (`debug=True`). Health check: `GET /health` → `ok`.

Use **tmux** for long-running dev server sessions in Cloud Agent VMs.

### Lint / tests

There is no configured ruff/flake8/pytest suite in-repo. Practical checks:

- **Syntax:** `.venv/bin/python -m compileall -q app.py latex_parser.py beamer_parser.py answer_grader.py verify_submission_flow.py`
- **Automated flow:** `.venv/bin/python verify_submission_flow.py` — initializes DB and checks answer extraction + templates. **Practice HTTP checks require an authenticated session** (unauthenticated `GET /practice/...` returns 302). After first DB init, seed user `Jack` exists from `data/render_users_seed.json` but passwords are not in git; set a known hash locally or use `/admin/setup` when no admin exists.
- **Authenticated smoke (example):** log in via test client or browser, then open `/practice/algebra/1_1/0` and submit via `/practice/submit`.

### Auth / first login

- Fresh DB with no admin: **`/admin/setup`** to create the first admin.
- Render seed: on first `init_db()`, accounts from `data/render_users_seed.json` may be imported (e.g. `Jack` admin). Plaintext passwords are not stored in the repo.

### Optional env (`.env`)

Copy from `.env.example`: `SECRET_KEY`, optional `DESMOS_API_KEY`, `OPENAI_API_KEY`, `DB_PATH`. MathJax loads from CDN in the browser for LaTeX rendering.

### Content rebuild (only when editing `.tex` sources)

`python3 scripts/build_question_bank.py` and `python3 scripts/build_course_materials.py` — not needed for normal app dev when `data/question_bank.json` / `data/course_materials.json` are present.
