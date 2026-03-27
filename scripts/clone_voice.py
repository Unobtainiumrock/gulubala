#!/usr/bin/env python3
"""Upload a voice reference file to Eigen and print the resulting voice_id."""

import argparse
import os
import sys

# Ensure project root is on the import path so `client.*` / `config.*` resolve.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()

from client.eigen import upload_voice_reference  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Clone a voice via Eigen AI")
    parser.add_argument("file", help="Path to a WAV or MP3 voice reference file")
    args = parser.parse_args()

    file_path = os.path.expanduser(args.file)
    try:
        voice_id = upload_voice_reference(file_path)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"\nVoice cloned successfully!")
    print(f"  voice_id = {voice_id}")
    print(f"\nAdd this to your .env file:")
    print(f"  DEMO_VOICE_ID={voice_id}")


if __name__ == "__main__":
    main()
