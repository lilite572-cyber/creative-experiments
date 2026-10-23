# Gemini open-media integration v1

Prospective protocol, 23 October 2026. Separate from the unsuccessful OpenAI
checks. Neither the frozen source packet nor either OpenAI attempt is modified.
This is a technical integration pilot, not a confirmatory research experiment.

## Data and independence

Reuse the existing licensed Kelliks source, `Coffee Bean & Tea Leaf Process`,
CC BY-SA 3.0, and its frozen eight JPEG frames from the silent 24 fps conversion.
Source: https://commons.wikimedia.org/wiki/File:Coffee_Bean_%26_Tea_Leaf_Process.webm
License: https://creativecommons.org/licenses/by-sa/3.0/
The independent unit is one recording, not eight frames. No train/test split,
human reference labels, publication metrics, audio interpretation or inference
of video-wide continuity. Prior owner labels belong to other sources.

## Method and budget

Model: `gemini-3.5-flash-lite`, native generateContent, structured JSON,
one candidate, minimal thinking, 4096 maximum output tokens per operation.
At most two inference requests: visual analysis, then hypothesis wording over
programmatically computed exploratory candidates. No retries, paid fallback,
model fallback, external tools, grounding, generation or transcription.
Store the actual returned modelVersion: the stable model name is not a guarantee
of immutable weights. The model and prompt differ from OpenAI; this is not a
controlled comparison between providers.

Additional authorized spending: **$0**, conditional on the owner confirming that
the key's Google project is **Free tier**, without active paid billing. A key alone
does not establish billing tier. The API response does not certify it either.
The runner refuses execution without a private authorization bound to the key.
It cannot prevent charges if that attestation is false or billing is later enabled.
Do not enable paid billing. A quota rejection ends the run; do not delete its ledger.
Google may use free-tier inputs and outputs to improve its products. Only this
openly licensed source is sent, never the original private review packet.

Official documentation checked on 23 October 2026:
- https://ai.google.dev/gemini-api/docs/pricing
- https://ai.google.dev/gemini-api/docs/billing
- https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite
- https://ai.google.dev/api/generate-content

## Evaluation and evidence

Require schema-valid analysis with references to supplied frame indices, then
schema-valid wording with known unique candidate IDs. Sources, counts, metric
definitions and evaluation criteria are inherited from the simple deterministic
baseline, not invented by the model. Compare the baseline's protected fields to
the returned recommendations programmatically. Report counts, not significance.
Valid references do not establish correct visual descriptions or useful advice.
Prose validation cannot prove absence of unsupported semantic claims.

Stop on HTTP errors, transport failure, truncation, malformed JSON, absent model
version, unknown references or missing/excessive usage. Persist each pending
attempt before its request; preserve an interrupted run and block replay. Capture
request, response, validated result, diagnostics, actual model version, token
usage and duration privately. The public report contains aggregate checks and
source attribution, not video, images, keys or generated descriptions. Billed cost
stays null; expected Free-tier cost is zero, not a fabricated billing receipt.

`data/private/gemini-open-media-v1/plan.json` binds runtime, source freeze and
prior OpenAI ledger hashes before execution. Credentials are entered with hidden
Terminal input and stored in ignored `data/private/gemini_api_key` with mode 0600.
No API key is written to source, shell history, Git or reports.

## Run

From the repository root, using the installed environment:

```sh
.venv/bin/python scripts/run_gemini_check.py --prepare
.venv/bin/python scripts/run_gemini_check.py --check-only
.venv/bin/python scripts/run_gemini_check.py --start
```

Preparation is one-shot; skip `--prepare` if the plan already exists. `--start`
asks for Free-tier confirmation and the hidden key if not configured, then runs
the two bounded operations. `--configure` saves configuration without inference;
`--execute` requires prior configuration. Never replay a started run. The live
result appears in `artifacts/verification/gemini_open_media.json` when produced.
This adapter is currently available through this research runner, not the web UI.
