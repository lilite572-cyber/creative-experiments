# Creative Experiments

A local workspace for tracing a short-video experiment from an observation to an
edited version and a recorded outcome. Keep the source clips, publication
metrics, hypothesis, fixed evaluation rule and unsuccessful experiments together.

This is an independent portfolio product. It is not affiliated with Higgsfield.
The included coffee example and its publication statistics are **synthetic**.
No engagement improvement or real campaign outcome is claimed.

## Run locally

Requirements: Python 3.12, a supported macOS/Linux/Windows environment and a
browser. `imageio-ffmpeg` supplies the FFmpeg executable on supported wheels;
a separate system FFmpeg installation is not normally needed. Dependency
installation requires network access. Run from this project directory:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.lock
python -m app.demo
python -m uvicorn app.main:app --host 127.0.0.1 --port 8770 --workers 1
```

On Windows, activate with `.venv\Scripts\activate` instead. Open
<http://127.0.0.1:8770>. Choose the synthetic demo or sign in with
`demo@example.test` / `creative-demo`. Create a separate workspace for your own
uploads. Synthetic demo edits accept only the supplied alternative fragment
(verified by file hash); use an ordinary workspace for your own footage. Running
the demo seed again preserves existing records.

SQLite, uploads and operation records persist in `data/`. Set `CE_DATA_DIR`
before starting to use another directory. Keep that directory private and back
it up while the application is stopped. Do not commit it. Use one server process
and one worker; this MVP uses an in-process job queue.

## What works

- **Library:** brand workspaces, MP4 uploads, native video playback, documented
  CSV import, atomic validation and idempotent repeated imports.
- **Analysis:** measured video properties, timestamped evidence and an explicit
  distinction between authored demo labels, local measurements and model output.
- **Experiments:** saved hypothesis and source observation, versioned criteria,
  generation brief, real segment replacement, side-by-side playback and outcome.
- **Brand knowledge:** successful, unsuccessful and insufficient-data outcomes
  with sources, criteria, dates and limitations.

An upload may be at most 50 MiB, 120 seconds, 1–60 fps and 1920×1080 pixels
(or portrait equivalent). The supported container is MP4; upright display
metadata is required. Editing uses a 24 fps timeline, frame-aligned boundaries
and an alternative fragment long enough to cover the replacement interval.
The original soundtrack is retained; audio in the alternative fragment is ignored.

See [the five-minute demo](docs/demo.md), [CSV contract](docs/csv.md) and
[architecture](docs/architecture.md). Ready-to-upload authored clips and the
seed CSV are also included in [fixtures/demo](fixtures/demo/README.md).

## Three different kinds of analysis

| Mode | Actual behavior |
| --- | --- |
| Synthetic demo | Known labels attached to locally authored clips. No model call. |
| Local | FFmpeg measures the file and extracts timestamped frames. Hook, product, text and speech semantics remain unknown. |
| OpenAI | Prepared adapter interprets up to eight sampled frames with structured outputs and validated evidence references. Speech requires the separate optional transcription path. |

The offline recommendation engine computes compatible groups and proposes at
most three tests. It compares preparation-first and packaging-first hooks where
sufficient labeled data exist; otherwise it proposes an explicitly exploratory
test. This is a deliberately narrow first strategy, not a general creative
intelligence system. Optional model wording inherits the computed sources and
statistics; the model cannot supply numerical results or new source IDs.

A generation brief is a task specification. No generative-video provider is
connected, and uploading a fragment does not prove that it was AI-generated.
The edited video and frame-preservation report are separate artifacts.

## Optional paid integration — disabled by default

Adapter tests use fake responses. The owner's first live integration attempt
halted without a parsed response; its charge is unknown and live compatibility
is not established. The visual and hypothesis adapter pins
`gpt-4.1-mini-2025-04-14`. Check current availability and prices before
authorizing a run or changing the model/protocol.

The [separate live-pilot protocol](docs/live_pilot.md) prepares real-source review
packets and unsent requests. The [combined budget](docs/combined_api_budget_ru.md)
allocates $5 for this project and $0.50 for BriefGuard within the authorized $8.
For the prepared Mixkit packet, Amir supplied 24 frame descriptions and configured
the local key; permission for the specific AI evaluation use remains unresolved.
The packet has not been sent to the provider.
The key-setup command is `.venv/bin/python scripts/configure_openai.py`; it makes
no API call and does not enable paid mode by itself.

For the two prepared local research packets, follow the
[combined launch instructions](docs/run_both_pilots_ru.md). The launcher checks
both sets of real human labels before sending any inference request and keeps
the allocated spending ledgers across restarts.

A separate [open-media integration check](docs/open_media_integration_v1.md)
uses one CC BY-SA coffee video and does not claim human-rated accuracy. Its source,
eight frames and runtime are frozen; 33 preparation-focused tests passed. The
owner's first analysis attempt then halted with an unknown outcome and a $0.10
reservation. A separate diagnostic recovery is prepared, not executed; 15 focused
check/recovery tests passed. See the [current status and exact owner-Terminal
command](docs/open_media_check_status.md). Recovery keeps the original reservation
and can bring the total to at most $0.30 from the same CE allocation. Public
reports exclude media and raw payloads.

The [official deprecation schedule](https://developers.openai.com/api/docs/deprecations)
checked on 2026-10-22 lists this snapshot's shutdown for January 14, 2027.
Migration and a fresh live contract test are required before using it beyond
that date. The adapter's $0.40/M input and $1.60/M output cost estimate matches
the [published model rates](https://developers.openai.com/api/docs/models/gpt-4.1-mini)
at that check; cached-input discounts are not applied to this estimate.

After explicit approval of provider, model and total spend, configure
`OPENAI_API_KEY` privately in the server environment and set
`CE_OPENAI_APPROVED_BUDGET_USD` to the approved value, greater than zero and at most
10. Do not paste keys into the UI, commit them or pass them as URL parameters.
`CE_APPROVED_TRANSCRIPTION_MODEL=whisper-1` separately enables speech
transcription when the uploaded video has audio and that model is approved.

Each paid operation reserves $0.10 durably before transmission. Reservations are
shared across workspaces in the same data directory and are not refunded. This
is a local reservation guard, **not a provider billing cap**. Missing costs,
unknown outcomes and overruns halt subsequent paid operations until reviewed.
There are no automatic HTTP retries. Transcription cost is currently unknown in
the adapter, so a transcription operation triggers that review gate. Do not
reset the data directory or ledger to bypass an approved budget.

## Verify

```bash
python -m unittest discover -s tests -v
python scripts/evaluate_recommendations.py
python scripts/verify.py
```

Tests exercise media processing, ownership boundaries, CSV failure cases,
provider failures, edit verification, fixed criteria and persistence. The
recommendation evaluation uses authored synthetic cases with explicit expected
answers and compares against an unstratified mean-difference baseline. It checks
eligibility, source references, arithmetic and required limitations separately.
It is software acceptance evidence, not independent research on creative quality
or an evaluation of a live model. The [verification report](docs/verification.md)
separates automated results from the browser walkthrough. `scripts/verify.py`
saves command output and source hashes in `artifacts/verification/`.

## Boundaries

This is a loopback-only demonstration MVP, not a public multi-tenant deployment.
It has owner-scoped workspaces, hashed passwords and sessions, guarded media
routes and bounded subprocesses. It does not yet provide team invitations, TLS
termination, rate limiting, deployment-grade storage quotas, a distributed queue
or a completed formal security audit. Keep the bind address at `127.0.0.1`.

Publication results are manually supplied; there are no social-network,
ad-buying or video-generation integrations. Retention comparisons are
observational and never establish a causal effect. Averages cannot compensate
for differences in audiences, publication timing or distribution.

BriefGuard remains a separate project. Its synthetic benchmark is not used as
evidence of accuracy on these videos. MCP and RAG are not implemented here.
