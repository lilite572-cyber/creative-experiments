# Key-input compatibility correction, 23 October 2026

The first owner setup was blocked locally with `Invalid-form key; nothing saved`.
No Gemini inference occurred, no key or authorization was saved, and no run ledger
was created. The runner in commit `1c3fb03` only accepted an `AIza` prefix and
short keys. This was an implementation defect, not a provider rejection.

Google now issues authorization API keys by default, including `AQ.` keys.
The official key guide confirms the transition and the `x-goog-api-key` header:
https://ai.google.dev/gemini-api/docs/api-key

Revision `key-format-v2` accepts bounded ASCII credential characters without
requiring the legacy prefix, up to 4096 characters. It still refuses empty,
whitespace-containing, quoted, non-ASCII and oversized input, checks private-file
ownership and mode 0600, and never prints credentials. Syntactic acceptance is
not authentication: only Google can validate a key.

The original `plan.json` is retained byte-for-byte. Before any live request the
corrected runtime is frozen in `plan-key-format-v2.json`, with a reference to the
original plan hash. The original runtime remains in Git commit `1c3fb03`.
Preparing a revision cannot bypass an existing run. The source packet, model,
prompts, metrics, Free-tier confirmation, $0 spending authorization, two-request
limit and all OpenAI evidence remain unchanged. There are no new research results.

Use the same `--start` command after the corrected plan has been prepared. No new
key is required solely because the old local validator rejected its format.
