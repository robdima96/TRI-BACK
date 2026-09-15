TRI-BACK — Study prototype UI (research)
=======================================

WHAT IT IS
----------
Reflex web app for the TRI-BACK research study (formerly DigiMSK). Participants
and researchers log in here. All three experimental arms call the SAME bot
backend; only the presentation differs (baseline text / reasoning / graph panel).

Pages:  /        login
        /chat    conversation
        /admin   researcher dashboard


HOW TO RUN LOCALLY
------------------
Two PowerShell windows. Bot first, then the study UI.

Do not put the bot on 8000. Reflex WebSocket must own 8000; the bot stays on 8001.
Open http://localhost:3000 (not 3001).

Terminal 1 — bot:

  cd "C:\ROBS STUFF\UBC Postdoctoral Fellowship\DigiMSKbot\bot"
  .\.venv\Scripts\Activate.ps1
  uvicorn app.main:app --reload --host 127.0.0.1 --port 8001

Wait until http://127.0.0.1:8001/ready is up (warmup can take 20-40s).
Start uvicorn from the bot/ folder (not the repo root) so reload does not
pick up study-app files.

Terminal 2 — study UI:

  cd "C:\ROBS STUFF\UBC Postdoctoral Fellowship\DigiMSKbot\prototypes\tri_back_study_app"
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

First-time only (venv + roster/login accounts), then run_local.py as above:

  cd "C:\ROBS STUFF\UBC Postdoctoral Fellowship\DigiMSKbot\prototypes\tri_back_study_app"
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  python scripts/generate_roster.py
  python scripts/init_db.py
  python scripts/seed_users.py --roster data/study_roster.csv

Optional: .env with CHATBOT_BASE_URL=http://127.0.0.1:8001

Do not use this launcher for Cloud Run. Public hosting still uses
bot/app/services/public_host/cloud_run/scripts/entrypoint_study.sh.


LOGIN
-----
Admin:        username admin, password TRI_BACK_ADMIN_PASSWORD
              (local fallbacks triback / digimsk if unset and not in public mode)
Participant:  study ID + password from data/participant_credentials.csv
              (created when you seed; keep private)


RELATED
-------
- Bot backend:  ../../bot/readme.txt
- Session lab:  ../../Testing/readme.txt
- Cloud Run notes: ../../bot/app/services/public_host/cloud_run/STUDY_SERVICE.md
