DigiMSK — Study prototype UI (research)
=======================================

WHAT IT IS
----------
Reflex web app for the DigiMSK research study. Participants and researchers
log in here. All three experimental arms call the SAME bot backend; only the
presentation differs (baseline text / reasoning / graph panel).

Pages:  /        login
        /chat    conversation
        /admin   researcher dashboard


HOW TO RUN LOCALLY
------------------
Prerequisites: bot already running on http://127.0.0.1:8001 (see bot/readme.txt).
Python 3.11+, Node.js 18+ (Reflex frontend toolchain).

  cd prototypes/digimsk_study_app
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  pip install -r requirements.txt
  python scripts/generate_roster.py
  python scripts/init_db.py
  python scripts/seed_users.py --roster data/study_roster.csv
  # Optional: .env with CHATBOT_BASE_URL=http://127.0.0.1:8001
  reflex run

Open:  http://localhost:3000
  (Reflex backend WebSocket uses port 8000 — do not put the bot on 8000.)


LOGIN
-----
Admin:        username admin, password DIGIMSK_ADMIN_PASSWORD
              (local fallback digimsk if unset and not in public mode)
Participant:  study ID + password from data/participant_credentials.csv
              (created when you seed; keep private)


RELATED
-------
- Bot backend:  ../../bot/readme.txt
- Session lab:  ../../Testing/readme.txt
- Cloud Run notes: ../../bot/app/services/public_host/cloud_run/STUDY_SERVICE.md
