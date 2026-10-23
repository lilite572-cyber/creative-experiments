#!/usr/bin/env bash
# Run in the owner's already-authorized Terminal. No API inference or media upload.
set -euo pipefail
ce_root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
workspace_root="$(dirname -- "$ce_root")"
reports_root="$workspace_root/creative-experiments-results"
command -v gh >/dev/null || { echo 'GitHub CLI is required.' >&2; exit 1; }
[[ "$(gh api user --jq .login)" == "lilite572-cyber" ]] || {
  echo 'Use the existing lilite572-cyber GitHub account in this Terminal.' >&2; exit 1;
}
bash "$workspace_root/briefguard/scripts/publish_pilot.sh"
cd -- "$reports_root"
[[ "$(git branch --show-current)" == "research/results" ]] || exit 1
[[ -z "$(git status --porcelain)" ]] || { echo 'Review uncommitted report changes first.' >&2; exit 1; }
repo='lilite572-cyber/creative-experiments-results'
if ! git remote get-url origin >/dev/null 2>&1; then
  if gh repo view "$repo" --json name >/dev/null 2>&1; then
    git remote add origin "https://github.com/$repo.git"
  else
    gh repo create "$repo" --public --description 'Creative Experiments: aggregate acceptance and exploratory pilot results; no footage or credentials' --source . --remote origin
  fi
fi
[[ "$(git remote get-url origin)" == "https://github.com/$repo.git" ]] || {
  echo 'Unexpected reports remote; refusing publication.' >&2; exit 1;
}
git fetch origin
if git show-ref --verify --quiet refs/remotes/origin/research/results; then
  git merge-base --is-ancestor origin/research/results HEAD || {
    echo 'Remote results contain newer changes; reconcile without force push.' >&2; exit 1;
  }
fi
git push origin HEAD:research/results
local_head="$(git rev-parse HEAD)"
remote_head="$(git ls-remote origin refs/heads/research/results | cut -f1)"
[[ "$local_head" == "$remote_head" ]] || { echo 'Remote verification failed.' >&2; exit 1; }
echo 'Published and verified: https://github.com/lilite572-cyber/creative-experiments-results/tree/research/results'
echo 'BriefGuard draft PR: https://github.com/lilite572-cyber/briefguard/pull/1'

# The owner also requested publication of the full application source.
bash "$ce_root/scripts/publish_source.sh"
