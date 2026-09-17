#!/usr/bin/env python3
"""Smoke-test Vertex Gemini using user Application Default Credentials (no key file)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_BOT_ROOT = Path(__file__).resolve().parents[1]
if str(_BOT_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOT_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project",
        help="GCP project ID (default: TRI_BACK_VERTEX_PROJECT_ID from .env)",
    )
    parser.add_argument(
        "--location",
        default=None,
        help="Vertex region (default: TRI_BACK_VERTEX_LOCATION from .env)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Gemini model id (default: TRI_BACK_GENERATOR_MODEL from .env)",
    )
    parser.add_argument(
        "--prompt",
        default="Reply with exactly one word: OK",
        help="Test prompt",
    )
    args = parser.parse_args()

    from app.config import settings
    from app.services.generator_backends import _extract_response_text
    from app.services.vertex_auth import vertex_adc_status

    project = args.project or settings.vertex_project_id
    location = args.location or settings.vertex_location
    model = args.model or settings.generator_model

    print("=== Vertex user ADC smoke test ===")
    adc_ok, adc_detail = vertex_adc_status()
    print(f"ADC: {'ok' if adc_ok else 'FAIL'} — {adc_detail}")
    if not adc_ok:
        print(
            "\nNext steps:\n"
            "  1. Install Google Cloud SDK (or: conda install -c conda-forge google-cloud-sdk)\n"
            "  2. Open a NEW terminal\n"
            "  3. gcloud auth application-default login\n"
            "  4. gcloud config set project YOUR_PROJECT_ID\n"
            "  5. gcloud auth application-default set-quota-project YOUR_PROJECT_ID\n"
            "  6. Ensure GOOGLE_APPLICATION_CREDENTIALS is NOT set\n",
            file=sys.stderr,
        )
        return 1

    if not project or not location:
        print(
            "Set TRI_BACK_VERTEX_PROJECT_ID and TRI_BACK_VERTEX_LOCATION in bot/.env",
            file=sys.stderr,
        )
        return 1

    print(f"Project: {project}")
    print(f"Location: {location}")
    print(f"Model: {model}")

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("pip install -e '.[generator-api]'", file=sys.stderr)
        return 1

    client = genai.Client(vertexai=True, project=project, location=location)
    response = client.models.generate_content(
        model=model,
        contents=args.prompt,
        config=types.GenerateContentConfig(
            max_output_tokens=64,
            thinking_config=types.ThinkingConfig(
                thinking_level="MINIMAL",
                include_thoughts=False,
            ),
        ),
    )
    try:
        text = _extract_response_text(response)
    except Exception as exc:
        print(f"Empty or unusable response from Vertex: {exc}", file=sys.stderr)
        return 1
    print(f"Response: {text!r}")
    if not text:
        print("Empty response from Vertex", file=sys.stderr)
        return 1
    print("=== SUCCESS ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
