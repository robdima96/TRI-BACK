# Running DigiMSKbot on UBC ARC Sockeye

This repo is a **FastAPI** app (`uvicorn app.main:app`). On Sockeye you typically:

1. Keep the checkout and **`data/`** (Chroma DB, checkpoints) under **`/scratch/...`** (fast I/O, enough space)—not under tiny home quotas alone.
2. Place **generator** and **encoder** weight dirs on **`/scratch`** and point **`DIGIMSK_GENERATOR_DIR`** / **`DIGIMSK_ENCODER_DIR`** at those paths (the app loads from disk with **`local_files_only=True`**; it will not pull models from the internet unless you change that elsewhere).
3. Use a **GPU** node when you enable RAG/query embeddings (`torch`) and local generation (`DIGIMSK_LOAD_*` defaults); VRAM demand depends on model size (`float16`, `device_map="auto"` in the generator).

Official ARC references: [Running Jobs](https://confluence.it.ubc.ca/spaces/UARC/pages/318409964/Running+Jobs), [Software / modules](https://confluence.it.ubc.ca/spaces/UARC/pages/187507341/Software), [About Sockeye](https://confluence.it.ubc.ca/spaces/UARC/pages/319206082/About+Sockeye). Hostnames mentioned in onboarding: **`sockeye.arc.ubc.ca`**, data transfer **`dtn.sockeye.arc.ubc.ca`**.

---

## 1. Clone and workspace layout

SSH to Sockeye (or use an OnDemand **terminal** tied to your allocation):

```bash
# Example: yours may be def-USER, rrg-FOO, etc.
mkdir -p "/scratch/$USER/digimsk"
cd "/scratch/$USER/digimsk"
git clone https://github.com/<YOUR_USERNAME>/DigiMSKbot.git repo
cd repo/bot        # Git repo root (pyproject.toml and app/)
```

Large artifacts (recommended alongside the clone):

```
/scratch/$USER/digimsk/models/encoder/GliNER-BioMed-or-your-encoder/
/scratch/$USER/digimsk/models/generator/Mistral7Binstruct-or-your-generator/
/scratch/$USER/digimsk/chroma/
/scratch/$USER/digimsk/checkpoints.sqlite   # optional: set DIGIMSK_CHECKPOINT_SQLITE
```

Copy weights from your workstation with **scp/rsync**, or upload via **`dtn.sockeye.arc.ubc.ca`** / Globus **`ubcarc#sockeye`** per ARC docs—do not commit weights to Git.

---

## 2. Python environment

Load a **recent Python module** stack that matches **`requires-python >= 3.11`** on Sockeye (exact module names change; check **`module spider python`**):

```bash
module purge
module load gcc opencv mpi4py python/3.12 cuda  # example only — validate on Sockeye
cd "/scratch/$USER/digimsk/repo/bot"
bash scripts/sockeye/setup_venv.sh
```

That script creates **`bot/.venv`** and runs **`pip install -e '.[dev]'`**. Installing **`torch`** may require the CUDA wheel aligned with the cluster’s driver/CUDA modules—if `pip install` fails, install PyTorch following [ARC/software notes](https://confluence.it.ubc.ca/spaces/UARC/pages/187507341/Software) or use a conda stack if your group standardizes on it.

Activate later:

```bash
source "/scratch/$USER/digimsk/repo/bot/.venv/bin/activate"
```

---

## 3. Environment variables (`/.env`)

The app reads **`bot/.env`** (see **`app/config.py`**). Copy the example:

```bash
cp scripts/sockeye/env.example .env
nano .env
```

Set **`DIGIMSK_ENCODER_DIR`** and **`DIGIMSK_GENERATOR_DIR`** to **`/scratch/...`** paths that contain **`config.json`** plus weights (safetensors for the generator).

Optional toggles:

- **`DIGIMSK_LOAD_RAG=0`** — skip Chroma and query embeddings if you want a lighter smoke test without a populated vector DB (generator still needs weights for full `/ready`).
- **`DIGIMSK_LOAD_NER=0`** — default in code fallback is **`False`** unless you enable NER in env.

Point persistence to scratch:

- **`DIGIMSK_CHROMA_PATH=/scratch/$USER/digimsk/chroma`**
- **`DIGIMSK_CHECKPOINT_SQLITE=/scratch/$USER/digimsk/langgraph_checkpoints.sqlite`**
- **`DIGIMSK_SESSION_STORE_DIR=/scratch/$USER/digimsk/sessions`**

---

## 4. Interactive use (OnDemand desktop or SSH on a GPU node)

**OnDemand → Desktop** gives you a browser desktop on a compute node; run a terminal inside it.

**SSH**: request an interactive GPU allocation as your PI allows (**`salloc` / `interactive_*` partition names vary**).

From the **`bot`** directory:

```bash
source .venv/bin/activate
export PORT=8000
uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
```

- Inside the desktop: open **`http://127.0.0.1:8000/docs`**.
- From your laptop: use **SSH local forwarding** (`ssh -L 8000:localhost:8000 ...`) exactly as ARC documents for reaching the compute node—you often forward through the login node per their current policy.

Smoke checks:

```bash
curl -s "http://127.0.0.1:${PORT:-8000}/health"
curl -s "http://127.0.0.1:${PORT:-8000}/ready"
```

---

## 5. Batch job (Slurm)

From **`bot/`** after editing **`scripts/sockeye/job_uvicorn_gpu.slurm`** (account, partition, `--gres`, `--mem`, `--time`):

```bash
sbatch scripts/sockeye/job_uvicorn_gpu.slurm
tail -f slurm-<jobid>.out
```

The job runs **`scripts/sockeye/run_uvicorn.sh`** (activates **`bot/.venv`**, starts **`uvicorn`** bound to **`0.0.0.0`**). Logs go to **`slurm-<jobid>.out` / `.err`**.

Notes:

- **Long-running inference services** may be discouraged or billed differently depending on allocation policy; interactive testing is fine for prototyping.
- If the job exits immediately, read **`slurm-*.err`** for missing CUDA, missing modules, or wrong **`--partition`/`--account`**.

---

## 6. Checklist before you rely on `/ready`

| Check | Env / path |
|--------|-------------|
| Encoder **`config.json`** under encoder dir | `DIGIMSK_ENCODER_DIR` |
| Generator **`.safetensors`** files | `DIGIMSK_GENERATOR_DIR` |
| Chroma writable if RAG enabled | `DIGIMSK_CHROMA_PATH`, collection name |
| SQLite checkpoint writable | `DIGIMSK_CHECKPOINT_SQLITE` |
| Torch sees GPU **(optional)** | `python -c "import torch; print(torch.cuda.is_available())"` |

If anything fails, **`GET /ready`** returns **`503`** with per-subsystem details.
