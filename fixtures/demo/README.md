# Authored demonstration media

`sample.mp4` and `replacement.mp4` are programmatically drawn geometric coffee
illustrations made by `app/media.py:make_demo`. No stock footage, third-party
photography, music, or generative-video provider is involved.

`metrics.csv` contains invented publication statistics for the four seeded demo
videos. It can be imported only after `python -m app.demo` creates their IDs.
The seed already imports those rows, so repeating this file demonstrates
idempotent import. These numbers are not campaign measurements.

Use `replacement.mp4` for the 0–2 second edit in the synthetic workspace.
Download the result CSV from the new experiment to obtain its actual variant ID.
That CSV is also synthetic. Ordinary user media belongs in a separate workspace.
