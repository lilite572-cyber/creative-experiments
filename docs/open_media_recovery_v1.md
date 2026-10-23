# Explicit diagnostic recovery v1

The original open-media check attempted one visual request and halted after
6,998 ms with `ProviderError`. It saved the request but no parsed response.
Its logger discarded the exception detail. The cause could be an HTTP rejection,
transport failure or response parsing failure; the evidence cannot distinguish
them. `schema_accepted=0` does not establish that the model produced invalid
structured output. The owner's abbreviated `--execut` was accepted by argparse;
it is not the cause of this failure.

Preserve the original frozen runtime, protocol, human labels, attempt, summary and
unknown outcome. The failed packet's ledger SHA-256 is
`b2e69607c5882f6305c46b0e14617f6fbed6a48187d6f1f8949514b7820d16b3`.
The original $0.10 reservation is not evidence of an actual charge or a refund.

This separate manual recovery prospectively amends the one-shot execution plan.
It permits at most one new visual attempt, then one hypothesis attempt only if
the analysis and usage validation succeed. It uses identical source frames,
model, prompts and response validators. No inference is made during preparation.
The original uncertainty is not resolved: retain its full $0.10 reservation and
append at most $0.20 to the same canonical ledger. Total reservation is at most
$0.30, within the existing CE $5 allocation and combined $8 budget. No additional
budget is requested. A local reservation is not a provider billing receipt.

Only an explicit owner invocation of the recovery command starts new paid calls.
There are no automatic retries. Refuse any ledger except the exact reviewed
one-attempt failure state. Preserve a byte-exact ledger snapshot before appending.
After starting, refuse every subsequent invocation, including interrupted runs.
The original entry remains unknown, and the global halted flag remains set;
this narrow recovery does not authorize general resumption. The failed request
may have been processed by the provider; this is a new paid attempt, not retrieval
of its lost response. Billing reconciliation remains outstanding.

The diagnostic transport saves HTTP status, bounded/redacted provider error
fields and transport exception type before raising. It does not save request
headers or keys. The private attempt retains available raw structured response
and usage even if downstream validation fails. Report the old unknown attempt and
new attempts separately; do not present known new usage as total spending.

Technical success only establishes operational completion and mechanically valid
references. The source has no human reference labels or publication metrics.
No model-quality, causal, engagement or superiority claim is warranted.

```sh
.venv/bin/python scripts/recover_open_media_check.py --prepare
.venv/bin/python scripts/recover_open_media_check.py --execute
```

Preparation is already performed for the owner packet. Run only `--execute` once
from the owner's Terminal. Original media, requests and diagnostics remain private;
the public report is `artifacts/verification/open_media_recovery.json`.
