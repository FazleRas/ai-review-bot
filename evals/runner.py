"""Offline eval runner: replays the pipeline against labeled diff fixtures.

Modes:
  --cassette  replay recorded provider responses (deterministic, free, runs in CI)
  --live      real API calls; spends free-tier daily budget, so run sparingly

Reports precision, recall, false-positive rate on clean diffs, and
hypothetical paid-tier cost per case. Lands in weekend 3.
"""

if __name__ == "__main__":
    raise SystemExit("eval runner lands in weekend 3 — see docs/architecture.md")
