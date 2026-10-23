# Open-media integration check v1

Prospective protocol, 2026-10-23. This is a separate technical check, not a
replacement for the Mixkit pilot or its human annotations. That packet remains
unchanged and unexecuted. No human labels are required or claimed for this check.

Use one convenience source: **Coffee Bean & Tea Leaf Process**, Kelliks, own work,
11 April 2013, [source](https://commons.wikimedia.org/wiki/File:Coffee_Bean_%26_Tea_Leaf_Process.webm),
[CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/).
The original WebM is 7,032,288 bytes; its Commons SHA-1 is
`0a3ca2cf4b1aba86546834edb86db225e44558f6`. Preserve original bytes and attribution
privately. Convert to silent H.264 MP4 at 24 fps for the existing loader; extract
eight uniform frames at at most 512 px. The API receives only those JPEG frames.
Do not identify people or infer personal attributes. No brand endorsement is implied.

The license permits reproduction and adaptation subject to its conditions; this
check records the assistant's source/license assessment, not a human attestation.
Keep media and request payloads private. If media derivatives are later shared,
retain credit, license and modification notices and meet ShareAlike requirements.
The public report contains aggregate operational results and source attribution,
not video, frame data, keys or provider response IDs.

Freeze source/frame/request hashes, measured metadata, runtime and this protocol
before inference. Run exactly one visual analysis followed by at most one
hypothesis-wording request using the existing programmatic `rules-v1` candidates.
Pin OpenAI `gpt-4.1-mini-2025-04-14`, low image detail, 1,200 output tokens,
`store=false`. No transcription, video generation, training or fine-tuning.

Reserve $0.10 before each attempt: $0.20 maximum from the existing CE $5 allocation,
not extra budget. Planning estimate: at most $0.01984 for two calls at 20,000 input
and 1,200 output tokens each using the existing frozen planning rates. Actual
usage-based cost is an estimate, not a billing receipt. Use the same canonical
CE ledger directory and exclusive lock. Refuse if any earlier ledger exists;
never reset it, retry automatically or replay a possibly charged request. This
deliberately one-shot check does not support automatic resume. A later protocol
must reconcile this ledger before spending any remaining CE allocation.

Report attempted/completed operations, schema acceptance, citations that refer to
supplied frames, hypothesis source/time bounds, retained programmatic fields,
latency and returned token usage. Keep failed calls in the denominator. Compare
the model wording with the saved rule candidates, without claiming the model is
more useful. One original source and two different operations are not independent
replicates. No human agreement, factual accuracy, repeatability, engagement gain,
successful creative pattern or causal effect can be estimated here. Absence of
publication metrics must remain explicit. Missing or excessive usage stops calls.

Commands, from the project root:

```sh
.venv/bin/python scripts/run_open_media_check.py --prepare
.venv/bin/python scripts/run_open_media_check.py --execute
```

Preparation downloads only the fixed licensed source and makes no API requests.
Execution first performs a model metadata availability check (no inference).
Private evidence: `data/private/open-media-integration-v1/`; budget/evidence:
`data/private/ce-live-pilot-ledger/`. A public aggregate report is written to
`artifacts/verification/open_media_integration.json` after the run.
