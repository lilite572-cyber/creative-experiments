# Creative Experiments — exploratory live pilot v1

Protocol prepared on 2026-10-23 before this pilot's model responses. This is a
bounded integration and interpretation pilot, not a confirmatory test of video
engagement or causal creative effectiveness. The existing synthetic acceptance
suite remains separate. No model response, human label or publication statistic
is fabricated by preparation.

## Scope and independent units

Use up to 20 short, lawful, naturally recorded MP4 sources. A source is an
independent original recording, not a crop, edit, codec conversion, repost or
frame. Select the sources before viewing pilot model outputs. Seek varied hooks,
product visibility, readable/unreadable text and CTAs, including ambiguous cases;
record the inclusion decision in the provenance note. This is a convenience
sample, not a representative advertising benchmark.

Each source is at most 100 MiB, 120 seconds, 1920×1080 or 1080×1920, 1–60 fps,
with no display-rotation metadata. Total originals must fit 500 MiB. The existing
bounded FFmpeg loader validates the files. Eight uniformly spaced frames,
including the beginning, are extracted as JPEGs with longest side at most 512 px.
The existing `app.provider.prepare_request` builds the exact unsent structured
Responses request at low image detail. Speech transcription and generation are
excluded from this budget and protocol. Audio in the source can be reviewed by
the person but is not evidence supplied to this visual-only model call.

Two fresh analysis observations per source allow inspection of repeatability;
there are at most 40 analysis attempts. Repeats share a source and **must not be
counted as independent videos**. No confidence interval treating 40 responses as
40 independent recordings is appropriate. Report source counts and repeat counts
separately; retain failed or indeterminate calls in operational denominators.

## Source manifest and rights

Create UTF-8 CSV with these exact columns, in order:

```csv
source_id,path,source_url,credit,rights_url,rights_note,distribution_allowed
```

- `source_id`: unique recording ID, letters/digits/underscore/hyphen, at most 64 characters.
- `path`: relative MP4 path under the supplied media root. Absolute paths, `..`,
  escaping symlinks, repeated paths and identical file bytes are rejected.
- `source_url`: stable HTTPS origin page, without credentials, query or fragment.
  For owned footage, a real accessible project/source page can document ownership;
  do not invent a source URL to pass validation.
- `credit`: actual creator and attribution required by the source.
- `rights_url`: stable HTTPS license or ownership/permission reference.
- `rights_note`: applicable permission, why analysis is permitted, any attribution
  or redistribution conditions, and whether this is an independent recording.
- `distribution_allowed`: exactly `true` or `false`; this is a recorded declaration,
  not a license granted by the tool. False does not prevent private preparation.

The tool validates completeness and file identity. It cannot verify legal rights,
consent, the truth of ownership claims or recording independence. The reviewer
must inspect the source/license pages and confirm lawful API analysis explicitly
in `source_confirmation.json` before any later runner may send images.
Do not include private, confidential or otherwise unauthorized footage. No upload
is performed by the preparation script. Keep the packet private; do not publish
originals or frames merely because they were technically accepted. Even `true`
requires retaining attribution and checking the original license conditions.

## Preparation and immutable evidence

After installing the project's pinned requirements:

```bash
.venv/bin/python scripts/prepare_live_pilot.py \
  --manifest /absolute/path/to/sources.csv \
  --media-root /absolute/path/to/owned-or-licensed-mp4 \
  --out /absolute/path/to/private-ce-live-pilot-v1
```

The output must not already exist. The script validates the whole manifest, stages
all processing, and publishes a new packet only when preparation succeeds. Failed
processing does not leave a half-complete packet at the requested output path.
The packet contains copied source MP4s, eight JPEGs per source, exact unsent request
JSON, request audit records, model/prompt identifiers and SHA-256 hashes of source
bytes, frames, request, config, protocol and relevant source code in `freeze.json`.
File hashes catch identical inputs, not semantically duplicated recordings.

Open `review.html` locally to inspect full videos and timestamped sampled frames.
It contains no model answers. Fill `human_review.csv` with actual personal
judgments before looking at the model responses. Source and frame identifiers are
prefilled; all human-label, reviewer and notes fields are initially blank. Enter
hook categories (`preparation`, `packaging`, `other`, `unknown`), relevant kinds
(`hook`, `scene`, `product`, `text`, `cta`), legible visible text and a short
supported description. Do not infer unobserved actions or speech from stills.
Leave uncertain labels blank and explain in notes. Record reviewer identity and
provenance confirmations. This is practical blinding of predictions, not an
independent expert annotation process. Preserve the completed labels' hash before
inference; do not overwrite labels after seeing model answers.

## Hypothesis requests and outcome evaluation

At most six hypothesis requests are reserved. Once source selection is frozen,
partition source IDs lexicographically into three groups by position modulo three,
then make two repeated hypothesis observations per nonempty group. If fewer than
three recordings are supplied, skip empty groups and leave unused budget unused.
These hypotheses use only the corresponding observed videos, reviewable source
references and programmatically computed candidate fields. They do not introduce
publication statistics: without genuine compatible publication metrics, every
recommendation remains exploratory and must state that no successful pattern has
been established. Preparing the packet reserves these slots without fabricating
model outcomes or claiming the hypothesis calls have run.

For visual analysis, report operational completion, valid-schema rate, valid cited
frame rate, hook agreement on human-labeled cases, unsupported-description count
and visible-text agreement where human text is legible. Keep blank/uncertain human
labels outside agreement denominators and report their count. Assess observations
only against the supplied evidence frame; timestamp references are not claims
about exact scene-change boundaries. For each source, describe differences between
the two repeats rather than treating repetition as additional independent evidence.

For hypotheses, compare model wording to the existing local `rules-v1` candidate
for the same input. Separately review source identity/time bounds, correctness of
attached numeric calculations, missing-data caveats, preservation requirements
and whether the proposed edit is actionable. Human usefulness judgments require
real reviewer entries. Do not convert these checks into a fabricated probability
of success. Existing authored synthetic acceptance cases remain software tests,
not a replacement for this live evaluation.

## Budget and execution boundary

Pinned provider/model: **OpenAI Responses API / `gpt-4.1-mini-2025-04-14`**. The
snapshot is deprecated; availability must be checked without silently changing
the model. A migration requires a separate versioned protocol and reviewed budget.
No automatic retries: timeout/unknown outcome consumes an attempt and reservation.
Manual diagnostic/recovery attempts count toward the same durable ledger.

| Allocation | Maximum attempts | Reservation |
| --- | ---: | ---: |
| Visual analyses, two per source | 40 | $4.00 |
| Hypothesis wording | 6 | $0.60 |
| Diagnostics/recovery, including uncertain outcomes | 4 | $0.40 |
| Creative Experiments total | **50** | **$5.00** |

The planning allowance is 20,000 input tokens and 1,200 output tokens per attempt.
At $0.40/M input and $1.60/M output, that is **$0.00992 per attempt**, at most
**$0.496** for 50 attempts. The conservative reservation is $0.10 per attempt.
These are estimates and local spending controls, not guaranteed provider invoice
caps. Actual returned usage and unknown charges must be recorded; stop for review
if usage exceeds its reservation or cannot be reconciled safely.

BriefGuard has a separate $0.50 allowance. The reserved combined allocation is
therefore **$5.50**, below the user's **$8 total authorization**. The remaining
$2.50 is unallocated contingency, not permission to reset a ledger or expand the
number of requests. Billing from unrelated applications is outside this project's
ledger. Never copy API keys into manifests, files, arguments or chat.

The preparation CLI has **no paid execution path** and does not read an API key.
It imports only local request preparation, not the paid analysis entry point.
The later execution path must require the verified packet, completed human review,
confirmed source rights, `OPENAI_API_KEY` in the process environment, the pinned
model and one persistent ledger covering all attempts. Preserve raw structured
responses safely, returned model, prompt, request and response IDs, durations,
usage/cost when available, and failures. Never automatically replay an unknown
outcome after interruption.

## Current status

The offline preparation implementation and tests use deliberately synthetic local
fixture video. They do not constitute the real-video source dataset. At protocol
creation, no real-source manifest, completed human labels or API credential is
available to this task. There are **zero live calls** and no model-quality or
engagement result. The script rejects an empty manifest instead of substituting
synthetic sources and presenting them as natural footage.

## Configure the key locally, without sending it in chat

In your own interactive Terminal, from this project directory:

```bash
.venv/bin/python scripts/configure_openai.py
```

Paste the key into the hidden Terminal prompt. The command refuses piped/non-TTY
input and any `getpass` fallback that would echo the key. It makes no network
request and writes only `data/private/openai_api_key` inside the already ignored
`data/` directory. The key file uses mode `0600`, its private directory `0700`;
symlink destinations/components are refused. An existing key remains intact
unless you explicitly run the command with `--replace`.

Saving the file does **not** load it into an application or runner, does not
verify account access, and does not authorize a different model or budget. The
existing application reads `OPENAI_API_KEY` from its process environment. To load
the saved key explicitly in your own trusted Terminal before starting an approved
runner or server:

```bash
export OPENAI_API_KEY="$(cat data/private/openai_api_key)"
```

This command prints no key. Do not enable shell tracing (`set -x`), print the
environment, copy the file into a submission, or include it in an archive. The
server/runner still needs its separate configured spending gate; merely setting
the variable does not start a request. Use `unset OPENAI_API_KEY` when finished.
