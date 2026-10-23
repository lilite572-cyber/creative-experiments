#!/usr/bin/env bash
# Publish the complete tracked application, never the local data directory.
set -euo pipefail
project_root="$(cd -- "$(dirname -- "$0")/.." && pwd)"
cd -- "$project_root"
repo='lilite572-cyber/creative-experiments'
branch='feature/creative-experiments'
expected_remote="https://github.com/$repo.git"
[[ "$(git branch --show-current)" == "$branch" ]] || { echo 'Unexpected branch.' >&2; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo 'Review uncommitted changes first.' >&2; exit 1; }
python3 scripts/check_publication.py
command -v gh >/dev/null || { echo 'GitHub CLI is required.' >&2; exit 1; }
[[ "$(gh api user --jq .login)" == "lilite572-cyber" ]] || {
  echo 'This Terminal must use the existing lilite572-cyber GitHub authorization.' >&2; exit 1;
}
if ! git remote get-url origin >/dev/null 2>&1; then
  if gh repo view "$repo" --json name >/dev/null 2>&1; then
    git remote add origin "$expected_remote"
  else
    gh repo create "$repo" --public --description 'Local video experiment workspace: evidence, hypotheses, precise edits and recorded outcomes' --source . --remote origin
  fi
fi
actual_remote="$(git remote get-url origin)"
[[ "$actual_remote" == "$expected_remote" || "$actual_remote" == "git@github.com:$repo.git" ]] || {
  echo 'Unexpected remote; refusing push.' >&2; exit 1;
}
git fetch origin
if git show-ref --verify --quiet "refs/remotes/origin/$branch"; then
  git merge-base --is-ancestor "origin/$branch" HEAD || {
    echo 'Remote branch contains other changes; reconcile without force push.' >&2; exit 1;
  }
fi
git push --set-upstream origin "HEAD:$branch"
local_head="$(git rev-parse HEAD)"
remote_head="$(git ls-remote origin "refs/heads/$branch" | cut -f1)"
[[ "$local_head" == "$remote_head" ]] || { echo 'Remote commit verification failed.' >&2; exit 1; }
printf 'Published complete application at %s\nhttps://github.com/%s/tree/%s\n' "$local_head" "$repo" "$branch"
