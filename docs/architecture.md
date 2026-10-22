# Architecture

The unit of work is one brand workspace. A signed-in owner can access only its
workspaces and their videos, metrics, experiments and operations. Synthetic demo
records live in a dedicated workspace; ordinary uploads require a separate one.

## Components

| Component | Responsibility |
| --- | --- |
| `web/` | Four screens, video playback, evidence seeking, forms and operation polling. Plain JavaScript, HTML and CSS; no CDN or build step. |
| `app/main.py` | FastAPI HTTP boundary, sessions, ownership checks, transitions and durable operation records. |
| `app/db.py` | SQLite transactions and JSON records; local media remains outside the public static directory. |
| `app/media.py` | Bounded FFmpeg probing, frame extraction, segment replacement and preservation checks. |
| `app/research.py` | CSV validation, programmatic group statistics, source-backed rule candidates, fixed-criterion evaluation and generation briefs. |
| `app/provider.py` | Opt-in OpenAI visual interpretation, hypothesis wording and optional speech transcription. |
| `app/demo.py` | Deterministic authored synthetic videos, metadata and publication examples. |

Python keeps media processing, validation and statistics in one runtime. SQLite
fits a local single-process product and avoids service dependencies. Vanilla
JavaScript keeps this small interface directly runnable; TypeScript would add a
build pipeline without changing the present domain boundaries. A larger UI can
adopt it without moving calculations into the browser.

## Saved workflow

Analysis and editing create an operation before work starts:
`pending → running → completed | failed`. A thread pool runs two jobs, with at
most one active operation per workspace. On startup, unfinished records become
`interrupted`; they are not silently resubmitted. The queue is local, so run one
worker. Do not interpret a missing response as a completed action.

Experiment transitions are `draft → ready → awaiting → completed`. A real edited
variant is required before `ready`. Entering `awaiting` snapshots the hypothesis
and numerical criterion. Later edits increment the revision and remain visible
in history; evaluation uses the snapshot. Existing variant metrics at freeze
are recorded as a retrospective condition. Completion requires evaluation and
includes `insufficient_data` as a valid result. Re-evaluation preserves earlier
outcomes in the history.

The experiment stores a snapshot of its recommendation, including sources and
statistics. New uploads, analysis or metrics invalidate cached model wording;
they do not rewrite the experiment's original observation.

## Evidence and calculations

The server computes all counts, means and differences. Comparable recommendation
groups share platform, traffic type, metric source and measurement-window
length. They need at least two eligible videos per recognized opening category.
Videos with multiple publication/window records are excluded rather than
choosing the best result. Means weight videos equally, not viewers.

Evaluation requires exactly one compatible publication/window for each version,
the saved observation-window length, sufficient video starts and present
retention values. It reports an observed criterion outcome, not significance or
causality. Source dates are measurement dates; audience overlap and time since
publication are unavailable.

## Video transformation

FFmpeg is invoked with argument arrays, fixed filters, timeouts and a local
protocol whitelist. User strings never become shell commands. The editor creates
a normalized 24 fps yuv420p master, replaces the specified visual frames and
copies the source soundtrack. It rejects insufficient replacement footage and
non-frame-aligned boundaries.

Every decoded frame outside the interval is SHA-256 compared against the
normalized master, and the frame count must match before publishing the output.
This verifies preservation after normalization; it does not preserve the original
compressed bytes or promise an identical original encoding. The report retains
source, replacement and output hashes and the normalization details.
The export explicitly uses constant 24 fps. An additional check reads encoded
packet timestamps and durations using rational arithmetic: packet `i` must start
at `i/24`, and every packet must last `1/24` second. Pixel equality alone would
not catch a truncated final packet duration.

## Optional model boundary

Visual analysis uses `gpt-4.1-mini-2025-04-14` with strict structured output and
up to eight supplied images. Evidence must cite an actual sampled frame;
interpretations are not continuous video observations. Visible text is model
interpretation, not a guaranteed OCR transcript. Speech is not inferred from
images. The optional `whisper-1` path uses extracted audio and validates segment
timestamps; its failure can leave a partial visual result.

Hypothesis wording receives only computed candidates. It must return existing
candidate IDs. Source references, numerical statistics and criteria are inherited
unchanged; generated prose containing numerical characters is rejected. This
constrains arithmetic fabrication but does not prove semantic correctness.

Operation records include model, prompt version, input evidence references,
validated output, duration, usage and cost when available. Keys remain in the
server environment. Unknown provider outcomes consume their reservation and halt
further paid work. The guard cannot guarantee the external invoice, and it does
not cover unrelated applications using the same API account.

## Current deployment boundary

Authentication protects local application routes; this is not a hosted SaaS
security claim. HTTP cookies are configured for loopback development. Public
hosting needs TLS, secure-cookie configuration, request-rate and storage quotas,
shared durable jobs, backups and an additional security review. No external
publishing, ad buying, MCP server, retrieval system or generative-video adapter
is included.
