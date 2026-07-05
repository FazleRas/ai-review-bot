# Architecture

## What this is

v1 is a **diff reviewer**: a PR opens → a GitHub Action triggers → the bot reads
the changed hunks → an LLM posts inline review comments. It deliberately does
not read the whole repository — that context layer (retrieval over the
codebase) is the v2 upgrade, not the v1 identity.

## Pipeline

```
pull_request event (opened | synchronize | reopened | ready_for_review)
  │  concurrency group per PR, cancel-in-progress
  ▼
1. FETCH        GET /pulls/{n}/files (paginated per-file patches)
  ▼
2. FILTER       drop lockfiles/generated/binary/removed files, ignore globs
  ▼
3. CHUNK        per-file → per-hunk, context expansion, token budgeting
  ▼
4. RATE LIMIT   client-side throttle: RPM sliding window + RPD daily budget,
                retry/backoff on 429s; daily exhaustion → graceful partial review
  ▼
5. TRIAGE       gemini-2.5-flash-lite scores chunks 0-10; below threshold = skip
  ▼
6. REVIEW       gemini-2.5-flash, reasoning on, structured output → Findings
  ▼
7. POSTPROCESS  anchor validation, confidence threshold, dedupe, comment cap
  ▼
8. IDEMPOTENCY  content-based fingerprints vs existing comments (survives force-push)
  ▼
9. POST         one review: summary body + inline comments (path, line, side=RIGHT)
  ▼
10. TELEMETRY   per-stage tokens/latency + hypothetical paid-tier cost → step summary
```

## Design decisions

**Provider-agnostic LLM interface.** The pipeline talks to a `Provider`
protocol, never to a vendor SDK. The Gemini adapter shipped first (free-tier
development); an Anthropic adapter slots behind the same interface. Vendor
knobs stay in adapters — the protocol exposes intent (`reasoning: bool`), and
each adapter translates (Gemini: `thinking_budget` −1/0; Anthropic: adaptive
thinking).

**The constraint is rate limit budget, not dollars.** On the free tier, RPD is
the scarce resource. That forced three features that were decorative in a
paid-tier design: the triage tier (spend review-model requests only on chunks
that matter), the client-side rate limiter (two clocks: RPM for burst
smoothing, RPD for the real cap, with graceful partial-review degradation),
and cassette-based eval replay (live eval runs spend the same budget as
reviews, so recorded responses are the default and CI regression runs are
free).

**Structured outputs everywhere.** Both models return JSON validated against
Pydantic schemas (`Finding`, `TriageResult`). No regex-parsing of LLM prose.

**Content-based idempotency.** Comment fingerprints hash the flagged lines'
content, not line numbers, so re-runs after force-pushes skip already-posted
findings even when the diff shifted.

**Fork-PR security policy.** v1 reviews same-repo PRs only
(`head.repo.full_name == github.repository`). Fork PRs can't read secrets, and
the `pull_request_target` + untrusted-checkout pattern is a known RCE vector.
Minimal permissions block: `contents: read`, `pull-requests: write`.

## Eval harness (weekend 3)

Labeled cases mined from real repo history: PRs whose bugs were fixed by later
commits give ground-truth (diff, finding-location) pairs; deliberately clean
diffs measure the false-positive rate. Runner replays the pipeline offline —
`--cassette` mode (recorded provider responses, deterministic, runs in CI on
every prompt change) or `--live` (spends real budget, run sparingly). Metrics:
precision, recall, FP rate on clean diffs, hypothetical cost per PR, latency.
Cassettes record at the Provider boundary, so the same cases replay against
any future adapter — that's the provider benchmark dataset.

## Future work / paid-tier optimizations

- **Prompt caching** — on Anthropic, `cache_control` on the long system prompt
  would serve calls 2..N of a run at ~10% input price; Gemini has its own
  context caching with different mechanics/minimums. Not wired because the
  free tier removes the incentive; the lever is documented because it's the
  first thing to turn on if this moves to paid traffic.
- **Anthropic adapter** behind the existing `Provider` protocol + cross-provider
  benchmark on the eval set.
- **v2: repository context layer** — retrieval (AST-aware chunking via
  tree-sitter, symbol-graph lookup, embeddings as one retriever among several)
  feeding the review pass.

## Free-tier data caveat

Google's free tier may use prompts/outputs for model improvement. Fine for the
public portfolio repos this bot dogfoods on; **do not run it on private or
proprietary repos while on the free tier.**
