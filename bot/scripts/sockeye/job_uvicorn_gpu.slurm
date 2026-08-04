#!/bin/bash
#SBATCH --job-name=digimsk-bot
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=48G
#SBATCH --time=04:00:00
#SBATCH --output=slurm-%j.out
#SBATCH --error=slurm-%j.err
#
# TODO: Replace account and partition with values valid for YOUR allocation on Sockeye.
# Typical patterns (verify): --account=def-USERNAME or rrg-YOURGROUP
#                            --partition=interactive_gpu OR gpu_* (See ARC Confluence.)
#SBATCH --account=REPLACE_WITH_YOUR_ACCOUNT
#SBATCH --partition=REPLACE_WITH_PARTITION
#SBATCH --gres=gpu:1

# Submit from repo root containing pyproject.toml, e.g.:
#   cd /scratch/$USER/digimsk/repo/bot
#   sbatch scripts/sockeye/job_uvicorn_gpu.slurm

set -euo pipefail

ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "${ROOT}"

bash scripts/sockeye/run_uvicorn.sh
