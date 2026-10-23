# Source publication

The complete application is prepared for the repository
`lilite572-cyber/creative-experiments`, branch `feature/creative-experiments`.
The separate `creative-experiments-results` repository contains aggregate reports.

From an owner-authorized Terminal:

```bash
bash scripts/publish_source.sh
```

The script checks tracked files and reachable history for private paths and common
credential patterns, creates the source repository if needed, performs a normal
push and verifies the remote commit SHA. It never pushes main/master, force-pushes,
merges a PR, or calls a model. A successful verification message is the publication
receipt; a prepared script or local commit is not evidence of publication.

Included: application source, frontend, tests, dependency lock, documentation,
acceptance reports and two programmatically authored synthetic demo MP4 files.
Excluded: `data/`, keys, working database, sessions, downloaded source videos,
raw provider responses and the local Python environment. A fresh clone runs the
synthetic demo through README instructions; reproducing a private API pilot still
requires the owner's separately retained packet.

## Screenshot attribution

`artifacts/final_acceptance/browser.jpg` is an application screenshot containing
frames from **Coffee Bean & Tea Leaf Process**, by **Kelliks**, licensed under
[CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/).
[Original source](https://commons.wikimedia.org/wiki/File:Coffee_Bean_%26_Tea_Leaf_Process.webm).
The displayed footage was converted to silent 24 fps H.264; the alternative
version replaces its first two seconds with an excerpt from the same source.
Those depicted source frames and their adaptations retain CC BY-SA 3.0.
Brand names shown in the footage do not imply endorsement or affiliation.

Historical protocol/runtime files retain their exact contents for frozen-hash
verification. Their records are not personal human-review sign-offs.
