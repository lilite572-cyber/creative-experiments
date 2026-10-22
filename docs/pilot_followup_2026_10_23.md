# Pilot follow-up, 23 October 2026

Amir supplied observations for all six BriefGuard pilot cases and all 24 sampled
frames across the three Creative Experiments sources. Original statements remain
in the private session logs. Descriptions and uncertainties are preserved; human
observations are not model outputs. These private records are not bundled here.
Amir declined another annotation round. Do not require a replacement human dataset
to continue engineering work, transfer these labels to different media, or invent
additional human judgments.

BriefGuard's v2 packet passed its offline readiness check after source confirmation.
Creative Experiments' Mixkit packet remains on hold: the
[Mixkit terms](https://mixkit.co/terms/) incorporate
[Envato's Acceptable Use Policy](https://help.elements.envato.com/hc/en-us/articles/31035788503321-Acceptable-Use-Policy).
Section 4.m restricts unauthorized use for developing or enhancing AI models or
ML algorithms. Permission for this particular inference/evaluation use has not
been established. This is an unresolved permission question, not a definitive
legal conclusion that every inference use is prohibited. A general free stock
license alone does not resolve it. Preserve the existing packet and labels.

A replacement-source run without new human labels must be a separate prospective
integration check. It may report API completion, schema validation, source/time
reference bounds, duration and returned token usage. It must not claim human
agreement, factual accuracy, successful creative patterns, or engagement gains.
Do not bypass the existing evaluated pilot's human/source gates. No replacement
packet or model-quality result has been produced yet.

## Run BriefGuard independently

The coordinator can select BriefGuard alone while preserving its original
protocol, labels, source gate, pinned model and USD 0.50 ledger limit. The combined
USD 8 authorization remains unchanged; this adds no allocation or retry budget.

From the Creative Experiments project directory:

```bash
.venv/bin/python scripts/run_authorized_pilots.py --project briefguard --execute
```

Without `--execute`, this selection performs only the offline readiness check.
With `--execute`, it reads the protected local key, checks the pinned model's
metadata, and invokes the existing guarded runner only if that check succeeds.
It never runs the Creative Experiments packet in this mode.

The agent's latest provider metadata check failed with a connection/metadata
error; no inference request was sent. This does not establish that the key is
invalid. Running the command from the user's own Terminal is the available next
step if that environment has network access. Do not delete ledgers or automatically
repeat a request with an unresolved outcome.

Validation for this coordinator change: six focused tests passed, including
project isolation and stopping before execution when the provider is unavailable.
