# Generated media size correction

The natural-video browser workflow exposed a real edit failure: a compressed
44.46-second source under the 50 MiB upload limit expanded beyond 100 MiB during
lossless H.264 normalization/editing. The original media module applied its input
file limit to the internally generated output and rejected the otherwise valid
variant. The failed operation remains in history.

`app/media_edit_v2.py` is an explicitly separate application editor derived from
the frozen `app/media.py` implementation. Frozen media code, sampling, original
pilot runtime hashes and saved results are unchanged. Only the application's
editing route uses v2; uploaded files still have the original 50 MiB HTTP limit
and source/replacement decoding uses the original 100 MiB media limit.

Internally generated master and edited output have a 512 MiB cap. Both FFmpeg
commands use `-fs`; both files must remain at least 2 MiB below that cap because
FFmpeg can stop successfully at a size bound before encoding the complete clip.
Master duration must match the original within one 24 fps frame plus the source
metadata's hundredth-second precision. Oversized or shortened files are rejected
before publication. The two generated files can temporarily use about 1 GiB of
disk; processing timeouts and all other dimension/duration bounds remain.

The previous preservation checks are retained: identical decoded frame count,
SHA-256 equality outside the replacement interval against the normalized master,
exact CFR packet timestamps/durations, copied source audio and atomic publication
of a fully verified output. The report identifies `generated-media-v2`. Larger
files are hashed incrementally instead of loading the whole file into memory.

This is not a general increase in allowed hostile uploads. Large generated
variants can be played and compared but the original analysis/source-edit input
path still rejects files above 100 MiB. Export a smaller input for a fresh
analysis or subsequent edit; automatic lossy recompression would invalidate the
exact decoded-frame preservation claim and is not performed.
