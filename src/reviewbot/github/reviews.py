"""Validate finding anchors against the diff and post one batched review."""

from reviewbot.github.client import GitHubClient
from reviewbot.schemas import Finding


def post_review(gh: GitHubClient, pr_number: int, commit_sha: str,
                summary: str, findings: list[Finding]) -> None:
    """POST /pulls/{n}/reviews with event=COMMENT and inline comments.

    Every finding must already be anchored to a line present on side RIGHT of
    the diff (validated in postprocess) or GitHub rejects the whole review.
    """
    raise NotImplementedError("weekend 1")
