# Executing the prepared Creative Experiments pilot

The existing `configs/live_pilot_v1.json`, `docs/live_pilot.md` and preparation code remain frozen. This runner adds execution without changing that protocol. It uses the approved OpenAI model `gpt-4.1-mini-2025-04-14`; there is no model fallback. Preparing and checking a packet are offline operations. The software tests use generated temporary media and fake transports, not live model responses or human research labels.

## Complete the human gates

Open the packet's `review.html` and complete `human_review.csv` before inference. Keep its source IDs, frame indices and timestamps. Give each row a reviewer and either a supported description or uncertainty explanation. A blank hook category is permitted with an explanation in `notes`; `unknown` is also permitted. Neither is scored as a definite hook label. The hook comparison uses the earliest sampled frame's human label, not all eight labels as independent opening examples.

Complete `source_confirmation.json`: name the reviewer and confirm that each source's rights reference has been reviewed and API analysis is lawful. Do not claim independent recordings merely because files have different names. `independent_original_recording_confirmed` may remain `null` or be `false` with an explanation in `notes`; the report then labels the entire packet as an integration pilot with independence unestablished. These are human declarations, not automatically verified legal clearance.

The runner checks these declarations, frame/source/request hashes, measured metadata, configuration, frozen code and protocol. It reconstructs requests and operation plans before sending anything. It does not fill either human file.

```sh
.venv/bin/python scripts/run_live_pilot.py /absolute/path/to/prepared-packet --check-only
```

This prints JSON: exit 0 means ready, exit 2 means blocked. Check-only does not read a key or ledger and does not call a network service. It does not claim that the provider is available or that a previous execution can resume.

## Run with the already authorized budget

For the combined BriefGuard + Creative Experiments run, use [the combined launcher](run_both_pilots_ru.md), which checks both packets before any inference. To execute CE separately from the repository root:

```sh
.venv/bin/python scripts/run_live_pilot.py /absolute/path/to/prepared-packet --key-file data/private/openai_api_key
```

Alternatively omit `--key-file` and provide `OPENAI_API_KEY` through your local environment. The key is never printed. Explicit key files must be owned regular files with permissions 0600 and cannot be symlinks. Do not paste keys into chat. This CLI loads the key explicitly; the preparation script does not.

Each source gets two visual analyses over the eight prepared frames. Up to three source groups each receive two hypothesis wording calls using the corresponding real analysis repetition and the existing rule baseline. No publication statistics are supplied or invented, so all these hypotheses remain exploratory. The baseline candidates are retained in each request, and the final recommendations retain their source references and programmatic fields. No video generation, speech transcription, engagement testing or editing API is called.

## Durable cost controls and recovery

The canonical, private directory `data/private/ce-live-pilot-ledger/` is shared across every invocation and packet for this authorized CE budget. There is no CLI switch to choose a new ledger or reset spending. An exclusive process lock prevents concurrent calls. Before each call, an atomic, fsynced ledger entry reserves $0.10. Fifty attempts reserve at most $5, inside the combined $8 authorization. At most forty analysis and six hypothesis attempts are scheduled; four diagnostic/recovery slots remain unspent because automatic retries and automatic recovery are not implemented.

The frozen planning estimate is $0.00992 per attempt ($0.496 for fifty), using 20,000 input tokens and 1,200 output tokens. This is a planning estimate, not a provider bill. The runner pins 1,200 output tokens and bounds input text and image size before calling; API usage is checked after each response. A missing cost, usage above the planning allowance, or cost above a reservation halts execution. Reservations are never refunded automatically.

Successful attempts are reused on resume; they are not sent again. A timeout, interrupted pending operation, invalid response, unknown usage or over-reservation response blocks automatic continuation. A timeout may already have incurred a charge. Inspect the private evidence and provider billing before designing an explicit recovery; do not delete or edit the ledger to retry. This local ledger cannot protect against a person deliberately deleting all project state or spending through another application.

Changing the packet, human labels, source declarations, runner or rule baseline after execution starts prevents resume. This preserves the exact evaluated inputs. Request and response artifacts, audit metadata and results are saved as mode-0600 JSON, with the actual key string redacted. They can contain source images and descriptions, so keep this ignored directory private.

## What the saved report can establish

`summary.json` in the ledger directory records reservations, usage-derived cost, source count and independence status. Its offline evaluation includes:

- Hook-label matches against definite human labels from the earliest frame, alongside the trivial “always other” baseline. This baseline was fixed before any live inference; it was not selected using live outcomes. Both calls are listed per source; repetitions are not independent samples. Blank/unknown labels and denominators are explicit.
- Valid supplied frame references and timestamps, plus valid hypothesis video/time references. A valid reference does not prove that a description is factually supported.
- Agreement between repeated classifications for the same source. Consistency is not accuracy.

Unsupported descriptions, usefulness of a hypothesis and specificity of the suggested edit still require human review. No model grader is represented as a human. This pilot supplies no publication results and cannot establish engagement growth or causal effects. Related recordings or a small packet cannot support broad accuracy claims.

`check_packet(Path)` is a read-only preflight API; `run(Path, key_file=None, transport=None)` runs the same gates and execution path. The `transport` argument exists for offline tests. No inference calls were needed to implement or test the runner.
