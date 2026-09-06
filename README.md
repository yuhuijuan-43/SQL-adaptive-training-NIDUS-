# SQL Adaptive Training Platform

An SQL practice platform powered by a knowledge-graph illumination mechanism and an adaptive question-generation algorithm. It includes 58 practice questions (basic / advanced multiple choice) plus 42 real-exam questions (classic Niuke-style SQL fill-in-the-blank), covering common knowledge points such as basic syntax, joins, subqueries, aggregation, and window functions. Practice progress is visualized through the knowledge graph.

## Interface Preview

**Home** — Portal entry, supports 6-language switching

![Home](docs/screenshots/home.png)

**About Us** — Updates and project vision

![About Us](docs/screenshots/about.png)

**Login / Register** — Random username and secure password generation

![Login](docs/screenshots/login.png)

**Practice** — Adaptive progression and answer interface

![Practice](docs/screenshots/practice.png)

## Features

- Three-level knowledge-graph illumination: knowledge points are organized as leaf / branch / root; answering correctly illuminates nodes and visualizes progress
- Adaptive question generation: each round composes a 5-question sequence of "3 multiple choice + 2 fill-in-the-blank"; correct answers accumulate across practice pools and illuminate nodes (idempotent persistence)
- SQL judging: SQL normalization, read-only single-statement validation, sandboxed execution, and result-set comparison
- Question bank: 58 practice questions (29 basic + 29 advanced multiple choice; advanced questions include table DDL and expected output) + 42 classic Niuke-style SQL fill-in-the-blank questions (covering all 29 knowledge tags); full backups at `data/questions_full.json` / `data/exam_questions_full.json`
- Learning loop: level diagnosis → adaptive practice → mistake collection → graph illumination → advanced selection
- Account system: register / login / GitHub one-click login (OAuth2, optional) / session management / admin console (password login + referral-code registration, real-time user activity & system logs, admin-activity audit for the primary admin)
- Framework-free frontend with localized chart library, supports offline deployment
- One-click startup: auto-detects and installs Python, installs dependencies, starts the service, and opens the browser

## Tech Stack

- Backend: Python / Flask / SQLite
- Frontend: vanilla HTML / CSS / JS, ECharts (localized resources)
- Judging: custom SQL normalization + sandboxed execution comparison
- Testing: pytest (149 test cases)

## Quick Start

### One-click startup on Windows

```bat
start_server.bat
```

The script automatically: detects an available Python (downloads and installs it if missing) → installs dependencies → starts the service → opens the browser at `http://localhost:5000`

### Manual startup

```bash
# Install dependencies
pip install -r backend/requirements.txt

# Initialize the question bank
python backend/seeding.py

# Start the service
python backend/run.py
# Visit http://localhost:5000
```

## GitHub One-Click Login (Optional)

The GitHub button on the login page uses the OAuth2 authorization-code flow; anyone can enable it by registering for free:

1. [github.com/settings/developers](https://github.com/settings/developers) → **New OAuth App** (note: an OAuth App, not a GitHub App)
2. Set Application name to anything; set Homepage URL to `http://localhost:5000`; **set Authorization callback URL to `http://localhost:5000/api/oauth/github/callback`** (must match the backend character for character); do not check Enable Device Flow
3. After creation, copy the **Client ID**, click **Generate a new client secret** to create the **Client Secret** (shown only once — save it immediately)
4. Fill in `backend/oauth_config.json` (gitignored; template at `backend/oauth_config.example.json`):

```json
{ "github_client_id": "Ov1.xxxx", "github_client_secret": "xxxx" }
```

Environment variables `GITHUB_OAUTH_CLIENT_ID` / `GITHUB_OAUTH_CLIENT_SECRET` can also override these values (higher priority; recommended for server deployment).

Behavior notes:

- If a GitHub username collides with an existing registered user, `_gh` is appended automatically so the accounts do not interfere; repeated logins with the same GitHub account reuse the same `session_id`, keeping progress continuous
- GitHub accounts cannot log in with a password (their password is a random hash); an admin can reset the password for such an account in the panel to switch it to password login
- A GitHub OAuth App supports only **one** callback URL: when deploying via ngrok or a formal domain, update both the callback URL in GitHub's settings and the local startup address, otherwise the authorization redirect points back to localhost

## Directory Structure

```
├── backend/               # Flask backend
│   ├── app.py             # Routes / API / auth
│   ├── engine.py          # Adaptive question engine (graph illumination)
│   ├── sql_judge.py       # SQL judging engine
│   ├── seeding.py         # Question-bank seed rebuild
│   ├── scraper.py         # Question-bank scraping tool
│   ├── oauth.py           # GitHub OAuth login (config / authorization-code flow / account creation)
│   └── tests/             # pytest test suite (149 test cases)
├── data/                  # Question-bank data sources (JSON / CSV)
│   ├── questions.json     # Practice bank (58 multiple choice; full backup at questions_full.json)
│   ├── exam_questions.json# Real-exam bank (42 Niuke SQL fill-in-the-blank; full backup at exam_questions_full.json)
│   └── knowledge_tags.csv # Knowledge-tag difficulty mapping
├── frontend/              # Frontend pages (vanilla HTML/CSS/JS)
│   ├── index_glass.html   # Portal entry page
│   ├── index.html         # Practice main interface
│   ├── login_glass.html   # Login / register
│   ├── knowledge_map.html # Knowledge-graph illumination view
│   ├── diagnostic.html    # Level diagnosis
│   └── admin*.html        # Admin panel
├── docs/                  # Design docs, specs, and internal manuals
└── start_server.bat       # One-click startup script
```

## Testing

```bash
cd backend
pytest -v        # all 149 test cases pass
```

Covers: SQL judging, graph-illumination rules, learning flow, seed rebuild, API security, and GitHub OAuth login.

## Docs

- [Knowledge Graph Design](docs/knowledge_map.md)
- [Question Format Spec](docs/format_spec.md)

## Notes

- The database (`backend/questions.db`) is rebuilt from the question-bank data sources and is not distributed with the repository
- Server secrets are stored via environment variables / the database and are never hardcoded; GitHub OAuth credentials use environment variables or `backend/oauth_config.json` (neither is distributed with the repository)
