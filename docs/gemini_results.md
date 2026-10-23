# Gemini integration outcome, 23 October 2026

The owner executed two real requests to `gemini-3.5-flash-lite` using the
configured Free-tier project. Both returned HTTP 200. One licensed recording
was represented by eight still frames. This establishes live transport and
structured visual analysis on this input, not general model quality.

## Original prospective run

- Analysis: accepted, 3,447 ms, 12 observations with 12 valid frame references.
- Hypothesis wording: rejected locally after HTTP 200, 1,391 ms.
- Final run status: `halted`; one of two outputs accepted under the frozen rules.
- The model copied `Video after second 2` from the precomputed preservation
  requirements. The validator prohibited every digit in generated text, including
  this verbatim requirement. This was not an invented numeric engagement claim.
- Raw provider usage across both responses: 9,538 input tokens, 703 output tokens,
  10,241 total. The original summary omitted usage for the rejected operation;
  the offline report recovers it from the preserved raw response.
- Expected Free-tier charge: $0 based on the owner's tier confirmation. No
  billing receipt was returned; actual billed charge remains null. `serviceTier:
  standard` describes serving class and is not proof of a paid billing account.

Original report: [gemini_open_media.json](../artifacts/verification/gemini_open_media.json).
Its hashes, private/public agreement, response hashes, runtime, plan and unchanged
OpenAI ledger were checked after execution.

## Explicit post-hoc offline correction

`scripts/review_gemini_run.py` reads and verifies the saved evidence without a key
or network calls. Its revised validation permits digits only in preservation
requirements that exactly equal the computed baseline. It still rejects numeric
claims in generated prose, unknown candidate IDs and altered preservation rules.
The original run, prompts, responses, validator and report remain untouched.

The saved hypothesis passes this revised contract: one valid source reference;
all protected programmatic fields preserved. Four focused tests passed, including
rejection of invented numeric claims and changed preservation text. This is a
correction designed after observing a failure, not a fresh prospective success.

Offline report: [gemini_offline_review.json](../artifacts/verification/gemini_offline_review.json).
Run again offline with `.venv/bin/python scripts/review_gemini_run.py` while the
private evidence is available. Public aggregate reports contain no footage or key;
complete output replay requires the private request/response artifacts.

## Remaining quality concerns

Valid references are not factual accuracy. The model labeled the scene at
19.04 seconds as `hook` despite the task asking about the opening, and labeled
license credits as `cta`. The offline report flags these as semantic consistency
concerns, not human reference labels. No human accuracy score is available for
this source. A single recording and one request per operation cannot establish
repeatability, generalization, superiority over another model, engagement lift,
or a successful creative pattern. The recommendation remains exploratory.

This Gemini path is a research runner, not yet a selectable provider in the web
application. Neither original inference command should be repeated: the ledger
deliberately blocks replay. No new API request was needed for the offline review.
