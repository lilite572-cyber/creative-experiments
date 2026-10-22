# Publication metrics CSV v1

Use UTF-8 comma-separated CSV, with this exact header and column order:

```csv
publication_id,video_id,platform,traffic,source,period_start,period_end,views,retention_3s,retention_unit
post-001,REPLACE_WITH_WORKSPACE_VIDEO_ID,instagram,organic,manual-platform-export,2026-10-01,2026-10-08,1000,0.42,fraction
```

Download a workspace template after uploading a video to obtain a valid ID.
The experiment template includes both version IDs. In a normal workspace its
metric fields are blank. **In the synthetic demo it contains authored example
numbers**, solely to exercise import and evaluation.

| Column | Definition and validation |
| --- | --- |
| `publication_id` | Stable identifier for one platform publication; 1–200 printable characters. |
| `video_id` | Existing video in the selected workspace. Foreign or unknown IDs are rejected. |
| `platform` | `instagram`, `tiktok` or `youtube`. |
| `traffic` | `organic` or `paid`. Never pooled together. |
| `source` | Provenance of this export, 1–200 printable characters; keep the label stable across comparable records. |
| `period_start` | Measurement-window start, `YYYY-MM-DD`, inclusive. |
| `period_end` | Window end, `YYYY-MM-DD`, exclusive; after start and not later than today in UTC. |
| `views` | Number of video starts, a nonnegative integer. Not impressions or unique viewers. Blank means unknown. |
| `retention_3s` | Share of those video starts still viewing at three seconds, a finite fraction from 0 to 1. Blank means unknown. |
| `retention_unit` | Exactly `fraction`; a percentage such as `42` is rejected rather than silently converted. |

A seven-day window has `period_end − period_start = 7 days`. The CSV records a
measurement interval, not the publication timestamp. If the source platform's
metric has a different denominator or definition, do not relabel it as this
metric. Transform a compatible export explicitly or leave the value unknown.

## Validation and repeats

HTTP imports are limited to 1 MiB and 5,000 data rows. The entire file is validated
before a transaction inserts anything. Empty files, missing/extra/reordered
columns, malformed rows, invalid dates, non-finite values, invalid units and
foreign videos are rejected. Formula-like identifiers are rejected. Retention
with zero starts is undefined and rejected; zero retention with positive starts
is valid. Missing values remain `null`, not zero.

Uniqueness uses workspace, platform, publication ID and measurement interval.
An exact repeated row is skipped and reported as a duplicate. A changed value
under the same identity is a conflict; no rows in that import are applied.
Overlapping windows for the same publication are rejected. Publication identity
cannot be reassigned to another video, traffic type or metric source.

Disjoint windows can be retained for history, but the first evaluation strategy
requires one unambiguous publication/window per version. It returns insufficient
data instead of selecting the most favorable window. Recommendations also avoid
counting repeated windows as independent videos.
