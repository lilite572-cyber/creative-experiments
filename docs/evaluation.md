# Recommendation acceptance evaluation

Executed on 2026-10-23 (Asia/Almaty). The current recommendation engine is
`rules-v1`: calculations, eligibility checks and hypothesis templates run locally.
No model was called for this evaluation.

## Reproduce

From the project root after installing dependencies:

```bash
mkdir -p artifacts/verification
.venv/bin/python scripts/evaluate_recommendations.py > artifacts/verification/recommendations.json
.venv/bin/python -m unittest discover -s tests -p test_research.py
```

The first command exits nonzero if any expected recommendation kind, reference,
calculation or required limitation check fails. The second command separately
checks CSV validation, recommendation edge cases and frozen-criteria evaluation.
All 16 research unit tests passed in the recorded execution.

Saved output: [recommendations.json](../artifacts/verification/recommendations.json).
The [execution manifest](../artifacts/verification/recommendations_manifest.json)
records the runtime and SHA-256 hashes of the code, fixture and generated report.

## Data and labels

[fixtures/evaluation.json](../fixtures/evaluation.json) contains 12 **authored
synthetic software acceptance cases**. Expected labels are test specifications;
they are not independent human annotations of videos. The cases were constructed
to exercise the implemented policy, not randomly sampled from a customer workload.
They are not a held-out research set and were available during implementation.

The cases cover a compatible positive pattern, a reversed pattern, no metrics,
paid versus organic traffic, different platforms, different sources, unknown
hooks, missing retention, repeated publication records, small denominators,
equal group means and unequal measurement-window lengths.

The target label has two values:

- `observational`: describe a difference in a compatible stratum, with limitations.
- `exploratory`: propose a test without asserting that a successful pattern was found.

Even an `observational` label does not mean a causal effect was established.
The rule requires at least two videos per recognized hook category, one metric
record per video and at least 100 starts per video. These are transparent MVP
eligibility rules, not a statistical power calculation. Groups are matched on
platform, traffic type, source, units and measurement-window duration. Means give
each video equal weight; individual views are not treated as independent trials.
Multiple records for a video are excluded rather than choosing the best window.

## Baseline

The baseline compares unweighted preparation-versus-packaging hook means whenever
both groups have at least one nonmissing retention value. A nonzero difference
produces `observational`; otherwise it produces `exploratory`. It deliberately
omits provenance matching, minimum denominator checks and repeated-record controls.
It is a simple reference implementation, not an industry benchmark or a competing
LLM. Both approaches receive the same fixture inputs and expected labels.

## Observed results

| Check | Passing cases | Meaning |
| --- | ---: | --- |
| Rule-engine eligibility decision | 12 / 12 | Returned recommendation kind matches the authored expected label |
| Simple baseline eligibility decision | 5 / 12 | Baseline matches the same authored expected labels |
| Source references | 12 / 12 | At least one source exists; referenced video IDs belong to the case and time intervals lie within its duration |
| Numeric output contract | 12 / 12 | Two observational cases match expected +20 / −20 percentage-point differences; ten exploratory cases emit no invented delta |
| Limitation fields | 12 / 12 | Causal caution is present; exploratory recommendations also include the required no-pattern caveat |

The baseline fails seven deliberately adversarial cases: incompatible traffic,
platform, source or windows; missing retention reducing an eligible group below
the minimum; repeated publication records; and small denominators. These failures
show the value of the specified checks on this fixture. They do not quantify an
expected improvement on unseen customer data.

The reference check validates IDs and temporal bounds, not whether a human agrees
with the semantic relevance of each cited scene. The limitation check tests
required text presence, not a comprehensive natural-language factuality rubric.
No claim of independent expert review is made.

## What this does not establish

This evaluation does not measure audience engagement, real-world recommendation
usefulness, VLM accuracy, speech recognition, creative quality or a causal impact
on retention. It contains no observed publication experiment. Synthetic demo
statistics remain separate from user data. A live-model evaluation would need
approved calls, separately labeled video cases and a versioned protocol; a claim
about engagement would additionally require an appropriate publication study.
