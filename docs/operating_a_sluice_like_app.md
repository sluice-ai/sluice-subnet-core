# Operating a Sluice-like App

## Recommendation

The best way to handle an app like Sluice is to treat it as four separate planes with one immutable contract between them:

1. Build plane
   Router authors package pure routing logic into a pinned artifact plus a manifest.
2. Validation plane
   Validators fetch the exact artifact bytes, sandbox the router, benchmark it on hidden tasks, and score it.
3. Promotion plane
   A small control service consumes validator results, chooses approved manifests, and publishes signed policy snapshots.
4. Serving plane
   A separate customer-facing app loads only approved policy snapshots, injects live provider telemetry, executes the routing policy, and makes the final provider call.

The artifact manifest is the handoff contract. The key rule is:

`benchmark exact artifact bytes offline, then serve only approved artifact bytes online`

That gives you reproducibility, safe rollback, and clean separation between subnet incentives and customer traffic.

## Why This Split Is Best

This repo already has the right core idea: validators score pinned router artifacts instead of following a moving Git branch. The strongest production design extends that idea in two important ways:

- Do not let the live serving path pull directly from the subnet on the request hot path.
- Do not let provider credentials, external network access, or customer prompts enter the validator loop.

That split preserves the strengths of each system:

- Subnet validation is deterministic, adversarial, and isolated.
- Serving is low-latency, stateful, and allowed to use live health signals and provider credentials.
- Promotion is the narrow bridge that decides what moves from "scored" to "servable".

## Target Architecture

## Latency-First Client Design

The public Sluice product should have a very thin client.

The client should not:

- talk to the subnet directly
- download miner artifacts
- compute competitive scores locally
- hold the full provider registry
- make cross-provider routing decisions in the browser

The client should only:

- accept user input
- attach tenant auth and request metadata
- call a nearby Sluice route endpoint
- stream back the chosen provider response
- optionally render route metadata for transparency

Recommended client surfaces:

- TypeScript SDK for browser and Node
- Python SDK for server integrations
- `POST /route` for sync requests
- `POST /route/stream` for streaming responses
- `POST /feedback` for post-hoc quality signals

That keeps the client bundle small, removes chain latency from the user path, and makes browser performance predictable.

## Serving Fast Path

To avoid latency issues, the live request path should be:

1. Client sends a normalized request to a regional Sluice gateway.
2. The gateway reads an in-memory active-policy snapshot.
3. The gateway enriches the task with live provider telemetry.
4. The gateway executes an already-approved router artifact locally.
5. The gateway applies final health and policy guardrails.
6. The gateway calls the selected provider using warm pooled connections.
7. The response is streamed back immediately.

The hot path should never:

- wait on validator consensus
- query miners live
- fetch policy code from remote storage
- rebuild scores from historical subnet data

Latency budget guidance:

- route decision overhead inside the gateway should usually stay under 10 to 20 ms p50
- policy snapshot reads should be memory-local, not database-blocking
- provider health data should be refreshed asynchronously, not pulled inline per request

Operational requirements:

- keep approved router artifacts preloaded on disk and warm in memory
- keep provider price and health tables in memory with background refresh
- use connection pooling and streaming for provider calls
- pin clients to the closest region and fail over using last-known-good policy snapshots

### 1. Build Plane

This is the miner-side authoring workflow.

Responsibilities:

- Build a deterministic router artifact from source.
- Compute the artifact digest.
- Emit a `RouterArtifactManifest`.
- Publish the artifact to immutable storage.
- Announce the manifest to the subnet.

What belongs here:

- `sluice/router/builder.py`
- `sluice/router/artifacts.py`
- CI checks for deterministic packaging, dependency locking, and manifest validation

Design rules:

- The router artifact should be pure decision logic only.
- The router should not contain provider API keys, network calls, or customer-specific state.
- Artifacts should be reproducible from source and versioned by digest first, human version second.

### 2. Validation Plane

This repo is the control plane for validation.

Responsibilities:

- Sample hidden benchmark tasks.
- Query miners for manifests.
- Materialize and verify the exact artifact bytes.
- Sandbox router execution with no network access.
- Score the returned route against task requirements and reference providers.

What belongs here:

- `sluice_subnet/protocol.py`
- `sluice/router/cache.py`
- `sluice/sandbox.py`
- `agent/runner.py`
- `sluice/scorer.py`
- `sluice_subnet/validator/forward.py`

Design rules:

- Validators should never score a moving repository head.
- Validators should never execute provider API calls.
- Benchmarks should stay hidden, versioned, and replayable.
- Scores should be tied to `(manifest_sha256, benchmark_set_version, scorer_version)`.

### 3. Promotion Plane

This is the missing piece that turns subnet scores into something safe for production serving.

Responsibilities:

- Consume validator score history.
- Aggregate by manifest digest, workload type, capabilities, and privacy tier.
- Apply promotion rules such as minimum score, minimum sample count, freshness window, and validator diversity.
- Publish a signed active-policy snapshot.
- Support instant rollback to a previous snapshot.

Recommended output:

```json
{
  "snapshot_version": "2026-05-19T12:00:00Z",
  "policies": [
    {
      "router_name": "sluice-router",
      "router_version": "0.2.4",
      "sha256": "abc123...",
      "artifact_uri": "https://artifacts.example/router.tar.gz",
      "entrypoint_path": "agent.py",
      "entrypoint_callable": "agent_main",
      "workload_types": ["chat", "batch-summary"],
      "required_capabilities": ["json-mode"],
      "privacy_tiers": ["public", "internal"],
      "min_offline_score": 0.91,
      "status": "active"
    }
  ],
  "signature": "..."
}
```

Design rules:

- The serving plane should only read from promotion snapshots, not directly from chain state.
- Promotion should be conservative by default and require enough evidence before activation.
- Rollback should be snapshot-based, not code-based.

### 4. Serving Plane

This is the customer-facing application and should live in a separate codebase.

Responsibilities:

- Accept client requests.
- Normalize them into a routing task shape.
- Attach live provider telemetry such as price, latency, health, quotas, and rate-limit state.
- Load an approved router artifact from the latest signed snapshot.
- Execute the router in a lightweight runtime.
- Apply final safety guardrails before calling the selected provider.
- Record outcome telemetry for future router improvements.

Minimal APIs:

- `POST /route`
- `POST /feedback`
- `GET /policies/active`

Design rules:

- Do not fetch arbitrary miner artifacts during a live request.
- Keep a warmed local cache of approved manifests by digest.
- If the selected provider is unhealthy, use `fallback_provider_ids` or a local emergency policy.
- Keep a "last known good" snapshot on disk for cold start and outage recovery.

## Core Contracts

The current repo already has the right three core data models:

- `RouterArtifactManifest`
- `RoutingTask`
- `RoutingExecutionReport`

The best long-term contract shape is:

1. The serving plane builds a normalized `RoutingTask`.
2. The router artifact returns a `RoutingExecutionReport`.
3. The serving plane treats that report as a route plan, not blind execution authority.

That means the serving layer may still reject or adjust a route if:

- the provider is currently degraded
- the live price exceeds the declared budget
- the privacy tier no longer matches policy
- rate limits or tenant policy forbid the provider

This keeps offline benchmarking meaningful while still allowing safe online execution.

## Scoring Model

The public product language describes Sluice as routing across:

- cost
- latency
- quality
- reliability
- privacy

That means Sluice should use two related but different scoring systems.

### 1. Offline subnet score

This is the miner competition score used by validators.

Its job is to answer:

`did this router choose a strong route under hidden benchmark conditions?`

This score should be versioned and reproducible. It should be tied to:

- scorer version
- benchmark set version
- artifact digest

### 2. Online serving utility

This is the low-latency decision function used by the serving gateway.

Its job is to answer:

`given current provider health and task requirements, which approved route should we use right now?`

This score can use live telemetry and local guardrails, but it should only choose among already-approved policies.

## Important Current Gap

The current repo scorer is intentionally simple, but it does not fully match the public product framing yet.

Today, [sluice/scorer.py](/home/yogesh/Documents/the-sluice/sluice-subnet-core/sluice/scorer.py:16) heavily favors cost:

- cost: `0.70`
- latency: `0.10`
- reliability: `0.08`
- privacy: `0.05`
- calibration: `0.05`
- fallback: `0.02`

Also, quality is currently used as a feasibility threshold in [sluice/scorer.py](/home/yogesh/Documents/the-sluice/sluice-subnet-core/sluice/scorer.py:28), but not as a first-class optimization term in the final weighted score.

If the goal is to match the public Sluice product, the scorer should evolve so quality is first-class rather than only a minimum gate.

## Recommended Scoring Upgrade

Use a two-stage model:

1. Feasibility filter
   Enforce hard constraints first:
   capability match, privacy requirement, max latency, min quality, budget ceiling.
2. Utility score
   Rank feasible providers with a tunable weighted utility:
   cost, latency, quality, reliability, privacy margin, forecast calibration, and fallback quality.

Recommended direction:

- keep hard policy constraints as binary pass/fail
- add direct quality contribution into the final score
- make weights workload-aware instead of one global constant
- version the scorer so validator history stays interpretable

Example workload-aware presets:

- `chat-realtime`
  heavier latency and reliability weighting
- `batch-summarization`
  heavier cost weighting
- `high-trust-enterprise`
  heavier privacy and reliability weighting
- `code-generation`
  heavier quality and reliability weighting

## Data Stores

Use separate stores for separate responsibilities:

- Artifact store
  Immutable object storage keyed by digest.
- Benchmark store
  Hidden task sets, benchmark versions, and scorer versions.
- Evaluation store
  Raw validator reports and aggregated scores.
- Promotion store
  Signed active-policy snapshots and rollback history.
- Telemetry store
  Serving-time latency, success rate, cost, and fallback outcomes.

The most important join key across systems is the artifact digest.

## Security Model

For an app like Sluice, the router is untrusted code until proven otherwise. Treat it that way everywhere.

Required controls:

- immutable digest verification before execution
- sandboxed validator execution with network disabled
- static screening before runtime
- hard CPU, memory, and wall-clock limits
- safe archive extraction and no symlinks
- signed promotion snapshots
- serving-plane allowlist of approved artifacts only

Recommended next hardening steps:

- add manifest signing so miners can attest to artifact ownership
- add dependency allowlists or vendored runtime packaging rules
- store benchmark provenance with every score
- cap artifact size and extracted file count in the cache path

## Request Lifecycle

The healthiest end-to-end flow is:

1. A router author builds an artifact and manifest.
2. The miner announces the manifest to the subnet.
3. Validators benchmark the exact artifact bytes.
4. The promotion service aggregates scores and activates a signed snapshot.
5. The serving layer pulls the latest approved snapshot on a timer.
6. A client request is converted into a `RoutingTask` with live provider telemetry.
7. The serving layer executes the approved router artifact locally.
8. The executor either uses the selected provider or falls back safely.
9. Outcome telemetry feeds the next authoring and promotion cycle.

## What Should Stay Out Of This Repo

To keep this codebase sharp and reliable, avoid pushing these concerns into the subnet repo:

- client auth
- customer prompt storage
- provider API keys
- live provider execution
- tenant-specific rate limits
- billing
- online experimentation dashboards

Those belong in the serving plane.

## Immediate Priorities For This Repo

If we continue building from the current codebase, the best next steps are:

1. Add a promotion snapshot writer/reader contract.
2. Version benchmark sets and scorer logic explicitly in validator outputs.
3. Add manifest signing and verification fields.
4. Enforce artifact size and extracted file-count limits in `ArtifactCache`.
5. Persist validator results so policy promotion is based on history, not a single round.
6. Add serving-plane reference docs or a thin reference implementation in a separate repo.

## Bottom Line

The best approach for Sluice is not a monolith. It is:

- this repo as the artifact validation control plane
- a small promotion layer as the approval boundary
- a separate serving app as the customer-facing execution plane

That gives you deterministic benchmarking, safe rollout, rapid rollback, and room to evolve live routing behavior without weakening validator trust.
