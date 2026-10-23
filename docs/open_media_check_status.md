# Integration-check readiness, 23 October 2026

## Separate Gemini continuation prepared

The owner obtained a Gemini key. The new [Gemini protocol](gemini_open_media_v1.md)
uses the existing licensed source and a separate ledger. It requires an explicit
Free-tier confirmation tied to the key, permits two requests and no automatic
retry, and authorizes no new spending. Ten new Gemini tests and fifteen existing
open-media/recovery tests passed with fake transports. No Gemini inference or
live compatibility is claimed at preparation. Existing OpenAI ledgers, runtime
freezes and results remain unchanged.

Subsequent account screenshots showed the $50 OpenAI grant was redeemed on
23 September and later marked Inactive; usage for 23 September–23 October
displayed $0.01. This does not explain the reason for deactivation, but does not
support attributing $50 of API spending to these experiments. The older account
inspection statement below describes the earlier stage of the investigation.

## Current blocker: provider credit balance

The owner executed diagnostic recovery. OpenAI returned HTTP 429 with
`type=insufficient_quota`, `code=credit_balance_exhausted`. Its message states
that no credits remain and points to the organization billing page. This is a
quota rejection, not evidence of a model-quality failure. It does not establish
that the API key is invalid or that the video was analyzed.

There are now two recorded attempts: the original unknown outcome and this
explicit HTTP rejection. No valid analysis or hypothesis was obtained. The
canonical ledger retains $0.20 in reservations; this is not a measured API charge.
Actual total spending remains unknown because the first attempt was not reconciled.
Do not attribute the exhaustion of an advertised $50 credit grant to these calls.
The account's activation, balance and credit history have not been inspected.

The saved report is `artifacts/verification/open_media_recovery.json`. Its public
and private copies match; both attempt artifact hashes were verified. No new
inference was sent during this inspection. The original runtime and preparation
freezes remain unchanged. No code change or additional test run was needed to
record this provider response.

The owner must check the balance and credit history for the account/organization
associated with the configured key at
<https://platform.openai.com/settings/organization/billing/>. Do not post the key
in chat. Both existing one-shot execution commands have now been used and must
not be rerun or their ledgers deleted. A future execution requires a separately
recorded recovery after the billing blocker is resolved, preserving all attempts.

The sections below describe earlier states and are retained as history.

## Latest outcome: owner execution halted

The owner subsequently executed the command. The first analysis attempt halted
after 6,998 ms with `ProviderError`, without a parsed response. One attempt and a
$0.10 reservation are recorded; actual charge and tokens are unknown. No
hypothesis call occurred. The original logger discarded the precise error detail,
so HTTP rejection, connection failure and parsing failure cannot be distinguished.
This is not evidence of poor model accuracy or an invalid key.

The completed failed-run artifact is
`artifacts/verification/open_media_integration.json`. The earlier readiness report
below describes the state before the owner's attempt. **Do not rerun its original
execution command.**

A separate [explicit diagnostic recovery](open_media_recovery_v1.md) is prepared,
not executed. It preserves the original attempt and reservation and permits at
most two new calls. Total reservation can reach $0.30 within the existing CE $5
allocation. It records safe provider diagnostics, refuses replay, and does not
claim the old unknown charge has been reconciled. Fifteen focused tests passed
(seven original-check tests and eight recovery/transport tests).

The next owner-Terminal command is:

```sh
/Users/admin/Documents/Codex/2026-10-22/new-chat-20/creative-experiments/.venv/bin/python /Users/admin/Documents/Codex/2026-10-22/new-chat-20/creative-experiments/scripts/recover_open_media_check.py --execute
```

## Historical preparation state

The separate [open-media protocol](open_media_integration_v1.md) is implemented
in commit `2faac2c`. Its one licensed source was downloaded, checked against the
Commons original SHA-1, converted, and sampled into eight frames. All input and
runtime hashes were frozen before attempting provider access.

The model metadata check from the agent environment failed. **Zero inference
requests were sent, zero dollars were reserved, and no live result exists.**
This does not establish that the locally configured key is invalid. The original
Mixkit packet remains unexecuted; its frozen runtime and Amir's 24 descriptions
are unchanged. Those descriptions are not labels for the replacement source.

Validation completed: 20 original-runner tests, six coordinator tests and seven
new-runner tests passed. These used fake API transports. A changed-frame check
on a temporary copy was correctly rejected before inference. This is 33 focused
tests, not a claim that the complete application suite was rerun.

The remaining execution command, from the owner's Terminal, is:

```sh
/Users/admin/Documents/Codex/2026-10-22/new-chat-20/creative-experiments/.venv/bin/python /Users/admin/Documents/Codex/2026-10-22/new-chat-20/creative-experiments/scripts/run_open_media_check.py --execute
```

Do not rerun `--prepare`: the packet already exists. No further human annotation
is required for this technical check. It attempts at most two calls, reserves at
most $0.20 within the existing CE $5 allocation and stops on failure. Its planning
estimate is $0.01984; the saved report will give actual returned usage if available.
Do not delete the shared ledger or automatically repeat an interrupted request.

The command writes private requests and responses under
`data/private/ce-live-pilot-ledger/`, and a media-free aggregate report to
`artifacts/verification/open_media_integration.json`. Do not publish the private
directory. Source and license provenance remain necessary to interpret and
reproduce the reported check; they do not imply company endorsement.

This repository currently has no Git remote. The implementation is committed
locally; no Creative Experiments files or results have been pushed by this step.
