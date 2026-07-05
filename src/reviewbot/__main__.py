"""Action entry point: read the pull_request event, run the pipeline, post one review.

Wiring lands in weekends 1-2 (see docs/architecture.md for the stage plan).
"""

import json
import os
import sys
from pathlib import Path

from reviewbot.config import BotConfig


def main() -> int:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        print("reviewbot: GITHUB_EVENT_PATH not set — must run inside a GitHub Action")
        return 1
    event = json.loads(Path(event_path).read_text())
    pr = event.get("pull_request")
    if pr is None:
        print("reviewbot: not a pull_request event, nothing to do")
        return 0

    config = BotConfig.load(Path(os.environ.get("REVIEWBOT_CONFIG", ".github/reviewbot.yml")))
    print(f"reviewbot: PR #{pr['number']} — models {config.models.triage} → {config.models.review}")
    print("reviewbot: pipeline not wired yet (weekend 1-2) — exiting cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
