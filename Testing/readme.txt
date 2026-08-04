DigiMSK — Session lab (developer testing)
=========================================

WHAT IT IS
----------
A small FastAPI + HTML tool for developers. It does NOT talk to participants.
It reads bot session JSON files and shows transcripts, checklist growth,
coverage, engagement charts, and disposition audits while you debug the bot.


HOW TO RUN LOCALLY
------------------
Prerequisites: session files exist under bot/data/sessions/ (create some by
chatting via the study app or calling the bot API).

  cd Testing
  pip install -r requirements.txt
  uvicorn app:app --reload --port 8765

Open:  http://127.0.0.1:8765

Sessions are loaded from ../bot/data/sessions (relative to the DigiMSK
workspace root). test_log.json appears as a reference row when present.


RELATED
-------
- Bot backend:   ../bot/readme.txt
- Study UI:      ../prototypes/digimsk_study_app/readme.txt
