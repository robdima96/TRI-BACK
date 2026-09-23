# TRI-BACK study prototype

See **[readme.txt](readme.txt)** for what this app is and how to run it locally.

```powershell
cd bot
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

```powershell
cd prototypes/tri_back_study_app
.\.venv\Scripts\Activate.ps1
python scripts/run_local.py --kill-stale
```

Open **http://localhost:3000**. Reflex WebSocket is `:8000`; bot API is `:8001`.
