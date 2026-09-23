TRI-BACK — Study prototype UI (research)
=======================================

WHAT IT IS
----------
Reflex web app for the TRI-BACK research study. Researchers
log in here. All three experimental arms call the SAME bot
backend; only the presentation differs (baseline text / reasoning / graph panel).

Pages:  /        login
        /chat    conversation
        /admin   researcher dashboard


HOW TO RUN LOCALLY
------------------
Two PowerShell windows. Bot first, then the study UI.

Copy .env.example to .env. Set TRI_BACK_ADMIN_PASSWORD.
In bot/.env set TRI_BACK_ALLOW_OPEN_API=1 (local chat without an API key).

Do not put the bot on 8000. Reflex WebSocket must own 8000; the bot stays on 8001.
Open http://localhost:3000 (not 3001).

Terminal 1 — bot:

  cd bot
  .\.venv\Scripts\Activate.ps1
  uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

Wait until http://127.0.0.1:8001/ready is up (warmup can take 20-40s).
Start uvicorn from the bot/ folder (not the repo root) so reload does not
pick up study-app files.

Terminal 2 — study UI:

  cd prototypes/tri_back_study_app
  .\.venv\Scripts\Activate.ps1
  python scripts/run_local.py --kill-stale

--kill-stale frees leftover Reflex processes on 3000/8000 so the WebSocket
does not jump onto 8001 (that 403's against the bot). The launcher also
restores missing .web template files.

Same launcher from repo root:

  python prototypes/tri_back_study_app/scripts/run_local.py --kill-stale

Expected ports:
  UI                 http://localhost:3000
  Reflex WebSocket   http://127.0.0.1:8000
  Bot API            http://127.0.0.1:8001

First-time only (venv), then run_local.py as above:

  cd prototypes/tri_back_study_app
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt

The study app creates an empty SQLite database on first start.

Optional: .env with CHATBOT_BASE_URL=http://127.0.0.1:8001

Do not use this launcher for Cloud Run. Public hosting still uses
bot/app/services/public_host/cloud_run/scripts/entrypoint_study.sh.


LOGIN
-----
Admin: username admin, password TRI_BACK_ADMIN_PASSWORD
       (required in .env for local and hosted runs)


RELATED
-------
- Bot backend:  ../../bot/readme.txt
- Session lab:  ../../Testing/readme.txt
- Cloud Run notes: ../../bot/app/services/public_host/cloud_run/STUDY_SERVICE.md
